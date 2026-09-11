"""
Anthropic client wrapper.

Everything that touches the API key lives here. The key is read from the
environment on the server only and is never sent to, or referenced by, the
frontend. Logs record model name, latency, token counts and truncated prompts —
never the key, and never a full prompt containing customer data.

The wrapper enforces:
  * a hard timeout,
  * bounded retries on transient failures only,
  * response validation (non-empty, length-capped, no leaked scaffolding),
  * a typed result that always tells the caller whether the text came from the
    model or from a deterministic fallback.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

from app.config import get_settings

log = logging.getLogger(__name__)

MAX_CHARS = 4000

# Transient conditions worth one retry. Anything else fails fast to the fallback:
# a business dashboard should degrade in a second, not hang.
_RETRYABLE = ("overloaded", "rate_limit", "timeout", "timed out", "connection",
              "internal server error", "503", "529")


@dataclass
class LlmResult:
    ok: bool
    text: str
    model: str | None = None
    latency_ms: int | None = None
    error: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class LlmUnavailable(RuntimeError):
    pass


class LlmClient:
    """Thin, defensive wrapper around `anthropic.Anthropic`."""

    def __init__(self) -> None:
        s = get_settings()
        self.model = s.model_name
        self.timeout = s.llm_timeout_seconds
        self.max_tokens = s.llm_max_tokens
        self.max_retries = s.llm_max_retries
        self._enabled = s.llm_enabled
        self._client = None
        if self._enabled:
            try:
                from anthropic import Anthropic

                self._client = Anthropic(api_key=s.anthropic_api_key, timeout=self.timeout)
                log.info("LLM enabled (model=%s, timeout=%.1fs)", self.model, self.timeout)
            except Exception as exc:  # pragma: no cover - import/config failure
                log.error("failed to construct Anthropic client: %s", type(exc).__name__)
                self._enabled = False
        else:
            log.warning(
                "ANTHROPIC_API_KEY not set — explanations and Q&A will use the "
                "deterministic fallback and be labelled as such in the UI."
            )

    @property
    def available(self) -> bool:
        return bool(self._enabled and self._client is not None)

    # -----------------------------------------------------------------------
    def complete(self, *, system: str, user: str, max_tokens: int | None = None) -> LlmResult:
        """Single completion. Never raises — failure is returned, not thrown."""
        if not self.available:
            return LlmResult(False, "", error="llm_not_configured")

        attempts = self.max_retries + 1
        last_err = "unknown_error"
        for attempt in range(attempts):
            started = time.perf_counter()
            try:
                resp = self._client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens or self.max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                latency = int((time.perf_counter() - started) * 1000)
                text = _extract_text(resp)
                valid, reason = _validate(text)
                if not valid:
                    log.warning("LLM response rejected (%s), attempt %d/%d",
                                reason, attempt + 1, attempts)
                    last_err = f"invalid_response:{reason}"
                    continue
                usage = getattr(resp, "usage", None)
                log.info(
                    "LLM ok model=%s latency=%dms in_tokens=%s out_tokens=%s chars=%d",
                    self.model, latency,
                    getattr(usage, "input_tokens", None),
                    getattr(usage, "output_tokens", None), len(text),
                )
                return LlmResult(
                    True, text, model=self.model, latency_ms=latency,
                    input_tokens=getattr(usage, "input_tokens", None),
                    output_tokens=getattr(usage, "output_tokens", None),
                )
            except Exception as exc:
                latency = int((time.perf_counter() - started) * 1000)
                name = type(exc).__name__
                detail = str(exc)[:200]
                last_err = name
                retryable = any(t in detail.lower() or t in name.lower() for t in _RETRYABLE)
                log.warning(
                    "LLM call failed (%s) after %dms, attempt %d/%d, retryable=%s: %s",
                    name, latency, attempt + 1, attempts, retryable, detail,
                )
                if not retryable or attempt == attempts - 1:
                    break
                time.sleep(0.4 * (attempt + 1))
        return LlmResult(False, "", error=last_err)


def _extract_text(resp) -> str:
    parts = []
    for block in getattr(resp, "content", []) or []:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", ""))
    return "\n".join(parts).strip()


def _validate(text: str) -> tuple[bool, str]:
    """Reject empty, truncated-to-nothing, or scaffolding-leaking responses."""
    if not text or not text.strip():
        return False, "empty"
    if len(text) > MAX_CHARS:
        return False, "too_long"
    # A model that echoes the evidence block back has not answered the question.
    if re.search(r"^\s*\{\s*[\"']sku", text, re.IGNORECASE):
        return False, "echoed_evidence_json"
    if len(text.split()) < 4:
        return False, "too_short"
    return True, ""


_client: LlmClient | None = None


def get_llm() -> LlmClient:
    global _client
    if _client is None:
        _client = LlmClient()
    return _client


def reset_for_tests(client: LlmClient | None = None) -> None:
    global _client
    _client = client

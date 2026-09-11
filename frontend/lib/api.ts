/**
 * Backend client.
 *
 * The base URL comes from NEXT_PUBLIC_API_URL and nothing else — no localhost is
 * hardcoded into a code path that ships to production. There is deliberately no
 * Anthropic key here and no ML logic: this file only speaks HTTP to FastAPI.
 */
import type {
  CategoryRisk,
  DashboardResponse,
  ExplanationResponse,
  MetadataResponse,
  ModelInfo,
  QaResponse,
  SkuDetail,
  SkuSummary,
} from "@/types/api";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ??
  "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly isNetwork = false,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(
      `Cannot reach the API at ${API_BASE}. Check that the backend is running and that NEXT_PUBLIC_API_URL is correct.`,
      0,
      true,
    );
  }

  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      /* response had no JSON body; keep the status line */
    }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as T;
}

export interface SkuFilters {
  risk_level?: string[];
  risk_type?: string[];
  category?: string[];
  cold_start?: boolean;
  search?: string;
}

function toQuery(f: SkuFilters): string {
  const p = new URLSearchParams();
  if (f.risk_level?.length) p.set("risk_level", f.risk_level.join(","));
  if (f.risk_type?.length) p.set("risk_type", f.risk_type.join(","));
  if (f.category?.length) p.set("category", f.category.join(","));
  if (f.cold_start !== undefined) p.set("cold_start", String(f.cold_start));
  if (f.search) p.set("search", f.search);
  const q = p.toString();
  return q ? `?${q}` : "";
}

export const api = {
  health: () =>
    request<{
      status: string;
      artifacts_loaded: boolean;
      llm_configured: boolean;
    }>("/health"),
  dashboard: () => request<DashboardResponse>("/api/dashboard"),
  skus: (f: SkuFilters = {}) => request<SkuSummary[]>(`/api/skus${toQuery(f)}`),
  sku: (id: string, historyDays = 90) =>
    request<SkuDetail>(
      `/api/skus/${encodeURIComponent(id)}?history_days=${historyDays}`,
    ),
  explanation: (id: string, force = false) =>
    request<ExplanationResponse>(
      `/api/skus/${encodeURIComponent(id)}/explanation${force ? "?force=true" : ""}`,
    ),
  ask: (question: string) =>
    request<QaResponse>("/api/qa", {
      method: "POST",
      body: JSON.stringify({ question }),
    }),
  qaSuggestions: () => request<string[]>("/api/qa/suggestions"),
  metadata: () => request<MetadataResponse>("/api/metadata"),
  modelInfo: () => request<ModelInfo>("/api/model-info"),
  categories: () => request<CategoryRisk[]>("/api/categories"),
};

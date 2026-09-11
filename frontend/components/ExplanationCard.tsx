"use client";

import { useCallback, useState } from "react";
import { Loader2, RefreshCw, Sparkles, TriangleAlert } from "lucide-react";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/primitives";
import { Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import type { ExplanationResponse } from "@/types/api";

/**
 * The AI explanation card.
 *
 * The call goes to the backend, which owns the Anthropic key and builds the
 * evidence object. The browser never talks to Anthropic and never sees a key.
 */
export function ExplanationCard({ skuId }: { skuId: string }) {
  const [data, setData] = useState<ExplanationResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (force: boolean) => {
      setLoading(true);
      setError(null);
      try {
        setData(await api.explanation(skuId, force));
      } catch (e) {
        setError(
          e instanceof Error
            ? e.message
            : "Could not generate an explanation right now.",
        );
      } finally {
        setLoading(false);
      }
    },
    [skuId],
  );

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-slate-400" />
            <CardTitle>Why this SKU is flagged</CardTitle>
          </div>
          <div className="flex items-center gap-2">
            {data?.source === "llm" && data.model && (
              <Badge variant="outline">
                {data.cached ? "Cached ·" : ""}
                {data.model}
              </Badge>
            )}
            <Button
              variant={data ? "outline" : "default"}
              size="sm"
              onClick={() => void load(Boolean(data))}
              disabled={loading}
            >
              {loading ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : data ? (
                <RefreshCw className="h-3.5 w-3.5" />
              ) : (
                <Sparkles className="h-3.5 w-3.5" />
              )}
              {loading
                ? "Generating…"
                : data
                  ? "Regenerate"
                  : "Generate explanation"}
            </Button>
          </div>
        </div>
        <CardDescription>
          Written from this SKU&apos;s own figures — stock, forecast, lead time,
          delivery history — and nothing else.
        </CardDescription>
      </CardHeader>

      <CardContent>
        {loading && (
          <div className="space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-11/12" />
            <Skeleton className="h-4 w-4/5" />
            <p className="pt-2 text-xs text-slate-400">
              Sending the computed evidence to the model…
            </p>
          </div>
        )}

        {!loading && error && (
          <div className="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
            <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
            <div className="flex-1">
              <p className="font-medium">Explanation unavailable</p>
              <p className="mt-0.5">{error}</p>
              <button
                onClick={() => void load(true)}
                className="mt-2 text-xs font-medium underline underline-offset-4"
              >
                Try again
              </button>
            </div>
          </div>
        )}

        {!loading && !error && !data && (
          <p className="text-sm text-slate-500">
            Select <span className="font-medium">Generate explanation</span> for
            a plain-English summary of why this SKU is flagged and what to do
            about it.
          </p>
        )}

        {!loading && data && (
          <div className="space-y-3">
            <p className="whitespace-pre-line text-sm leading-relaxed text-slate-800">
              {data.explanation}
            </p>

            {data.source === "fallback" && (
              <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>
                  The AI-generated explanation is temporarily unavailable
                  {data.error ? ` (${data.error})` : ""}. Shown instead is a
                  direct read-out of the same computed figures, so the numbers
                  are still correct.
                </span>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

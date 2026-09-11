"use client";

import { useState } from "react";
import Link from "next/link";
import { Database, Loader2, Send, Sparkles, TriangleAlert } from "lucide-react";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
} from "@/components/ui/primitives";
import { api } from "@/lib/api";
import type { QaResponse } from "@/types/api";

const FALLBACK_SUGGESTIONS = [
  "Which SKUs need attention?",
  "Which products have the highest stockout risk?",
  "Which SKUs are overstocked and tying up working capital?",
  "Which categories carry the most risk?",
];

export function AskPanel({ suggestions }: { suggestions?: string[] }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<QaResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const chips = (
    suggestions?.length ? suggestions : FALLBACK_SUGGESTIONS
  ).slice(0, 5);

  async function ask(q: string) {
    const text = q.trim();
    if (text.length < 3 || loading) return;
    setLoading(true);
    setError(null);
    setAnswer(null);
    try {
      setAnswer(await api.ask(text));
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Could not get an answer. Please try again.",
      );
    } finally {
      setLoading(false);
    }
  }

  const groundedSkus = answer?.grounded_on.flatMap((g) => g.sku_ids) ?? [];

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-slate-400" />
          <CardTitle>Ask about your inventory</CardTitle>
        </div>
        <CardDescription>
          Answers are generated from the live risk data on this dashboard — not
          from the model&apos;s general knowledge.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void ask(question);
          }}
          className="flex gap-2"
        >
          <Input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask about your inventory…"
            aria-label="Ask about your inventory"
            maxLength={500}
            disabled={loading}
          />
          <Button
            type="submit"
            disabled={loading || question.trim().length < 3}
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            <span className="hidden sm:inline">Ask</span>
          </Button>
        </form>

        <div className="flex flex-wrap gap-2">
          {chips.map((s) => (
            <button
              key={s}
              onClick={() => {
                setQuestion(s);
                void ask(s);
              }}
              disabled={loading}
              className="rounded-full border border-slate-200 px-3 py-1 text-xs text-slate-600 transition-colors hover:border-slate-300 hover:bg-slate-50 disabled:opacity-50"
            >
              {s}
            </button>
          ))}
        </div>

        {loading && (
          <div className="flex items-center gap-2 rounded-lg bg-slate-50 px-4 py-6 text-sm text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            Reading the current risk data and composing an answer…
          </div>
        )}

        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
            <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <p className="font-medium">Could not answer that</p>
              <p className="mt-0.5">{error}</p>
            </div>
          </div>
        )}

        {answer && !loading && (
          <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50/60 p-4">
            <p className="whitespace-pre-line text-sm leading-relaxed text-slate-800">
              {answer.answer}
            </p>

            {answer.source === "fallback" && (
              <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>
                  The AI service is unavailable, so this is a direct read-out of
                  the underlying figures rather than a generated answer.
                </span>
              </div>
            )}

            <div className="flex flex-wrap items-center gap-2 border-t border-slate-200 pt-3">
              <Badge variant="outline">
                <Database className="h-3 w-3" />
                Grounded in live dashboard data
              </Badge>
              {answer.grounded_on.map((g) => (
                <Badge key={g.kind} variant="outline">
                  {g.label}
                </Badge>
              ))}
              {answer.source === "llm" && answer.model && (
                <span className="text-xs text-slate-400">
                  via {answer.model}
                </span>
              )}
            </div>

            {groundedSkus.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 text-xs">
                <span className="text-slate-500">Open:</span>
                {groundedSkus.slice(0, 8).map((s) => (
                  <Link
                    key={s}
                    href={`/supply-chain/sku/${s}`}
                    className="rounded border border-slate-200 px-1.5 py-0.5 font-medium text-slate-700 hover:bg-white"
                  >
                    {s}
                  </Link>
                ))}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

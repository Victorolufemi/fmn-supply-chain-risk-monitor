"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";
import {
  NewSkuBadge,
  RiskBadge,
  RiskTypeBadge,
  UndersuppliedBadge,
} from "@/components/RiskBadge";
import { EmptyState } from "@/components/ui/states";
import { days, num } from "@/lib/format";
import type { SkuSummary } from "@/types/api";

function Cell({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <td className={`px-4 py-3 align-middle ${className}`}>{children}</td>;
}

/** Highlights cover that is already shorter than the time it takes to restock. */
function Coverage({ sku }: { sku: SkuSummary }) {
  const c = sku.inventory_coverage_days;
  if (c === null) return <span className="text-slate-400">—</span>;
  const short = c < sku.lead_time_days;
  return (
    <span
      className={short ? "font-medium text-rose-600" : "text-slate-700"}
      title={
        short
          ? `${c.toFixed(1)} days of cover is less than the ${sku.lead_time_days}-day lead time.`
          : undefined
      }
    >
      {days(c)}
    </span>
  );
}

export function SkuTable({
  skus,
  onClear,
}: {
  skus: SkuSummary[];
  onClear?: () => void;
}) {
  if (skus.length === 0) {
    return (
      <EmptyState
        title="No SKUs match these filters"
        hint="Try widening the risk level, category or search filters."
        action={
          onClear ? (
            <button
              onClick={onClear}
              className="text-sm font-medium text-slate-900 underline underline-offset-4"
            >
              Clear all filters
            </button>
          ) : undefined
        }
      />
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[980px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
            <th className="px-4 py-2.5 font-medium">SKU</th>
            <th className="px-4 py-2.5 font-medium">Category</th>
            <th className="px-4 py-2.5 font-medium">Risk</th>
            <th className="px-4 py-2.5 font-medium">Type</th>
            <th className="px-4 py-2.5 text-right font-medium">Stock</th>
            <th className="px-4 py-2.5 text-right font-medium">Cover</th>
            <th className="px-4 py-2.5 text-right font-medium">Lead time</th>
            <th className="px-4 py-2.5 text-right font-medium">Forecast/day</th>
            <th className="px-4 py-2.5 font-medium">Main reason</th>
            <th className="px-4 py-2.5" />
          </tr>
        </thead>
        <tbody>
          {skus.map((s) => (
            <tr
              key={s.sku_id}
              className="border-b border-slate-100 transition-colors last:border-0 hover:bg-slate-50"
            >
              <Cell>
                <Link
                  href={`/supply-chain/sku/${s.sku_id}`}
                  className="font-medium text-slate-900 hover:underline"
                >
                  {s.sku_id}
                </Link>
                <div className="mt-1 flex flex-wrap gap-1">
                  {s.is_cold_start && <NewSkuBadge days={s.days_of_history} />}
                  {s.is_structurally_undersupplied && !s.is_cold_start && (
                    <UndersuppliedBadge ratio={null} />
                  )}
                </div>
              </Cell>
              <Cell className="text-slate-600">{s.category}</Cell>
              <Cell>
                <RiskBadge level={s.risk_level} />
              </Cell>
              <Cell>
                <RiskTypeBadge type={s.risk_type} />
              </Cell>
              <Cell className="text-right tabular-nums text-slate-700">
                {num(s.current_stock)}
              </Cell>
              <Cell className="text-right tabular-nums">
                <Coverage sku={s} />
              </Cell>
              <Cell className="text-right tabular-nums text-slate-600">
                {num(s.lead_time_days)}d
              </Cell>
              <Cell className="text-right tabular-nums text-slate-700">
                {num(s.forecast_daily_demand)}
              </Cell>
              <Cell className="max-w-[320px] text-slate-600">
                <span className="line-clamp-2">{s.headline}</span>
              </Cell>
              <Cell className="text-right">
                <Link
                  href={`/supply-chain/sku/${s.sku_id}`}
                  aria-label={`Open ${s.sku_id}`}
                  className="inline-flex h-7 w-7 items-center justify-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                >
                  <ChevronRight className="h-4 w-4" />
                </Link>
              </Cell>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

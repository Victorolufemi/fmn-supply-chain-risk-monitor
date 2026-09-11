"use client";

import Link from "next/link";
import {
  AlertOctagon,
  ArrowDownCircle,
  ArrowUpCircle,
  Boxes,
} from "lucide-react";
import { Card, InfoTip } from "@/components/ui/primitives";
import { num } from "@/lib/format";
import type { DashboardKpis } from "@/types/api";

/**
 * A KPI tile carries a 3px gradient bar in the colour of what it measures —
 * neutral for the portfolio count, red for attention, orange for stockout, blue
 * for overstock. It is the same colour language as the risk badges, so the eye
 * links the tile to the rows it filters to, and the icon tile repeats it.
 */
function Kpi({
  label,
  value,
  sub,
  icon,
  href,
  accent,
  iconClass,
  tip,
}: {
  label: string;
  value: string;
  sub: string;
  icon: React.ReactNode;
  href?: string;
  accent: string;
  iconClass: string;
  tip: string;
}) {
  const body = (
    <Card
      className="accent-bar relative h-full overflow-hidden p-5 pt-6 transition-all hover:-translate-y-0.5 hover:shadow-md hover:shadow-slate-300/50"
      style={{ ["--accent" as string]: accent }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
            {label}
          </span>
          <InfoTip text={tip} />
        </div>
        <span
          className={`flex h-7 w-7 items-center justify-center rounded-lg text-white shadow-sm ${iconClass}`}
        >
          {icon}
        </span>
      </div>
      <p className="mt-3 text-3xl font-semibold tabular-nums text-slate-900">
        {value}
      </p>
      <p className="mt-1.5 text-xs text-slate-500">{sub}</p>
    </Card>
  );

  return href ? (
    <Link
      href={href}
      className="block rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-300"
    >
      {body}
    </Link>
  ) : (
    body
  );
}

export function KpiCards({ kpis }: { kpis: DashboardKpis }) {
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <Kpi
        label="SKUs monitored"
        value={num(kpis.total_skus)}
        sub={`${kpis.newly_launched_count} newly launched · ${kpis.healthy_count} healthy`}
        icon={<Boxes className="h-4 w-4" />}
        accent="var(--grad-neutral)"
        iconClass="grad-neutral"
        tip="Every SKU in the dataset is scored every time the model runs. Newly launched SKUs have far less history and are marked accordingly."
      />
      <Kpi
        label="Need attention"
        value={num(kpis.high_risk_count)}
        sub={`${kpis.critical_count} critical · ${kpis.out_of_stock_now} out of stock now`}
        icon={<AlertOctagon className="h-4 w-4" />}
        accent="var(--grad-critical)"
        iconClass="grad-critical"
        href="/supply-chain?risk=CRITICAL,HIGH"
        tip="SKUs at critical or high risk. Critical means either already at zero stock, or a 70%+ modelled chance of running out before a replenishment ordered today could arrive."
      />
      <Kpi
        label="Stockout risk"
        value={num(kpis.stockout_risk_count)}
        sub={`${kpis.structurally_undersupplied} receiving less than they sell`}
        icon={<ArrowDownCircle className="h-4 w-4" />}
        accent="var(--grad-stockout)"
        iconClass="grad-stockout"
        href="/supply-chain?type=STOCKOUT"
        tip="SKUs whose forecast demand over the lead time, net of expected deliveries, threatens the stock on hand. Under-supplied SKUs are draining structurally regardless of today's level."
      />
      <Kpi
        label="Overstock risk"
        value={num(kpis.overstock_risk_count)}
        sub={`${num(kpis.total_excess_units)} units above policy maximum`}
        icon={<ArrowUpCircle className="h-4 w-4" />}
        accent="var(--grad-overstock)"
        iconClass="grad-overstock"
        href="/supply-chain?type=OVERSTOCK"
        tip="Stock above the order-up-to level implied by the forecast, the lead time and a review cycle. Measured against expected demand, never against raw unit counts."
      />
    </div>
  );
}

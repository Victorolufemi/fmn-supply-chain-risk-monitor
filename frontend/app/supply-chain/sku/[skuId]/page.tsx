"use client";

import Link from "next/link";
import { use } from "react";
import {
  ArrowLeft,
  CalendarClock,
  ClipboardCheck,
  Info,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { ExplanationCard } from "@/components/ExplanationCard";
import {
  NewSkuBadge,
  RiskBadge,
  RiskTypeBadge,
  UndersuppliedBadge,
} from "@/components/RiskBadge";
import { DemandChart, InventoryChart } from "@/components/SkuCharts";
import {
  Badge,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  InfoTip,
  Skeleton,
} from "@/components/ui/primitives";
import { ChartSkeleton, ErrorState } from "@/components/ui/states";
import { api } from "@/lib/api";
import { days, longDate, num, pct, probability } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import type { SkuDetail } from "@/types/api";

export default function SkuPage({
  params,
}: {
  params: Promise<{ skuId: string }>;
}) {
  const { skuId } = use(params);
  const { data, loading, error, reload } = useApi<SkuDetail>(
    () => api.sku(decodeURIComponent(skuId)),
    [skuId],
  );

  return (
    <div className="space-y-6">
      <Link
        href="/supply-chain"
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-900"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to dashboard
      </Link>

      {error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : loading || !data ? (
        <LoadingDetail />
      ) : (
        <Detail sku={data} />
      )}
    </div>
  );
}

function Detail({ sku }: { sku: SkuDetail }) {
  const stockoutRisk = sku.risk_type === "STOCKOUT";

  return (
    <>
      {/* ------------------------------------------------------ header ---- */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
              {sku.sku_id}
            </h1>
            <RiskBadge level={sku.risk_level} />
            <RiskTypeBadge type={sku.risk_type} />
            {sku.is_cold_start && <NewSkuBadge days={sku.days_of_history} />}
            {sku.is_structurally_undersupplied && (
              <UndersuppliedBadge ratio={sku.supply_coverage_ratio} />
            )}
          </div>
          <p className="mt-1.5 text-sm text-slate-500">
            {sku.category} · {sku.headline}
          </p>
        </div>
        <Badge variant="outline">Data as of {longDate(sku.as_of)}</Badge>
      </div>

      {/* --------------------------------------------- cold-start note ---- */}
      {sku.is_cold_start && (
        <div className="flex items-start gap-2 rounded-lg border border-violet-200 bg-violet-50 px-4 py-3 text-sm text-violet-900">
          <Info className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p className="font-medium">
              Limited history — this SKU has {sku.days_of_history} days of
              observed demand
            </p>
            <p className="mt-0.5">
              Its risk estimate is less certain than for established SKUs. The
              weekly demand pattern and the variability used for the safety
              buffer are largely borrowed from other {sku.category} products,
              its lead time is the {sku.category} median because the recorded
              values were inconsistent, and its forecast comes from a simpler,
              more robust model than the one used elsewhere.
            </p>
          </div>
        </div>
      )}

      {/* -------------------------------------------- recommended action -- */}
      <Card className="border-slate-300">
        <CardContent className="flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 rounded-lg bg-slate-900 p-2">
              <ClipboardCheck className="h-4 w-4 text-white" />
            </span>
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                Recommended action
              </p>
              <p className="mt-1 text-sm font-medium text-slate-900">
                {sku.recommended_action}
              </p>
            </div>
          </div>
          {stockoutRisk && sku.suggested_order_qty ? (
            <div className="shrink-0 rounded-lg bg-slate-50 px-4 py-2 text-center">
              <p className="text-xs text-slate-500">Suggested order</p>
              <p className="text-xl font-semibold tabular-nums text-slate-900">
                {num(sku.suggested_order_qty)}
              </p>
              <p className="text-xs text-slate-500">units</p>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <ExplanationCard skuId={sku.sku_id} />

      {/* ------------------------------------------------------- stats ---- */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat
          label="Stock on hand"
          value={num(sku.current_stock)}
          unit="units"
          tip="Closing stock on the most recent day of data."
        />
        <Stat
          label="Inventory coverage"
          value={days(sku.inventory_coverage_days)}
          unit={`against a ${num(sku.lead_time_days)}-day lead time`}
          tone={
            sku.inventory_coverage_days !== null &&
            sku.inventory_coverage_days < sku.lead_time_days
              ? "text-rose-600"
              : undefined
          }
          tip="Stock on hand divided by forecast daily demand. Below the lead time, an order placed today would arrive after the stock runs out."
        />
        <Stat
          label="Forecast demand"
          value={num(sku.forecast_daily_demand)}
          unit="units/day over the next 7 days"
          tip="Mean of the model's daily forecast for the next seven days."
        />
        <Stat
          label={stockoutRisk ? "Stockout probability" : "Risk score"}
          value={probability(
            stockoutRisk ? sku.stockout_probability : sku.risk_score,
          )}
          unit={
            stockoutRisk
              ? `within the ${num(sku.lead_time_days)}-day lead time`
              : "0 = healthy, 1 = severe"
          }
          tip={
            stockoutRisk
              ? "Modelled chance that demand over the lead time, net of expected deliveries, exceeds the stock on hand. Demand and supply variability are both priced in."
              : "How far stock sits above the order-up-to level implied by the forecast, lead time and review cycle."
          }
        />
      </div>

      {/* ------------------------------------------------------ charts ---- */}
      <div className="grid gap-4 xl:grid-cols-2">
        <DemandChart sku={sku} />
        <InventoryChart sku={sku} />
      </div>

      {/* --------------------------------------------- drivers + policy --- */}
      <div className="grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>Risk drivers</CardTitle>
            <CardDescription>
              The figures behind this flag, most decisive first. These are
              exactly what the AI explanation is given.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {sku.drivers.map((d, i) => (
              <div
                key={d.name}
                className="flex gap-3 border-b border-slate-100 pb-3 last:border-0 last:pb-0"
              >
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-slate-100 text-[10px] font-semibold text-slate-600">
                  {i + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-3">
                    <p className="text-sm font-medium text-slate-900">
                      {d.label}
                    </p>
                    <p className="shrink-0 text-sm font-semibold tabular-nums text-slate-900">
                      {num(d.value, Number.isInteger(d.value ?? 0) ? 0 : 2)}{" "}
                      <span className="text-xs font-normal text-slate-500">
                        {d.unit}
                      </span>
                    </p>
                  </div>
                  <p className="mt-0.5 text-xs leading-relaxed text-slate-500">
                    {d.detail}
                  </p>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Replenishment policy</CardTitle>
              <CardDescription>
                Computed from the forecast, the lead time and this SKU&apos;s
                demand variability.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <Row
                label="Demand over lead time"
                value={`${num(sku.lead_time_demand)} units`}
              />
              <Row
                label="Safety stock"
                value={`${num(sku.safety_stock_units)} units`}
              />
              <Row
                label="Reorder point"
                value={`${num(sku.reorder_point_units)} units`}
              />
              <Row
                label="Order-up-to level"
                value={`${num(sku.order_up_to_units)} units`}
              />
              {sku.excess_units ? (
                <Row
                  label="Above policy maximum"
                  value={`${num(sku.excess_units)} units`}
                />
              ) : null}
              <Row
                label="Days to projected stockout"
                value={
                  sku.days_to_projected_stockout === null
                    ? `Beyond ${sku.forecast.length} days`
                    : `${num(sku.days_to_projected_stockout)} days`
                }
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Demand and supply behaviour</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <Row
                label="Last 7 days average"
                value={`${num(sku.recent_7d_avg_demand)} units/day`}
              />
              <Row
                label="Previous 7 days average"
                value={
                  sku.previous_7d_avg_demand === null
                    ? "—"
                    : `${num(sku.previous_7d_avg_demand)} units/day`
                }
              />
              <Row
                label="Change"
                value={
                  <span className="inline-flex items-center gap-1">
                    {sku.demand_change_pct !== null &&
                      (sku.demand_change_pct >= 0 ? (
                        <TrendingUp className="h-3.5 w-3.5 text-slate-400" />
                      ) : (
                        <TrendingDown className="h-3.5 w-3.5 text-slate-400" />
                      ))}
                    {pct(sku.demand_change_pct, 1)}
                  </span>
                }
              />
              <Row
                label="Demand variability (CV)"
                value={num(sku.demand_cv, 2)}
              />
              <Row
                label="Replenishment rate"
                value={`${num(sku.replenishment_rate_per_day)} units/day`}
              />
              <Row
                label="Expected inbound in lead time"
                value={
                  <span className="inline-flex items-center gap-1">
                    {num(sku.expected_inbound_within_lead_time)} units
                    <InfoTip text="Inferred from this SKU's own delivery record. The dataset contains no open purchase orders, so this is an estimate rather than confirmed stock, and it is shown beside the risk score rather than removing the flag." />
                  </span>
                }
              />
              <Row
                label={`Supply vs demand (${sku.supply_window_days}d)`}
                value={
                  sku.supply_coverage_ratio === null ? (
                    "—"
                  ) : (
                    <span className="inline-flex items-center gap-1">
                      {Math.round(sku.supply_coverage_ratio * 100)} received per
                      100 sold
                      <InfoTip
                        text={`Measured over ${sku.supply_window_days} days, a window covering whole delivery cycles so the ratio is not distorted by a delivery falling just inside or outside it. Below 100 means inventory is draining regardless of today's stock level.`}
                      />
                    </span>
                  )
                }
              />
              <Row
                label="Days since last delivery"
                value={
                  sku.days_since_last_receipt === null
                    ? "No deliveries on record"
                    : `${num(sku.days_since_last_receipt)} days`
                }
              />
              <Row
                label="Days at zero stock (all time)"
                value={`${Math.round(sku.observed_stockout_rate_all_time * 100)}% of days`}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <CalendarClock className="h-4 w-4 text-slate-400" />
                <CardTitle>Model confidence</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <Row
                label="Observed history"
                value={`${sku.days_of_history} days`}
              />
              <Row
                label="Confidence"
                value={
                  sku.confidence === "LOW"
                    ? "Limited history"
                    : sku.confidence === "MEDIUM"
                      ? "Medium"
                      : "High"
                }
              />
              <Row
                label="If nothing is on order"
                value={probability(sku.stockout_probability_no_inbound)}
              />
              <p className="pt-1 text-xs leading-relaxed text-slate-500">
                The headline probability credits this SKU&apos;s usual
                deliveries. The figure above is the conservative view for a
                planner who knows nothing is currently on order.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}

function Stat({
  label,
  value,
  unit,
  tone,
  tip,
}: {
  label: string;
  value: string;
  unit: string;
  tone?: string;
  tip: string;
}) {
  return (
    <Card className="p-5">
      <div className="flex items-center gap-1.5">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
          {label}
        </p>
        <InfoTip text={tip} />
      </div>
      <p
        className={`mt-2 text-2xl font-semibold tabular-nums ${
          tone ?? "text-slate-900"
        }`}
      >
        {value}
      </p>
      <p className="mt-1 text-xs text-slate-500">{unit}</p>
    </Card>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-slate-500">{label}</span>
      <span className="text-right font-medium tabular-nums text-slate-900">
        {value}
      </span>
    </div>
  );
}

function LoadingDetail() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-9 w-64" />
      <Skeleton className="h-20 w-full rounded-xl" />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-28 rounded-xl" />
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <ChartSkeleton height={300} />
        <ChartSkeleton height={300} />
      </div>
    </div>
  );
}

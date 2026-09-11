"use client";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import {
  Badge,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Skeleton,
} from "@/components/ui/primitives";
import { ErrorState } from "@/components/ui/states";
import { api } from "@/lib/api";
import { longDate, num } from "@/lib/format";
import { useApi } from "@/lib/useApi";

/**
 * Transparency page. A planner is being asked to act on a model's output, so the
 * validation design and its measured error are part of the product, not an
 * appendix.
 */
export default function ModelPage() {
  const info = useApi(() => api.modelInfo(), []);
  const meta = useApi(() => api.metadata(), []);

  return (
    <div className="space-y-6">
      <Link
        href="/supply-chain"
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-900"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to dashboard
      </Link>

      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
          How it works
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          What the model predicts, how well it does it, and what it cannot tell
          you.
        </p>
      </div>

      {info.error ? (
        <ErrorState error={info.error} onRetry={info.reload} />
      ) : info.loading || !info.data ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-64 rounded-xl" />
          <Skeleton className="h-64 rounded-xl" />
        </div>
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Forecast accuracy</CardTitle>
                <CardDescription>
                  Measured on {num(info.data.metrics.forecast_points)} forecasts
                  across {String(info.data.validation.folds)} chronological
                  validation folds — never on data the model had already seen.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <Row
                  label="WAPE (primary metric)"
                  value={
                    info.data.metrics.wape_pooled !== null
                      ? `${(info.data.metrics.wape_pooled * 100).toFixed(1)}%`
                      : "—"
                  }
                />
                <Row
                  label="Mean absolute error"
                  value={`${num(info.data.metrics.mae_units, 1)} units/day`}
                />
                <Row
                  label="RMSE"
                  value={`${num(info.data.metrics.rmse_units, 1)} units/day`}
                />
                <Row
                  label="Bias"
                  value={
                    info.data.metrics.bias_pct !== null
                      ? `${info.data.metrics.bias_pct > 0 ? "+" : ""}${info.data.metrics.bias_pct.toFixed(2)}%`
                      : "—"
                  }
                />
                <Row
                  label="Variation across folds"
                  value={
                    info.data.metrics.wape_sd_across_folds !== null
                      ? `±${(info.data.metrics.wape_sd_across_folds * 100).toFixed(2)} pts`
                      : "—"
                  }
                />
                <p className="pt-2 text-xs leading-relaxed text-slate-500">
                  WAPE is total absolute error divided by total actual volume:
                  the forecast is off by this share of the units actually
                  shipped. It was chosen over MAPE, which is distorted by
                  low-volume days, and over RMSE, which chases occasional demand
                  spikes.
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Model selection</CardTitle>
                <CardDescription>
                  Every candidate was scored the same way. The simplest model
                  that won, won.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-500">
                      <th className="pb-2 font-medium">Model</th>
                      <th className="pb-2 font-medium">Role</th>
                      <th className="pb-2 text-right font-medium">WAPE</th>
                    </tr>
                  </thead>
                  <tbody>
                    {info.data.baselines.map((b) => (
                      <tr
                        key={b.model}
                        className="border-b border-slate-100 last:border-0"
                      >
                        <td className="py-2 font-mono text-xs text-slate-700">
                          {b.model}
                          {b.model === info.data!.selected_model && (
                            <Badge className="ml-2 bg-emerald-50 text-emerald-700 ring-emerald-600/20">
                              selected
                            </Badge>
                          )}
                        </td>
                        <td className="py-2 text-xs text-slate-500">
                          {b.is_baseline ? "baseline" : "candidate"}
                        </td>
                        <td className="py-2 text-right tabular-nums text-slate-900">
                          {b.wape !== null
                            ? `${(b.wape * 100).toFixed(1)}%`
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Validation design</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <Row
                  label="Strategy"
                  value={String(info.data.validation.strategy)}
                />
                <Row label="Folds" value={String(info.data.validation.folds)} />
                <Row
                  label="Forecast horizon per fold"
                  value={`${String(info.data.validation.horizon_days)} days`}
                />
                <Row label="Random split used" value="No" />
                <p className="pt-2 text-xs leading-relaxed text-slate-500">
                  {String(info.data.validation.why_not_random)}
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Newly launched SKUs</CardTitle>
                <CardDescription>
                  These are treated differently, and told apart in the
                  interface.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <Row
                  label="Threshold"
                  value={`Under ${String(info.data.cold_start.threshold_days)} days of history`}
                />
                <Row
                  label="SKUs affected"
                  value={
                    (info.data.cold_start.skus as string[]).join(",") || "None"
                  }
                />
                <Row
                  label="Served by"
                  value={String(info.data.cold_start.serving_model)}
                />
                <ul className="list-disc space-y-1 pt-2 pl-4 text-xs leading-relaxed text-slate-500">
                  <li>
                    Weekly demand shape is shrunk toward the category average,
                    so a single observed Tuesday does not become a pattern.
                  </li>
                  <li>
                    Demand variability is shrunk toward the category median, so
                    the safety buffer is not built on twelve noisy days.
                  </li>
                  <li>
                    Uncertainty in the demand level itself is priced into the
                    stockout probability.
                  </li>
                  <li>
                    Lead time is replaced with the category median, because the
                    recorded values for these SKUs are inconsistent.
                  </li>
                  <li>
                    A simpler forecast is used, because it measurably beat the
                    main model on the cold-start validation fold.
                  </li>
                </ul>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Data behind the dashboard</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-x-8 gap-y-2 text-sm sm:grid-cols-2">
              {meta.data && (
                <>
                  <Row
                    label="Date range"
                    value={`${longDate(meta.data.date_range.start)} – ${longDate(meta.data.date_range.end)}`}
                  />
                  <Row
                    label="Rows after cleaning"
                    value={num(meta.data.row_count)}
                  />
                  <Row label="SKUs" value={num(meta.data.sku_count)} />
                  <Row label="Categories" value={meta.data.categories.length} />
                  <Row
                    label="Duplicate rows removed"
                    value={String(
                      meta.data.cleaning_report.exact_duplicates_dropped ?? "—",
                    )}
                  />
                  <Row
                    label="Missing demand values filled"
                    value={String(
                      meta.data.cleaning_report.demand_values_imputed ?? "—",
                    )}
                  />
                  <Row
                    label="Category labels normalised"
                    value={String(
                      meta.data.cleaning_report.category_case_normalised ?? "—",
                    )}
                  />
                  <Row
                    label="Days recorded at zero stock"
                    value={String(
                      meta.data.cleaning_report.observed_stockout_days ?? "—",
                    )}
                  />
                </>
              )}
              <Row
                label="Model trained"
                value={longDate(info.data.trained_at.slice(0, 10))}
              />
              <Row
                label="Forecast horizon"
                value={`${info.data.forecast_horizon_days} days`}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>What this tool cannot tell you</CardTitle>
              <CardDescription>
                Stated plainly, so the numbers are not over-trusted.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="list-disc space-y-2 pl-4 text-sm leading-relaxed text-slate-600">
                <li>
                  <span className="font-medium text-slate-900">
                    No open purchase orders.
                  </span>{" "}
                  The dataset records past deliveries only. Expected inbound is
                  inferred from each SKU&apos;s delivery pattern, not from a
                  live order book, so a confirmed order you know about is not
                  reflected.
                </li>
                <li>
                  <span className="font-medium text-slate-900">
                    Six months of history.
                  </span>{" "}
                  Weekly patterns are supported by the data; annual seasonality,
                  promotions and holiday effects are not.
                </li>
                <li>
                  <span className="font-medium text-slate-900">
                    Demand is recorded, not true, demand.
                  </span>{" "}
                  On days a SKU sat at zero stock, real customer demand may have
                  been higher than the sales figure shows.
                </li>
                <li>
                  <span className="font-medium text-slate-900">
                    No cost or margin data.
                  </span>{" "}
                  Risk is ranked by likelihood and by days of excess cover, not
                  by financial impact, so a high-value SKU is not prioritised
                  over a low-value one at equal risk.
                </li>
                <li>
                  <span className="font-medium text-slate-900">
                    Lead times are treated as fixed.
                  </span>{" "}
                  The safety buffer covers demand variability but not late
                  deliveries, so it is a lower bound.
                </li>
              </ul>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-slate-100 py-1.5 last:border-0">
      <span className="text-slate-500">{label}</span>
      <span className="text-right font-medium text-slate-900">{value}</span>
    </div>
  );
}

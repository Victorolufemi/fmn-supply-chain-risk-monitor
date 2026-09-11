"use client";

import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/primitives";
import { num, shortDate } from "@/lib/format";
import type { SkuDetail } from "@/types/api";

const AXIS = { fontSize: 11, fill: "currentColor" };
// Recharts takes literal colour strings, so these resolve through CSS custom
// properties defined in globals.css. Keeping them as tokens means the chart
// palette is edited in one place alongside the rest of the theme.
const GRID = "var(--chart-grid)";
const INK = "var(--chart-ink)";
// Area and bar fills are SVG gradients defined per chart in <defs>, so there is
// no flat-fill token for them.

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { name?: string; value?: number | string; color?: string }[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-lg">
      <p className="font-medium text-slate-900">{label}</p>
      {payload
        .filter((p) => p.value !== null && p.value !== undefined)
        .map((p) => (
          <p
            key={p.name}
            className="mt-0.5 flex items-center gap-1.5 text-slate-600"
          >
            <span
              className="h-2 w-2 rounded-sm"
              style={{ background: p.color }}
            />
            {p.name}:{" "}
            <span className="font-medium tabular-nums">
              {num(Number(p.value))}
            </span>
          </p>
        ))}
    </div>
  );
}

/**
 * Recent demand with the forecast continuing past the last observed day. One
 * continuous x-axis so the handover from actual to forecast is visible rather
 * than implied.
 */
export function DemandChart({ sku }: { sku: SkuDetail }) {
  const history = sku.history.slice(-60);
  const rows = [
    ...history.map((h) => ({
      date: h.date,
      label: shortDate(h.date),
      actual: h.units_sold,
      forecast: null as number | null,
    })),
    ...sku.forecast.map((f) => ({
      date: f.date,
      label: shortDate(f.date),
      actual: null as number | null,
      forecast: f.forecast_units,
    })),
  ];
  // Join the two series so the line does not visibly break at the boundary.
  const lastActual = history[history.length - 1];
  const boundary = rows.findIndex((r) => r.forecast !== null);
  if (boundary > 0 && lastActual)
    rows[boundary - 1].forecast = lastActual.units_sold;

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          Demand — last 60 days and {sku.forecast.length}-day forecast
        </CardTitle>
        <CardDescription>
          Solid line is recorded units sold. Dashed line is the model&apos;s
          forecast, which drives every risk figure on this page.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-[260px] text-slate-500">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart
              data={rows}
              margin={{ top: 8, right: 12, left: -18, bottom: 0 }}
            >
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis
                dataKey="label"
                tickLine={false}
                axisLine={false}
                tick={AXIS}
                minTickGap={28}
              />
              <YAxis tickLine={false} axisLine={false} tick={AXIS} />
              <Tooltip content={<ChartTooltip />} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {lastActual && (
                <ReferenceLine
                  x={shortDate(lastActual.date)}
                  stroke="#94a3b8"
                  strokeDasharray="3 3"
                  label={{ value: "today", position: "top", style: AXIS }}
                />
              )}
              <Line
                type="monotone"
                dataKey="actual"
                name="Units sold"
                stroke={INK}
                strokeWidth={1.6}
                dot={false}
                connectNulls={false}
              />
              <Line
                type="monotone"
                dataKey="forecast"
                name="Forecast"
                stroke="#2563eb"
                strokeWidth={1.8}
                strokeDasharray="5 4"
                dot={false}
                connectNulls={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * Stock level with deliveries, plus the two policy lines the risk logic uses.
 * Seeing stock cross the reorder point is the whole argument for acting.
 */
export function InventoryChart({ sku }: { sku: SkuDetail }) {
  const rows = sku.history.slice(-60).map((h) => ({
    label: shortDate(h.date),
    stock: h.closing_stock,
    received: h.units_received || null,
    stockout: h.is_stockout_day,
  }));

  // Recharts sizes the axis from the series alone, so a policy line above the
  // highest observed stock would be drawn off-chart — the caption would name a
  // line the reader cannot see. Extend the domain to cover both.
  const seriesMax = Math.max(
    0,
    ...rows.map((r) => Math.max(r.stock ?? 0, r.received ?? 0)),
  );
  const yMax =
    Math.max(
      seriesMax,
      sku.reorder_point_units ?? 0,
      sku.order_up_to_units ?? 0,
    ) * 1.08;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Inventory and deliveries — last 60 days</CardTitle>
        <CardDescription>
          Closing stock against the reorder point and the order-up-to level.
          Bars are goods received.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-[260px] text-slate-500">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart
              data={rows}
              margin={{ top: 8, right: 12, left: -18, bottom: 0 }}
            >
              {/* Gradient fills: the stock area fades out toward the baseline so
                  the line itself stays the readable edge, and delivery bars fade
                  downward so they sit behind the stock trace rather than on top
                  of it. */}
              <defs>
                <linearGradient id="stockFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#1e293b" stopOpacity={0.18} />
                  <stop offset="100%" stopColor="#1e293b" stopOpacity={0.01} />
                </linearGradient>
                <linearGradient id="receivedFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.95} />
                  <stop offset="100%" stopColor="#93c5fd" stopOpacity={0.55} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis
                dataKey="label"
                tickLine={false}
                axisLine={false}
                tick={AXIS}
                minTickGap={28}
              />
              <YAxis
                domain={[0, Math.ceil(yMax)]}
                tickLine={false}
                axisLine={false}
                tick={AXIS}
              />
              <Tooltip content={<ChartTooltip />} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar
                dataKey="received"
                name="Units received"
                fill="url(#receivedFill)"
                maxBarSize={10}
                radius={[2, 2, 0, 0]}
              />
              <Area
                type="stepAfter"
                dataKey="stock"
                name="Closing stock"
                stroke={INK}
                strokeWidth={1.6}
                fill="url(#stockFill)"
              />
              {sku.reorder_point_units !== null && (
                <ReferenceLine
                  y={sku.reorder_point_units}
                  stroke="#ea580c"
                  strokeDasharray="5 4"
                  label={{
                    value: "reorder point",
                    position: "insideTopRight",
                    style: AXIS,
                  }}
                />
              )}
              {sku.order_up_to_units !== null && (
                <ReferenceLine
                  y={sku.order_up_to_units}
                  stroke="#0284c7"
                  strokeDasharray="5 4"
                  label={{
                    value: "order-up-to",
                    position: "insideTopRight",
                    style: AXIS,
                  }}
                />
              )}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

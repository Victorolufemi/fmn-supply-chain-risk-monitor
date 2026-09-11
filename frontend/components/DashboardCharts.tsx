"use client";

import {
  Bar,
  BarChart,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
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
import { RISK_CHART_COLOR, RISK_LABEL, RISK_ORDER } from "@/lib/format";
import type { CategoryRisk, RiskCount, SkuSummary } from "@/types/api";

const AXIS = { fontSize: 11, fill: "currentColor" };

function TooltipBox({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-lg">
      {children}
    </div>
  );
}

/* ------------------------------------------------------------------ 1 ----- */
export function RiskDistributionChart({ data }: { data: RiskCount[] }) {
  const rows = RISK_ORDER.map((level) => ({
    level,
    label: RISK_LABEL[level],
    count: data.find((d) => d.level === level)?.count ?? 0,
  }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>Risk distribution</CardTitle>
        <CardDescription>
          How the portfolio splits across risk bands today.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-[220px] text-slate-500">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={rows}
              margin={{ top: 8, right: 8, left: -20, bottom: 0 }}
            >
              <XAxis
                dataKey="label"
                tickLine={false}
                axisLine={false}
                tick={AXIS}
              />
              <YAxis
                allowDecimals={false}
                tickLine={false}
                axisLine={false}
                tick={AXIS}
              />
              <Tooltip
                cursor={{ fill: "rgba(148,163,184,0.12)" }}
                content={({ active, payload }) =>
                  active && payload?.length ? (
                    <TooltipBox>
                      <p className="font-medium text-slate-900">
                        {payload[0].payload.label}
                      </p>
                      <p className="text-slate-600">{payload[0].value} SKUs</p>
                    </TooltipBox>
                  ) : null
                }
              />
              <Bar dataKey="count" radius={[4, 4, 0, 0]} maxBarSize={64}>
                {rows.map((r) => (
                  <Cell key={r.level} fill={RISK_CHART_COLOR[r.level]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------------ 2 ----- */
/**
 * Coverage against lead time. The single most decision-relevant view on the
 * dashboard: anything below the diagonal cannot be replenished before it runs
 * out, so the chart makes"needs an order today" a position on a page rather
 * than a number in a table.
 */
export function CoverageVsLeadTimeChart({ skus }: { skus: SkuSummary[] }) {
  const points = skus
    .filter((s) => s.inventory_coverage_days !== null)
    .map((s) => ({
      x: s.lead_time_days,
      y: Math.min(s.inventory_coverage_days as number, 30),
      clipped: (s.inventory_coverage_days as number) > 30,
      sku: s.sku_id,
      level: s.risk_level,
      coverage: s.inventory_coverage_days as number,
      category: s.category,
    }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>Inventory coverage vs lead time</CardTitle>
        <CardDescription>
          Points below the dashed line have less cover than it takes to restock
          — an order placed today would arrive too late.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-[220px] text-slate-500">
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 8, right: 12, left: -18, bottom: 4 }}>
              <XAxis
                type="number"
                dataKey="x"
                name="Lead time"
                domain={[0, 16]}
                tickLine={false}
                axisLine={false}
                tick={AXIS}
                label={{
                  value: "Lead time (days)",
                  position: "insideBottom",
                  offset: -2,
                  style: AXIS,
                }}
              />
              <YAxis
                type="number"
                dataKey="y"
                name="Coverage"
                domain={[0, 30]}
                tickLine={false}
                axisLine={false}
                tick={AXIS}
              />
              <ReferenceLine
                segment={[
                  { x: 0, y: 0 },
                  { x: 16, y: 16 },
                ]}
                stroke="#94a3b8"
                strokeDasharray="4 4"
              />
              <Tooltip
                cursor={{ strokeDasharray: "3 3" }}
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const p = payload[0].payload;
                  return (
                    <TooltipBox>
                      <p className="font-medium text-slate-900">{p.sku}</p>
                      <p className="text-slate-600">{p.category}</p>
                      <p className="mt-1 text-slate-600">
                        {p.coverage.toFixed(1)} days cover · {p.x} day lead time
                      </p>
                      <p className="text-slate-600">
                        {RISK_LABEL[p.level as keyof typeof RISK_LABEL]}
                      </p>
                    </TooltipBox>
                  );
                }}
              />
              <Scatter data={points}>
                {points.map((p) => (
                  <Cell
                    key={p.sku}
                    fill={RISK_CHART_COLOR[p.level]}
                    fillOpacity={0.85}
                  />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </div>
        <p className="mt-2 text-xs text-slate-400">
          Coverage is capped at 30 days for readability.
        </p>
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------------ 3 ----- */
export function CategoryRiskChart({ data }: { data: CategoryRisk[] }) {
  const rows = data.map((c) => ({
    category: c.category,
    atRisk: c.critical_high,
    rest: c.total - c.critical_high,
    total: c.total,
    stockout: c.stockout,
    overstock: c.overstock,
  }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>Risk by category</CardTitle>
        <CardDescription>
          Where high and critical SKUs are concentrated.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-[220px] text-slate-500">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={rows}
              layout="vertical"
              margin={{ top: 4, right: 12, left: 12, bottom: 0 }}
            >
              <XAxis
                type="number"
                allowDecimals={false}
                tickLine={false}
                axisLine={false}
                tick={AXIS}
              />
              <YAxis
                type="category"
                dataKey="category"
                width={72}
                tickLine={false}
                axisLine={false}
                tick={AXIS}
              />
              <Tooltip
                cursor={{ fill: "rgba(148,163,184,0.12)" }}
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const p = payload[0].payload;
                  return (
                    <TooltipBox>
                      <p className="font-medium text-slate-900">{p.category}</p>
                      <p className="text-slate-600">
                        {p.atRisk} of {p.total} SKUs at high or critical risk
                      </p>
                      <p className="text-slate-600">
                        {p.stockout} stockout · {p.overstock} overstock
                      </p>
                    </TooltipBox>
                  );
                }}
              />
              {/* The at-risk segment carries the critical gradient so it reads
                  as the same signal as the "Need attention" KPI tile. */}
              <defs>
                <linearGradient id="atRiskFill" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor="#e11d48" />
                  <stop offset="100%" stopColor="#f97316" />
                </linearGradient>
                <linearGradient id="restFill" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor="#e2e8f0" />
                  <stop offset="100%" stopColor="#cbd5e1" />
                </linearGradient>
              </defs>
              <Bar
                dataKey="atRisk"
                stackId="a"
                fill="url(#atRiskFill)"
                radius={[0, 0, 0, 0]}
                maxBarSize={22}
              />
              <Bar
                dataKey="rest"
                stackId="a"
                fill="url(#restFill)"
                radius={[0, 4, 4, 0]}
                maxBarSize={22}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-2 flex items-center gap-4 text-xs text-slate-500">
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-sm bg-rose-600" /> High or critical
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-sm bg-slate-300" /> Everything else
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

"use client";

import { Suspense, useCallback, useMemo, useState } from "react";
import { useSearchParams, type ReadonlyURLSearchParams } from "next/navigation";
import { RefreshCw, TriangleAlert } from "lucide-react";
import { AskPanel } from "@/components/AskPanel";
import {
  CategoryRiskChart,
  CoverageVsLeadTimeChart,
  RiskDistributionChart,
} from "@/components/DashboardCharts";
import {
  applyFilters,
  EMPTY_FILTERS,
  FilterBar,
  type Filters,
} from "@/components/FilterBar";
import { KpiCards } from "@/components/KpiCards";
import { SkuTable } from "@/components/SkuTable";
import {
  Badge,
  Button,
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/primitives";
import {
  ChartSkeleton,
  ErrorState,
  KpiSkeleton,
  TableSkeleton,
} from "@/components/ui/states";
import { api } from "@/lib/api";
import { longDate } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import type { RiskLevel, RiskType } from "@/types/api";

/**
 * Deep links from the KPI cards, e.g. /supply-chain?risk=CRITICAL,HIGH. Read once
 * as the initial filter state rather than synced through an effect — the query
 * string does not change while the user is on this page.
 */
function filtersFromParams(
  params: URLSearchParams | ReadonlyURLSearchParams,
): Filters {
  const risk = params.get("risk");
  const type = params.get("type");
  return {
    ...EMPTY_FILTERS,
    risk: risk
      ? risk.includes(",")
        ? "ATTENTION"
        : (risk as RiskLevel)
      : EMPTY_FILTERS.risk,
    type: (type as RiskType) ?? EMPTY_FILTERS.type,
  };
}

function DashboardInner() {
  const params = useSearchParams();
  const dashboard = useApi(() => api.dashboard(), []);
  const suggestions = useApi(() => api.qaSuggestions(), []);
  const [filters, setFilters] = useState<Filters>(() =>
    filtersFromParams(params),
  );

  const reset = useCallback(() => setFilters(EMPTY_FILTERS), []);
  const all = useMemo(
    () => dashboard.data?.attention_list ?? [],
    [dashboard.data],
  );
  const filtered = useMemo(() => applyFilters(all, filters), [all, filters]);
  const categories = useMemo(
    () => dashboard.data?.category_risk.map((c) => c.category) ?? [],
    [dashboard.data],
  );

  if (dashboard.error) {
    return (
      <div className="space-y-6">
        <Header />
        <ErrorState error={dashboard.error} onRetry={dashboard.reload} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Header
        asOf={dashboard.data?.as_of}
        model={dashboard.data?.model_name}
        onRefresh={dashboard.reload}
        loading={dashboard.loading}
      />

      {dashboard.data && !dashboard.data.llm_available && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p className="font-medium">AI explanations are unavailable</p>
            <p className="mt-0.5">
              No Anthropic API key is configured on the server. Risk scores,
              charts and figures are unaffected; written explanations fall back
              to a direct read-out of the same numbers and are labelled where
              they appear.
            </p>
          </div>
        </div>
      )}

      {dashboard.loading && !dashboard.data ? (
        <>
          <KpiSkeleton />
          <div className="grid gap-4 lg:grid-cols-3">
            <ChartSkeleton />
            <ChartSkeleton />
            <ChartSkeleton />
          </div>
        </>
      ) : (
        dashboard.data && (
          <>
            <KpiCards kpis={dashboard.data.kpis} />
            <div className="grid gap-4 lg:grid-cols-3">
              <CoverageVsLeadTimeChart skus={all} />
              <RiskDistributionChart data={dashboard.data.risk_distribution} />
              <CategoryRiskChart data={dashboard.data.category_risk} />
            </div>
          </>
        )
      )}

      <AskPanel suggestions={suggestions.data ?? undefined} />

      <Card>
        <CardHeader className="pb-0">
          <CardTitle className="text-base">SKUs requiring attention</CardTitle>
          <CardDescription>
            Ranked by severity, then by how soon stock is projected to run out.
            Click a SKU for the full picture.
          </CardDescription>
        </CardHeader>
        <div className="mt-4">
          <FilterBar
            filters={filters}
            categories={categories}
            onChange={setFilters}
            onReset={reset}
            resultCount={filtered.length}
            totalCount={all.length}
          />
          {dashboard.loading && !dashboard.data ? (
            <TableSkeleton />
          ) : (
            <SkuTable skus={filtered} onClear={reset} />
          )}
        </div>
      </Card>
    </div>
  );
}

function Header({
  asOf,
  model,
  onRefresh,
  loading,
}: {
  asOf?: string;
  model?: string;
  onRefresh?: () => void;
  loading?: boolean;
}) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <h1 className="text-gradient inline-block text-2xl font-semibold tracking-tight">
          Supply Chain Risk Monitor
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Identify SKUs likely to require attention before inventory becomes a
          problem.
        </p>
      </div>
      <div className="flex items-center gap-2">
        {asOf && <Badge variant="outline">Data as of {longDate(asOf)}</Badge>}
        {model && (
          <Badge variant="outline" title={`Serving model: ${model}`}>
            {model.startsWith("cold_start_router") ? "Routed model" : model}
          </Badge>
        )}
        {onRefresh && (
          <Button
            variant="outline"
            size="sm"
            onClick={onRefresh}
            disabled={loading}
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`}
            />
            Refresh
          </Button>
        )}
      </div>
    </div>
  );
}

export default function SupplyChainPage() {
  return (
    <Suspense fallback={<KpiSkeleton />}>
      <DashboardInner />
    </Suspense>
  );
}

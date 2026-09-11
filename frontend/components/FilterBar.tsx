"use client";

import { Search, X } from "lucide-react";
import { Button, Input, Select } from "@/components/ui/primitives";
import { RISK_LABEL, RISK_ORDER } from "@/lib/format";
import type { RiskLevel, RiskType } from "@/types/api";

export interface Filters {
  risk: RiskLevel | "ALL" | "ATTENTION";
  type: RiskType | "ALL";
  category: string;
  cohort: "ALL" | "NEW" | "ESTABLISHED";
  search: string;
}

export const EMPTY_FILTERS: Filters = {
  risk: "ALL",
  type: "ALL",
  category: "ALL",
  cohort: "ALL",
  search: "",
};

export function isFiltered(f: Filters): boolean {
  return (
    f.risk !== "ALL" ||
    f.type !== "ALL" ||
    f.category !== "ALL" ||
    f.cohort !== "ALL" ||
    f.search.trim() !== ""
  );
}

/** Applied client-side: the full list is 28 rows, so a round trip per keystroke
 * would add latency without adding correctness. */
interface Filterable {
  risk_level: RiskLevel;
  risk_type: RiskType;
  category: string;
  is_cold_start: boolean;
  sku_id: string;
}

export function applyFilters<T extends Filterable>(rows: T[], f: Filters): T[] {
  return rows.filter((r) => {
    if (f.risk === "ATTENTION" && r.risk_level === "HEALTHY") return false;
    if (f.risk !== "ALL" && f.risk !== "ATTENTION" && r.risk_level !== f.risk)
      return false;
    if (f.type !== "ALL" && r.risk_type !== f.type) return false;
    if (f.category !== "ALL" && r.category !== f.category) return false;
    if (f.cohort === "NEW" && !r.is_cold_start) return false;
    if (f.cohort === "ESTABLISHED" && r.is_cold_start) return false;
    const q = f.search.trim().toLowerCase();
    if (
      q &&
      !r.sku_id.toLowerCase().includes(q) &&
      !r.category.toLowerCase().includes(q)
    )
      return false;
    return true;
  });
}

export function FilterBar({
  filters,
  categories,
  onChange,
  onReset,
  resultCount,
  totalCount,
}: {
  filters: Filters;
  categories: string[];
  onChange: (f: Filters) => void;
  onReset: () => void;
  resultCount: number;
  totalCount: number;
}) {
  const set = <K extends keyof Filters>(key: K, value: Filters[K]) =>
    onChange({ ...filters, [key]: value });

  return (
    <div className="flex flex-col gap-3 border-b border-slate-200 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
          <Input
            value={filters.search}
            onChange={(e) => set("search", e.target.value)}
            placeholder="Search SKU or category"
            aria-label="Search SKU or category"
            className="w-56 pl-8"
          />
        </div>

        <Select
          value={filters.risk}
          onChange={(e) => set("risk", e.target.value as Filters["risk"])}
          aria-label="Filter by risk level"
        >
          <option value="ALL">All risk levels</option>
          <option value="ATTENTION">Needs attention</option>
          {RISK_ORDER.map((l) => (
            <option key={l} value={l}>
              {RISK_LABEL[l]}
            </option>
          ))}
        </Select>

        <Select
          value={filters.type}
          onChange={(e) => set("type", e.target.value as Filters["type"])}
          aria-label="Filter by risk type"
        >
          <option value="ALL">All risk types</option>
          <option value="STOCKOUT">Stockout</option>
          <option value="OVERSTOCK">Overstock</option>
          <option value="NONE">No flag</option>
        </Select>

        <Select
          value={filters.category}
          onChange={(e) => set("category", e.target.value)}
          aria-label="Filter by category"
        >
          <option value="ALL">All categories</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </Select>

        <Select
          value={filters.cohort}
          onChange={(e) => set("cohort", e.target.value as Filters["cohort"])}
          aria-label="Filter by SKU age"
        >
          <option value="ALL">New &amp; established</option>
          <option value="NEW">Newly launched only</option>
          <option value="ESTABLISHED">Established only</option>
        </Select>

        {isFiltered(filters) && (
          <Button variant="ghost" size="sm" onClick={onReset}>
            <X className="h-3.5 w-3.5" />
            Clear
          </Button>
        )}
      </div>

      <p className="shrink-0 text-xs text-slate-500">
        Showing <span className="font-medium tabular-nums">{resultCount}</span>{" "}
        of <span className="tabular-nums">{totalCount}</span> SKUs
      </p>
    </div>
  );
}

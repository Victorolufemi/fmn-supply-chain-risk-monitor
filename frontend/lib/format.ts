/** Presentation helpers. No business rules here — only formatting and labels. */
import type { Confidence, RiskLevel, RiskType } from "@/types/api";

export function num(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return v.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function days(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `${num(v, digits)}d`;
}

export function pct(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `${v > 0 ? "+" : ""}${num(v, digits)}%`;
}

export function probability(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `${Math.round(v * 100)}%`;
}

export function shortDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

export function longDate(iso: string): string {
  const d = new Date(iso.length > 10 ? iso : `${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/**
 * Badge styling per risk level. Deliberately restrained: one accent colour per
 * severity on a tinted background, so a table of 28 rows stays scannable instead
 * of turning into a traffic-light wall.
 */
export const RISK_STYLES: Record<RiskLevel, string> = {
  CRITICAL: "bg-rose-50 text-rose-700 ring-rose-600/20",
  HIGH: "bg-orange-50 text-orange-700 ring-orange-600/20",
  MEDIUM: "bg-amber-50 text-amber-800 ring-amber-600/20",
  LOW: "bg-sky-50 text-sky-700 ring-sky-600/20",
  HEALTHY: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
};

export const RISK_CHART_COLOR: Record<RiskLevel, string> = {
  CRITICAL: "#e11d48",
  HIGH: "#ea580c",
  MEDIUM: "#d97706",
  LOW: "#0284c7",
  HEALTHY: "#059669",
};

export const RISK_LABEL: Record<RiskLevel, string> = {
  CRITICAL: "Critical",
  HIGH: "High",
  MEDIUM: "Medium",
  LOW: "Low",
  HEALTHY: "Healthy",
};

export const RISK_TYPE_LABEL: Record<RiskType, string> = {
  STOCKOUT: "Stockout",
  OVERSTOCK: "Overstock",
  NONE: "—",
};

export const CONFIDENCE_LABEL: Record<Confidence, string> = {
  HIGH: "High confidence",
  MEDIUM: "Medium confidence",
  LOW: "Limited history",
};

export const RISK_ORDER: RiskLevel[] = [
  "CRITICAL",
  "HIGH",
  "MEDIUM",
  "LOW",
  "HEALTHY",
];

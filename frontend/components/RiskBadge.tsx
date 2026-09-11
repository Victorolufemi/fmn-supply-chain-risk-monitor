"use client";

import {
  AlertOctagon,
  ArrowDownCircle,
  ArrowUpCircle,
  Clock,
  Minus,
} from "lucide-react";
import { Badge } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";
import { RISK_LABEL, RISK_STYLES, RISK_TYPE_LABEL } from "@/lib/format";
import type { RiskLevel, RiskType } from "@/types/api";

export function RiskBadge({
  level,
  className,
}: {
  level: RiskLevel;
  className?: string;
}) {
  return (
    <Badge className={cn(RISK_STYLES[level], className)}>
      {level === "CRITICAL" && <AlertOctagon className="h-3 w-3" />}
      {RISK_LABEL[level]}
    </Badge>
  );
}

export function RiskTypeBadge({ type }: { type: RiskType }) {
  if (type === "NONE") {
    return <span className="text-slate-400">—</span>;
  }
  return (
    <Badge variant="outline">
      {type === "STOCKOUT" ? (
        <ArrowDownCircle className="h-3 w-3" />
      ) : (
        <ArrowUpCircle className="h-3 w-3" />
      )}
      {RISK_TYPE_LABEL[type]}
    </Badge>
  );
}

/** Shown wherever a cold-start SKU appears, so limited history is never implicit. */
export function NewSkuBadge({ days }: { days: number }) {
  return (
    <Badge
      className="bg-violet-50 text-violet-700 ring-violet-600/20"
      title={`Only ${days} days of observed demand — estimates are less certain than for established SKUs.`}
    >
      <Clock className="h-3 w-3" />
      New · {days}d
    </Badge>
  );
}

export function UndersuppliedBadge({ ratio }: { ratio: number | null }) {
  return (
    <Badge
      variant="outline"
      title={
        ratio !== null
          ? `Only ${Math.round(ratio * 100)} units received for every 100 sold over the last 56 days.`
          : "Receiving less than is being sold."
      }
    >
      <Minus className="h-3 w-3" />
      Under-supplied
    </Badge>
  );
}

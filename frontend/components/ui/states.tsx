/** Loading, empty and error states. No screen is ever allowed to render blank. */
"use client";

import { AlertTriangle, Inbox, RefreshCw, WifiOff } from "lucide-react";
import { Button, Card, Skeleton } from "@/components/ui/primitives";
import { ApiError } from "@/lib/api";

export function ErrorState({
  error,
  onRetry,
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  className?: string;
}) {
  const isNetwork = error instanceof ApiError && error.isNetwork;
  const message =
    error instanceof Error
      ? error.message
      : "Something went wrong loading this view.";

  return (
    <Card className={className}>
      <div className="flex flex-col items-center gap-3 px-6 py-10 text-center">
        <div className="rounded-full bg-rose-50 p-3">
          {isNetwork ? (
            <WifiOff className="h-5 w-5 text-rose-600" />
          ) : (
            <AlertTriangle className="h-5 w-5 text-rose-600" />
          )}
        </div>
        <div>
          <p className="text-sm font-semibold text-slate-900">
            {isNetwork
              ? "Cannot reach the service"
              : "Could not load this data"}
          </p>
          <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">
            {message}
          </p>
        </div>
        {onRetry && (
          <Button variant="outline" size="sm" onClick={onRetry}>
            <RefreshCw className="h-3.5 w-3.5" />
            Try again
          </Button>
        )}
      </div>
    </Card>
  );
}

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-14 text-center">
      <div className="rounded-full bg-slate-100 p-3">
        <Inbox className="h-5 w-5 text-slate-400" />
      </div>
      <div>
        <p className="text-sm font-semibold text-slate-900">{title}</p>
        {hint && (
          <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">{hint}</p>
        )}
      </div>
      {action}
    </div>
  );
}

export function KpiSkeleton() {
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <Card key={i} className="p-5">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="mt-3 h-8 w-16" />
          <Skeleton className="mt-3 h-3 w-32" />
        </Card>
      ))}
    </div>
  );
}

export function TableSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div className="space-y-2 p-5">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-4">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-4 w-20" />
          <Skeleton className="h-5 w-16 rounded-md" />
          <Skeleton className="h-4 flex-1" />
        </div>
      ))}
    </div>
  );
}

export function ChartSkeleton({ height = 240 }: { height?: number }) {
  return <Skeleton className="w-full" style={{ height }} />;
}

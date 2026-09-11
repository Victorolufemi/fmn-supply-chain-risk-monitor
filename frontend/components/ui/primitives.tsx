/**
 * shadcn/ui-style primitives.
 *
 * shadcn is a copy-in component set rather than a dependency, so these live in
 * the repo and follow its conventions (Radix-free where no behaviour is needed,
 * `cn()` for class merging, variants via class-variance-authority). Keeping them
 * in one file avoids twelve near-empty modules for a dashboard this size.
 */
"use client";

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/* ---------------------------------------------------------------- Card ---- */
export function Card({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        // `surface-gradient` is a barely-there vertical wash, so stacked cards
        // read as distinct planes against the gradient page without needing
        // heavier borders or shadows.
        "surface-gradient rounded-xl border border-slate-200/80 shadow-sm shadow-slate-200/50",
        className,
      )}
      {...props}
    />
  );
}

export function CardHeader({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("flex flex-col gap-1 p-5 pb-3", className)} {...props} />
  );
}

export function CardTitle({
  className,
  ...props
}: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3
      className={cn("text-sm font-semibold text-slate-900", className)}
      {...props}
    />
  );
}

export function CardDescription({
  className,
  ...props
}: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("text-sm text-slate-500", className)} {...props} />;
}

export function CardContent({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-5 pt-0", className)} {...props} />;
}

/* --------------------------------------------------------------- Badge ---- */
const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset whitespace-nowrap",
  {
    variants: {
      variant: {
        default: "bg-white/70 text-slate-700 ring-slate-300/70",
        outline: "bg-white/60 text-slate-600 ring-slate-300",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps
  extends
    React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

/* -------------------------------------------------------------- Button ---- */
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-lg text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        // The primary action is the only gradient control on a screen, so it
        // stays unambiguous as "the thing to press".
        default:
          "grad-brand text-white shadow-sm shadow-indigo-500/25 hover:shadow-md hover:shadow-indigo-500/30 hover:brightness-110",
        outline:
          "border border-slate-300 bg-white/80 text-slate-700 hover:border-slate-400 hover:bg-white",
        ghost: "text-slate-600 hover:bg-slate-100/80 hover:text-slate-900",
        subtle: "bg-slate-100 text-slate-700 hover:bg-slate-200",
      },
      size: {
        default: "h-9 px-4",
        sm: "h-8 px-3 text-xs",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends
    React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  ),
);
Button.displayName = "Button";

/* --------------------------------------------------------------- Input ---- */
export const Input = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ className, ...props }, ref) => (
  <input
    ref={ref}
    className={cn(
      "h-9 w-full rounded-lg border border-slate-300 bg-white/90 px-3 text-sm text-slate-900 placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-200",
      className,
    )}
    {...props}
  />
));
Input.displayName = "Input";

/* -------------------------------------------------------------- Select ---- */
export const Select = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement>
>(({ className, ...props }, ref) => (
  <select
    ref={ref}
    className={cn(
      "h-9 rounded-lg border border-slate-300 bg-white/90 px-2.5 text-sm text-slate-700 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-200",
      className,
    )}
    {...props}
  />
));
Select.displayName = "Select";

/* ------------------------------------------------------------ Skeleton ---- */
export function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "animate-pulse rounded-md bg-gradient-to-r from-slate-200 via-slate-100 to-slate-200",
        className,
      )}
      {...props}
    />
  );
}

/* ------------------------------------------------------------- Tooltip ---- */
/** Hover/focus hint. Native `title` is unreliable for long copy, so this is a
 *  small positioned popover that also opens on keyboard focus. */
export function InfoTip({
  text,
  className,
}: {
  text: string;
  className?: string;
}) {
  return (
    <span className={cn("group relative inline-flex", className)}>
      <button
        type="button"
        aria-label={text}
        className="flex h-4 w-4 items-center justify-center rounded-full border border-slate-300 text-[10px] font-semibold text-slate-500 hover:border-slate-400 hover:text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-300"
      >
        i
      </button>
      {/* `role="tooltip"` also carries a viewport-clamped max-width from
          globals.css, so a hint near the right edge cannot widen the page. */}
      <span
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-1/2 z-30 mb-2 w-64 -translate-x-1/2 rounded-lg bg-slate-900 px-3 py-2 text-xs leading-relaxed text-white opacity-0 shadow-lg transition-opacity group-hover:opacity-100 group-focus-within:opacity-100"
      >
        {text}
      </span>
    </span>
  );
}

import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

type Tone = "neutral" | "brand" | "success" | "warning" | "danger" | "info";

const tones: Record<Tone, string> = {
  neutral: "bg-surface-muted text-ink-muted",
  brand: "bg-brand-soft text-brand",
  success: "bg-success-soft text-success",
  warning: "bg-warning-soft text-warning",
  danger: "bg-danger-soft text-danger",
  info: "bg-info-soft text-info",
};

/** Small, restrained status label. Colour is never the only carrier of meaning: text is always present. */
export function Tag({
  tone = "neutral",
  children,
  className,
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded px-1.5 py-0.5 text-2xs font-medium",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function toneForStatus(status: string | null | undefined): Tone {
  switch (status) {
    case "running":
    case "in_progress":
    case "in_review":
      return "info";
    case "completed":
    case "met":
    case "reviewed":
    case "nominal":
      return "success";
    case "paused":
    case "attempted":
    case "follow_up":
    case "degraded":
      return "warning";
    case "aborted":
    case "not_met":
    case "cancelled":
      return "danger";
    default:
      return "neutral";
  }
}

export function Alert({
  tone = "info",
  title,
  children,
  className,
}: {
  tone?: Exclude<Tone, "neutral" | "brand">;
  title?: string;
  children?: ReactNode;
  className?: string;
}) {
  const border = {
    info: "border-info/30",
    success: "border-success/30",
    warning: "border-warning/30",
    danger: "border-danger/30",
  }[tone];
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={cn("rounded border px-3 py-2 text-sm", tones[tone], border, className)}
    >
      {title ? <p className="font-medium">{title}</p> : null}
      {children ? <div className={cn(title && "mt-0.5", "text-ink")}>{children}</div> : null}
    </div>
  );
}

export function ScoreBar({ value, label }: { value: number | null; label: string }) {
  const pct = value === null ? 0 : Math.max(0, Math.min(100, value));
  return (
    <div
      className="h-1.5 w-full rounded-full bg-surface-muted"
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={value ?? undefined}
    >
      <div className="h-1.5 rounded-full bg-brand" style={{ width: `${pct}%` }} />
    </div>
  );
}

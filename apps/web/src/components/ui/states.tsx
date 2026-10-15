import type { ReactNode } from "react";

import { errorMessage } from "@/lib/useAsync";

import { Button } from "./button";

export function LoadingState({ label = "Loading", rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div role="status" aria-live="polite" className="space-y-2 p-4">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="h-4 animate-pulse rounded bg-surface-muted"
          style={{ width: `${90 - i * 12}%` }}
        />
      ))}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  title = "Could not load this information",
}: {
  error: unknown;
  onRetry?: () => void;
  title?: string;
}) {
  return (
    <div role="alert" className="flex flex-col items-start gap-2 p-4">
      <p className="text-sm font-medium text-danger">{title}</p>
      <p className="text-sm text-ink-muted">{errorMessage(error)}</p>
      {onRetry ? (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Retry
        </Button>
      ) : null}
    </div>
  );
}

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-start gap-1 px-4 py-6">
      <p className="text-sm font-medium text-ink">{title}</p>
      {children ? <div className="max-w-xl text-sm text-ink-muted">{children}</div> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

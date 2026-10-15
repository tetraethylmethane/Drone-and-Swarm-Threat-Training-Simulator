export function formatClock(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export function formatSeconds(s: number | null | undefined, digits = 1): string {
  if (s === null || s === undefined) return "—";
  return `${s.toFixed(digits)} s`;
}

export function formatPercent(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined) return "n/a";
  return `${v.toFixed(digits)}%`;
}

const dateFmt = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
const dayFmt = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return dateFmt.format(new Date(iso));
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return dayFmt.format(new Date(iso));
}

export function formatDistance(m: number | null | undefined): string {
  if (m === null || m === undefined) return "—";
  return m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${Math.round(m)} m`;
}

export function shortId(id: string): string {
  return id.slice(0, 8);
}

import type { Job } from "./types";

/**
 * Returns the date the role was actually posted, parsing posted_at when
 * possible, otherwise falling back to first_seen (when the watcher saw it).
 */
export function effectivePostedDate(job: Job): Date {
  if (job.posted_at) {
    const t = Date.parse(job.posted_at);
    if (!isNaN(t)) return new Date(t);
  }
  return new Date(job.first_seen);
}

export type PostedWithin = "any" | "24h" | "7d" | "30d" | "90d";

export const POSTED_WITHIN_OPTIONS: { value: PostedWithin; label: string; hours: number | null }[] = [
  { value: "any", label: "Any time", hours: null },
  { value: "24h", label: "Last 24h", hours: 24 },
  { value: "7d", label: "Last 7 days", hours: 24 * 7 },
  { value: "30d", label: "Last 30 days", hours: 24 * 30 },
  { value: "90d", label: "Last 90 days", hours: 24 * 90 },
];

export function withinWindow(job: Job, window: PostedWithin): boolean {
  const opt = POSTED_WITHIN_OPTIONS.find((o) => o.value === window);
  if (!opt || opt.hours === null) return true;
  const cutoff = Date.now() - opt.hours * 60 * 60 * 1000;
  return effectivePostedDate(job).getTime() >= cutoff;
}

export function formatRelative(d: Date): string {
  const now = Date.now();
  const diffMs = now - d.getTime();
  if (diffMs < 0) return d.toLocaleDateString();
  const mins = diffMs / 60000;
  if (mins < 60) return `${Math.floor(mins)}m ago`;
  const hrs = mins / 60;
  if (hrs < 24) return `${Math.floor(hrs)}h ago`;
  const days = hrs / 24;
  if (days < 7) return `${Math.floor(days)}d ago`;
  if (days < 30) return `${Math.floor(days / 7)}w ago`;
  return d.toLocaleDateString();
}

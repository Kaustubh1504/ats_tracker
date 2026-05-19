"use client";

import { Job } from "@/lib/types";

export function StatsBar({ jobs }: { jobs: Job[] }) {
  const total = jobs.length;
  const byStatus = (s: string) => jobs.filter((j) => j.status === s).length;

  const now = Date.now();
  const oneDayAgo = now - 24 * 60 * 60 * 1000;
  const newToday = jobs.filter((j) => new Date(j.first_seen).getTime() > oneDayAgo).length;

  const cards: { label: string; value: number; tone?: string }[] = [
    { label: "Total", value: total },
    { label: "New (24h)", value: newToday, tone: "text-blue-600" },
    { label: "Interested", value: byStatus("interested"), tone: "text-amber-600" },
    { label: "Applied", value: byStatus("applied"), tone: "text-violet-600" },
    { label: "Interview", value: byStatus("interview"), tone: "text-fuchsia-600" },
    { label: "Offers", value: byStatus("offer"), tone: "text-emerald-600" },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-5">
      {cards.map((c) => (
        <div
          key={c.label}
          className="rounded-lg border border-[var(--border)] bg-[var(--card)] p-3"
        >
          <div className="text-xs text-[var(--muted)] uppercase tracking-wide">
            {c.label}
          </div>
          <div className={`text-2xl font-semibold mt-0.5 ${c.tone ?? ""}`}>
            {c.value.toLocaleString()}
          </div>
        </div>
      ))}
    </div>
  );
}

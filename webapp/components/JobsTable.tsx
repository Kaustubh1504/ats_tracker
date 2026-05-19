"use client";

import { useState } from "react";
import { Job, JobStatus, STATUSES, STATUS_COLORS, PRIORITY_COMPANIES } from "@/lib/types";
import { effectivePostedDate, formatRelative } from "@/lib/dates";
import { SortKey, SortDir } from "./Dashboard";
import { ChevronDown, ChevronUp, Star, ExternalLink, NotebookPen } from "lucide-react";

const SORT_HEADERS: { key: SortKey; label: string }[] = [
  { key: "posted", label: "Posted" },
  { key: "company", label: "Company" },
  { key: "title", label: "Title" },
  { key: "status", label: "Status" },
];

export function JobsTable({
  jobs,
  sortKey,
  sortDir,
  onSort,
  onStatus,
  onPriority,
  onNotes,
}: {
  jobs: Job[];
  sortKey: SortKey;
  sortDir: SortDir;
  onSort: (k: SortKey) => void;
  onStatus: (id: string, s: JobStatus) => void;
  onPriority: (id: string, current: boolean) => void;
  onNotes: (id: string, n: string) => void;
}) {
  if (jobs.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-[var(--border)] p-10 text-center text-[var(--muted)]">
        Nothing matches your filters.
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--card)] overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs uppercase tracking-wide text-[var(--muted)] bg-black/[0.02] dark:bg-white/[0.02]">
            <tr>
              <th className="w-8 px-3 py-2"></th>
              {SORT_HEADERS.map((h) => {
                const active = sortKey === h.key;
                return (
                  <th
                    key={h.key}
                    className="text-left px-3 py-2 cursor-pointer select-none"
                    onClick={() => onSort(h.key)}
                  >
                    <span className="inline-flex items-center gap-1">
                      {h.label}
                      {active &&
                        (sortDir === "asc" ? (
                          <ChevronUp className="w-3 h-3" />
                        ) : (
                          <ChevronDown className="w-3 h-3" />
                        ))}
                    </span>
                  </th>
                );
              })}
              <th className="text-left px-3 py-2">Location</th>
              <th className="text-left px-3 py-2">Source</th>
              <th className="text-left px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <JobRow
                key={job.id}
                job={job}
                onStatus={onStatus}
                onPriority={onPriority}
                onNotes={onNotes}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function JobRow({
  job,
  onStatus,
  onPriority,
  onNotes,
}: {
  job: Job;
  onStatus: (id: string, s: JobStatus) => void;
  onPriority: (id: string, current: boolean) => void;
  onNotes: (id: string, n: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [notes, setNotes] = useState(job.notes);
  const inferredPriority =
    job.priority || PRIORITY_COMPANIES.has(job.company.toLowerCase());

  return (
    <>
      <tr className="border-t border-[var(--border)] hover:bg-black/[0.02] dark:hover:bg-white/[0.02]">
        <td className="px-3 py-2">
          <button
            onClick={() => onPriority(job.id, job.priority)}
            title={job.priority ? "Unstar" : "Star"}
          >
            <Star
              className={`w-4 h-4 ${
                inferredPriority
                  ? "fill-yellow-400 text-yellow-400"
                  : "text-[var(--muted)] hover:text-yellow-500"
              }`}
            />
          </button>
        </td>
        <td
          className="px-3 py-2 whitespace-nowrap text-[var(--muted)] text-xs"
          title={`posted_at: ${job.posted_at ?? "—"}\nfirst_seen: ${job.first_seen}`}
        >
          {formatRelative(effectivePostedDate(job))}
        </td>
        <td className="px-3 py-2 whitespace-nowrap font-medium">
          {job.company}
        </td>
        <td className="px-3 py-2">
          <div className="flex items-center gap-2">
            <span className="line-clamp-2">{job.title}</span>
            {job.apply_url && (
              <a
                href={job.apply_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[var(--accent)] hover:opacity-70"
                title="Open apply page"
              >
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            )}
          </div>
        </td>
        <td className="px-3 py-2">
          <select
            value={job.status}
            onChange={(e) => onStatus(job.id, e.target.value as JobStatus)}
            className={`text-xs px-2 py-0.5 rounded border ${STATUS_COLORS[job.status]}`}
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </td>
        <td className="px-3 py-2 text-[var(--muted)] text-xs max-w-[180px] truncate">
          {job.location ?? "—"}
        </td>
        <td className="px-3 py-2 text-xs text-[var(--muted)]">{job.source}</td>
        <td className="px-3 py-2">
          <button
            onClick={() => setExpanded((e) => !e)}
            className="text-[var(--muted)] hover:text-[var(--fg)]"
            title="Notes / details"
          >
            <NotebookPen className="w-4 h-4" />
          </button>
        </td>
      </tr>
      {expanded && (
        <tr className="border-t border-[var(--border)] bg-black/[0.015] dark:bg-white/[0.02]">
          <td colSpan={8} className="px-6 py-4">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div>
                <div className="text-xs uppercase tracking-wide text-[var(--muted)] mb-1">
                  Notes
                </div>
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  onBlur={() => {
                    if (notes !== job.notes) onNotes(job.id, notes);
                  }}
                  rows={4}
                  placeholder="applied via referral, deadline 9/30, etc."
                  className="w-full px-2 py-1.5 rounded-md border border-[var(--border)] bg-transparent text-sm"
                />
                <div className="flex flex-wrap gap-2 mt-2 text-xs text-[var(--muted)]">
                  {job.salary_summary && <span>💰 {job.salary_summary}</span>}
                  {job.ats_type && <span>ATS: {job.ats_type}</span>}
                  {job.is_remote && <span>🏠 Remote</span>}
                  {job.posted_at && <span>posted: {job.posted_at}</span>}
                </div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wide text-[var(--muted)] mb-1">
                  Description
                </div>
                <div className="text-xs text-[var(--muted)] max-h-48 overflow-y-auto whitespace-pre-wrap leading-relaxed">
                  {job.description ?? "—"}
                </div>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}


"use client";

import { useMemo, useState, useTransition } from "react";
import { createClient } from "@/utils/supabase/client";
import { Job, JobStatus, STATUSES, STATUS_COLORS, PRIORITY_COMPANIES } from "@/lib/types";
import { effectivePostedDate, withinWindow, PostedWithin } from "@/lib/dates";
import { StatsBar } from "./StatsBar";
import { FiltersBar } from "./FiltersBar";
import { JobsTable } from "./JobsTable";

export type SortKey = "posted" | "company" | "title" | "status";
export type SortDir = "asc" | "desc";

export type Filters = {
  search: string;
  companies: string[];
  statuses: JobStatus[];
  source: "all" | "live" | "dataset";
  priorityOnly: boolean;
  hideSkipped: boolean;
  postedWithin: PostedWithin;
};

const DEFAULT_FILTERS: Filters = {
  search: "",
  companies: [],
  statuses: [],
  source: "all",
  priorityOnly: false,
  hideSkipped: true,
  postedWithin: "any",
};

export function Dashboard({ initialJobs }: { initialJobs: Job[] }) {
  const [jobs, setJobs] = useState<Job[]>(initialJobs);
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [sortKey, setSortKey] = useState<SortKey>("posted");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [, startTransition] = useTransition();
  const supabase = useMemo(() => createClient(), []);

  const allCompanies = useMemo(() => {
    const set = new Set<string>();
    jobs.forEach((j) => j.company && set.add(j.company));
    return Array.from(set).sort();
  }, [jobs]);

  const filtered = useMemo(() => {
    const search = filters.search.trim().toLowerCase();
    const companyFilter = new Set(filters.companies);
    const statusFilter = new Set(filters.statuses);

    let out = jobs.filter((j) => {
      if (filters.hideSkipped && j.status === "skip") return false;
      if (filters.priorityOnly && !j.priority && !PRIORITY_COMPANIES.has(j.company.toLowerCase()))
        return false;
      if (filters.source !== "all" && j.source !== filters.source) return false;
      if (companyFilter.size > 0 && !companyFilter.has(j.company)) return false;
      if (statusFilter.size > 0 && !statusFilter.has(j.status)) return false;
      if (!withinWindow(j, filters.postedWithin)) return false;
      if (search) {
        const hay = `${j.title} ${j.company} ${j.location ?? ""}`.toLowerCase();
        if (!hay.includes(search)) return false;
      }
      return true;
    });

    out = [...out].sort((a, b) => {
      const dir = sortDir === "asc" ? 1 : -1;
      if (sortKey === "posted") {
        return (effectivePostedDate(a).getTime() - effectivePostedDate(b).getTime()) * dir;
      }
      const ak = (a[sortKey] ?? "") as string;
      const bk = (b[sortKey] ?? "") as string;
      if (ak < bk) return -1 * dir;
      if (ak > bk) return 1 * dir;
      return 0;
    });

    return out;
  }, [jobs, filters, sortKey, sortDir]);

  const updateJob = (id: string, patch: Partial<Job>) => {
    setJobs((prev) => prev.map((j) => (j.id === id ? { ...j, ...patch } : j)));
    startTransition(async () => {
      const { error } = await supabase.from("jobs").update(patch).eq("id", id);
      if (error) {
        console.error("Update failed:", error);
      }
    });
  };

  const setStatus = (id: string, status: JobStatus) => updateJob(id, { status });
  const togglePriority = (id: string, current: boolean) =>
    updateJob(id, { priority: !current });
  const setNotes = (id: string, notes: string) => updateJob(id, { notes });

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "posted" ? "desc" : "asc");
    }
  };

  return (
    <main className="min-h-screen px-4 sm:px-6 lg:px-10 py-6 max-w-[1400px] mx-auto">
      <header className="mb-6 flex items-end justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">ATS Tracker</h1>
          <p className="text-sm text-[var(--muted)]">
            {jobs.length.toLocaleString()} total · {filtered.length.toLocaleString()} shown
          </p>
        </div>
      </header>

      <StatsBar jobs={jobs} />

      <FiltersBar
        filters={filters}
        setFilters={setFilters}
        allCompanies={allCompanies}
      />

      <JobsTable
        jobs={filtered}
        sortKey={sortKey}
        sortDir={sortDir}
        onSort={toggleSort}
        onStatus={setStatus}
        onPriority={togglePriority}
        onNotes={setNotes}
      />
    </main>
  );
}

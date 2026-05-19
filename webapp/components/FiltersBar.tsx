"use client";

import { useState } from "react";
import { Filters } from "./Dashboard";
import { JobStatus, STATUSES } from "@/lib/types";
import { POSTED_WITHIN_OPTIONS, PostedWithin } from "@/lib/dates";
import { Search, X } from "lucide-react";

export function FiltersBar({
  filters,
  setFilters,
  allCompanies,
}: {
  filters: Filters;
  setFilters: (f: Filters) => void;
  allCompanies: string[];
}) {
  const [companyOpen, setCompanyOpen] = useState(false);

  const toggleCompany = (c: string) => {
    const next = filters.companies.includes(c)
      ? filters.companies.filter((x) => x !== c)
      : [...filters.companies, c];
    setFilters({ ...filters, companies: next });
  };

  const toggleStatus = (s: JobStatus) => {
    const next = filters.statuses.includes(s)
      ? filters.statuses.filter((x) => x !== s)
      : [...filters.statuses, s];
    setFilters({ ...filters, statuses: next });
  };

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--card)] p-3 mb-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[260px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--muted)]" />
          <input
            type="text"
            value={filters.search}
            onChange={(e) => setFilters({ ...filters, search: e.target.value })}
            placeholder="Search title, company, location…"
            className="w-full pl-9 pr-3 py-2 rounded-md border border-[var(--border)] bg-transparent text-sm focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
          />
        </div>

        <select
          value={filters.postedWithin}
          onChange={(e) =>
            setFilters({ ...filters, postedWithin: e.target.value as PostedWithin })
          }
          className="px-3 py-2 rounded-md border border-[var(--border)] bg-transparent text-sm"
          title="Filter by date the role was posted"
        >
          {POSTED_WITHIN_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              Posted: {o.label}
            </option>
          ))}
        </select>

        <select
          value={filters.source}
          onChange={(e) =>
            setFilters({ ...filters, source: e.target.value as Filters["source"] })
          }
          className="px-3 py-2 rounded-md border border-[var(--border)] bg-transparent text-sm"
        >
          <option value="all">Any source</option>
          <option value="live">Live</option>
          <option value="dataset">Dataset</option>
        </select>

        <label className="flex items-center gap-2 text-sm px-3 py-2 rounded-md border border-[var(--border)] cursor-pointer select-none">
          <input
            type="checkbox"
            checked={filters.priorityOnly}
            onChange={(e) =>
              setFilters({ ...filters, priorityOnly: e.target.checked })
            }
          />
          ⭐ Priority only
        </label>

        <label className="flex items-center gap-2 text-sm px-3 py-2 rounded-md border border-[var(--border)] cursor-pointer select-none">
          <input
            type="checkbox"
            checked={filters.hideSkipped}
            onChange={(e) =>
              setFilters({ ...filters, hideSkipped: e.target.checked })
            }
          />
          Hide skipped
        </label>

        <button
          onClick={() =>
            setFilters({
              search: "",
              companies: [],
              statuses: [],
              source: "all",
              priorityOnly: false,
              hideSkipped: true,
              postedWithin: "any",
            })
          }
          className="px-3 py-2 rounded-md border border-[var(--border)] text-sm text-[var(--muted)] hover:text-[var(--fg)]"
        >
          Reset
        </button>
      </div>

      <div className="flex flex-wrap gap-1.5 mt-3">
        {STATUSES.map((s) => {
          const active = filters.statuses.includes(s);
          return (
            <button
              key={s}
              onClick={() => toggleStatus(s)}
              className={`px-2.5 py-1 rounded-full text-xs border transition ${
                active
                  ? "bg-[var(--accent)] text-white border-[var(--accent)]"
                  : "border-[var(--border)] text-[var(--muted)] hover:text-[var(--fg)]"
              }`}
            >
              {s}
            </button>
          );
        })}
      </div>

      <div className="mt-3">
        <button
          onClick={() => setCompanyOpen((o) => !o)}
          className="text-xs text-[var(--muted)] hover:text-[var(--fg)]"
        >
          {companyOpen ? "▾" : "▸"} Filter by company
          {filters.companies.length > 0 && (
            <span className="ml-2 text-[var(--accent)]">
              ({filters.companies.length})
            </span>
          )}
        </button>
        {companyOpen && (
          <div className="mt-2 max-h-56 overflow-y-auto border border-[var(--border)] rounded-md p-2 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-1">
            {allCompanies.map((c) => {
              const active = filters.companies.includes(c);
              return (
                <button
                  key={c}
                  onClick={() => toggleCompany(c)}
                  className={`text-left text-xs px-2 py-1 rounded ${
                    active
                      ? "bg-[var(--accent)] text-white"
                      : "hover:bg-[var(--border)]"
                  }`}
                >
                  {c}
                </button>
              );
            })}
          </div>
        )}

        {filters.companies.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            {filters.companies.map((c) => (
              <span
                key={c}
                className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-[var(--accent)] text-white"
              >
                {c}
                <button
                  onClick={() => toggleCompany(c)}
                  className="hover:opacity-80"
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

"use client";

import { useMemo, useState } from "react";
import type { SupabaseClient } from "@supabase/supabase-js";
import { RolesDoc } from "./SettingsEditor";
import { Save } from "lucide-react";

type SectionKey = "dataset_queries" | "title_patterns" | "intern_patterns" | "title_block_patterns";

const SECTIONS: { key: SectionKey; label: string; hint: string }[] = [
  {
    key: "dataset_queries",
    label: "Dataset queries",
    hint: "Free-text queries passed to jobhive.search() in the daily sweep. One per line.",
  },
  {
    key: "title_patterns",
    label: "Title patterns (positive)",
    hint: "Python regex — a job's title must match at least one. One regex per line. Use \\b for word boundaries.",
  },
  {
    key: "intern_patterns",
    label: "Intern patterns",
    hint: "Regex matched against title + description. One per line.",
  },
  {
    key: "title_block_patterns",
    label: "Title block patterns (negative)",
    hint: "Regex — if a job title matches any of these, it's rejected (e.g. \\bsales\\b, \\bph\\.?d\\b). One per line.",
  },
];

function toText(arr: string[] | undefined): string {
  return (arr || []).join("\n");
}

function fromText(s: string): string[] {
  return s
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.length > 0);
}

export function RolesEditor({
  initial,
  supabase,
  updatedAt,
}: {
  initial: RolesDoc;
  supabase: SupabaseClient;
  updatedAt: string | null;
}) {
  const [sections, setSections] = useState<Record<SectionKey, string>>({
    dataset_queries: toText(initial.dataset_queries),
    title_patterns: toText(initial.title_patterns),
    intern_patterns: toText(initial.intern_patterns),
    title_block_patterns: toText(initial.title_block_patterns),
  });
  const [country, setCountry] = useState(initial.country || "US");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastSaved, setLastSaved] = useState<string | null>(updatedAt);

  const regexErrors = useMemo(() => {
    const errs: Partial<Record<SectionKey, string>> = {};
    for (const s of SECTIONS) {
      if (s.key === "dataset_queries") continue;
      for (const line of fromText(sections[s.key])) {
        try {
          new RegExp(line);
        } catch (e) {
          errs[s.key] = `Bad regex on "${line.slice(0, 40)}": ${(e as Error).message}`;
          break;
        }
      }
    }
    return errs;
  }, [sections]);

  const update = (k: SectionKey, v: string) => {
    setSections({ ...sections, [k]: v });
    setDirty(true);
  };

  const save = async () => {
    if (Object.keys(regexErrors).length > 0) {
      setError("Fix regex errors before saving.");
      return;
    }
    setSaving(true);
    setError(null);
    const payload: RolesDoc = {
      _comment: initial._comment,
      dataset_queries: fromText(sections.dataset_queries),
      title_patterns: fromText(sections.title_patterns),
      intern_patterns: fromText(sections.intern_patterns),
      title_block_patterns: fromText(sections.title_block_patterns),
      country: country.trim().toUpperCase() || "US",
    };
    const { error } = await supabase
      .from("app_config")
      .upsert({ id: "roles", data: payload }, { onConflict: "id" });
    setSaving(false);
    if (error) {
      setError(error.message);
      return;
    }
    setDirty(false);
    setLastSaved(new Date().toISOString());
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm">
          <span className="text-[var(--muted)] mr-2">Country:</span>
          <input
            value={country}
            onChange={(e) => {
              setCountry(e.target.value);
              setDirty(true);
            }}
            className="bg-transparent px-2 py-1 rounded border border-[var(--border)] text-sm w-16 font-mono uppercase"
            maxLength={3}
          />
        </label>

        <div className="ml-auto flex items-center gap-2">
          {lastSaved && !dirty && (
            <span className="text-xs text-[var(--muted)]">
              Saved {new Date(lastSaved).toLocaleString()}
            </span>
          )}
          <button
            onClick={save}
            disabled={!dirty || saving || Object.keys(regexErrors).length > 0}
            className={`inline-flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-md border ${
              dirty && Object.keys(regexErrors).length === 0
                ? "border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--accent)] hover:text-white"
                : "border-[var(--border)] text-[var(--muted)] cursor-not-allowed"
            }`}
          >
            <Save className="w-4 h-4" />
            {saving ? "Saving…" : dirty ? "Save changes" : "Saved"}
          </button>
        </div>
      </div>

      {error && (
        <div className="text-sm text-red-600 px-3 py-2 rounded-md bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900">
          {error}
        </div>
      )}

      {SECTIONS.map((s) => (
        <div key={s.key} className="rounded-lg border border-[var(--border)] bg-[var(--card)] p-4">
          <div className="flex items-center justify-between mb-1">
            <h3 className="text-sm font-semibold">{s.label}</h3>
            <span className="text-xs text-[var(--muted)]">
              {fromText(sections[s.key]).length} entries
            </span>
          </div>
          <p className="text-xs text-[var(--muted)] mb-2">{s.hint}</p>
          <textarea
            value={sections[s.key]}
            onChange={(e) => update(s.key, e.target.value)}
            rows={Math.min(20, Math.max(6, sections[s.key].split("\n").length + 1))}
            spellCheck={false}
            className="w-full font-mono text-xs px-3 py-2 rounded-md border border-[var(--border)] bg-transparent focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
          />
          {regexErrors[s.key] && (
            <div className="text-xs text-red-600 mt-1">{regexErrors[s.key]}</div>
          )}
        </div>
      ))}
    </div>
  );
}

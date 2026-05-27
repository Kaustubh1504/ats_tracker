"use client";

import { useMemo, useState } from "react";
import type { SupabaseClient } from "@supabase/supabase-js";
import { TargetsDoc } from "./SettingsEditor";
import { Trash2, Plus, Save } from "lucide-react";

const KNOWN_ATSES = [
  "greenhouse", "lever", "ashby", "workday", "smartrecruiters", "icims",
  "oracle", "successfactors", "taleo", "phenom", "workable", "rippling",
  "personio", "eightfold", "amazon", "apple", "google", "tiktok", "uber",
  "meta", "tesla",
];

export function TargetsEditor({
  initial,
  supabase,
  updatedAt,
}: {
  initial: TargetsDoc;
  supabase: SupabaseClient;
  updatedAt: string | null;
}) {
  const [targets, setTargets] = useState(initial.targets || []);
  const [filter, setFilter] = useState("");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastSaved, setLastSaved] = useState<string | null>(updatedAt);

  const filtered = useMemo(() => {
    if (!filter.trim()) return targets;
    const f = filter.toLowerCase();
    return targets.filter(
      (t) => t.ats.toLowerCase().includes(f) || t.slug.toLowerCase().includes(f),
    );
  }, [targets, filter]);

  const byAts = useMemo(() => {
    const out: Record<string, number> = {};
    targets.forEach((t) => (out[t.ats] = (out[t.ats] || 0) + 1));
    return out;
  }, [targets]);

  const update = (idx: number, patch: Partial<{ ats: string; slug: string }>) => {
    const next = [...targets];
    next[idx] = { ...next[idx], ...patch };
    setTargets(next);
    setDirty(true);
  };

  const remove = (idx: number) => {
    setTargets(targets.filter((_, i) => i !== idx));
    setDirty(true);
  };

  const add = () => {
    setTargets([{ ats: "greenhouse", slug: "" }, ...targets]);
    setDirty(true);
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    const payload: TargetsDoc = { targets };
    const { error } = await supabase
      .from("app_config")
      .upsert({ id: "targets", data: payload }, { onConflict: "id" });
    setSaving(false);
    if (error) {
      setError(error.message);
      return;
    }
    setDirty(false);
    setLastSaved(new Date().toISOString());
  };

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <button
          onClick={add}
          className="inline-flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-md bg-[var(--accent)] text-white hover:opacity-90"
        >
          <Plus className="w-4 h-4" /> Add target
        </button>
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter by ATS or slug…"
          className="flex-1 min-w-[200px] text-sm px-3 py-1.5 rounded-md border border-[var(--border)] bg-transparent"
        />
        <div className="text-xs text-[var(--muted)] hidden sm:block">
          {targets.length} total ·{" "}
          {Object.entries(byAts)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 4)
            .map(([k, v]) => `${k} ${v}`)
            .join(" · ")}
        </div>
        <button
          onClick={save}
          disabled={!dirty || saving}
          className={`inline-flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-md border ${
            dirty
              ? "border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--accent)] hover:text-white"
              : "border-[var(--border)] text-[var(--muted)] cursor-not-allowed"
          }`}
        >
          <Save className="w-4 h-4" />
          {saving ? "Saving…" : dirty ? "Save changes" : "Saved"}
        </button>
      </div>

      {error && (
        <div className="text-sm text-red-600 mb-2">Save failed: {error}</div>
      )}
      {lastSaved && !dirty && (
        <div className="text-xs text-[var(--muted)] mb-2">
          Last saved: {new Date(lastSaved).toLocaleString()}
        </div>
      )}

      <div className="rounded-lg border border-[var(--border)] bg-[var(--card)] overflow-hidden">
        <table className="w-full text-sm">
          <thead className="text-xs uppercase tracking-wide text-[var(--muted)] bg-black/[0.02] dark:bg-white/[0.02]">
            <tr>
              <th className="text-left px-3 py-2 w-44">ATS</th>
              <th className="text-left px-3 py-2">Slug</th>
              <th className="w-10 px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr>
                <td colSpan={3} className="px-3 py-6 text-center text-[var(--muted)]">
                  {targets.length === 0
                    ? "No targets yet. Click 'Add target' to start."
                    : "No targets match the filter."}
                </td>
              </tr>
            )}
            {filtered.map((t) => {
              const originalIdx = targets.indexOf(t);
              return (
                <tr
                  key={originalIdx}
                  className="border-t border-[var(--border)] hover:bg-black/[0.02] dark:hover:bg-white/[0.02]"
                >
                  <td className="px-2 py-1">
                    <input
                      list="known-atses"
                      value={t.ats}
                      onChange={(e) => update(originalIdx, { ats: e.target.value })}
                      className="w-full bg-transparent px-2 py-1 rounded border border-transparent hover:border-[var(--border)] focus:border-[var(--accent)] focus:outline-none text-sm"
                    />
                  </td>
                  <td className="px-2 py-1">
                    <input
                      value={t.slug}
                      onChange={(e) => update(originalIdx, { slug: e.target.value })}
                      placeholder={
                        t.ats === "workday"
                          ? "https://tenant.wd5.myworkdayjobs.com/Site"
                          : "company-slug"
                      }
                      className="w-full bg-transparent px-2 py-1 rounded border border-transparent hover:border-[var(--border)] focus:border-[var(--accent)] focus:outline-none text-sm font-mono"
                    />
                  </td>
                  <td className="px-2 py-1">
                    <button
                      onClick={() => remove(originalIdx)}
                      className="text-[var(--muted)] hover:text-red-600"
                      title="Remove"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <datalist id="known-atses">
        {KNOWN_ATSES.map((a) => (
          <option key={a} value={a} />
        ))}
      </datalist>

      <p className="text-xs text-[var(--muted)] mt-3 leading-relaxed">
        For <code>workday</code>, the slug must be the full URL like{" "}
        <code>https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite</code>. For{" "}
        <code>greenhouse</code> / <code>lever</code> / <code>ashby</code> it's the company segment from
        their careers URL (<code>boards.greenhouse.io/X</code>, <code>jobs.lever.co/X</code>, etc.).
      </p>
    </div>
  );
}

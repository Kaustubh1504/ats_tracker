"use client";

import { useMemo, useState } from "react";
import { createClient } from "@/utils/supabase/client";
import { TargetsEditor } from "./TargetsEditor";
import { RolesEditor } from "./RolesEditor";

type Tab = "targets" | "roles";

export type TargetsDoc = { targets: { ats: string; slug: string }[] };

export type RolesDoc = {
  dataset_queries?: string[];
  title_patterns?: string[];
  intern_patterns?: string[];
  title_block_patterns?: string[];
  country?: string;
  _comment?: string;
};

export function SettingsEditor({
  initialTargets,
  initialRoles,
  targetsUpdatedAt,
  rolesUpdatedAt,
}: {
  initialTargets: TargetsDoc;
  initialRoles: RolesDoc;
  targetsUpdatedAt: string | null;
  rolesUpdatedAt: string | null;
}) {
  const [tab, setTab] = useState<Tab>("targets");
  const supabase = useMemo(() => createClient(), []);

  return (
    <main className="px-4 sm:px-6 lg:px-10 py-6 max-w-[1100px] mx-auto">
      <header className="mb-5">
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="text-sm text-[var(--muted)]">
          Edits go live on the watcher's next run (no Pi restart needed).
        </p>
      </header>

      <div className="flex gap-1 mb-5 border-b border-[var(--border)]">
        {(["targets", "roles"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm border-b-2 -mb-px capitalize transition ${
              tab === t
                ? "border-[var(--accent)] text-[var(--fg)]"
                : "border-transparent text-[var(--muted)] hover:text-[var(--fg)]"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "targets" ? (
        <TargetsEditor
          initial={initialTargets}
          supabase={supabase}
          updatedAt={targetsUpdatedAt}
        />
      ) : (
        <RolesEditor
          initial={initialRoles}
          supabase={supabase}
          updatedAt={rolesUpdatedAt}
        />
      )}
    </main>
  );
}

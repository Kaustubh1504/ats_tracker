import { createClient } from "@/utils/supabase/server";
import { SettingsEditor } from "@/components/SettingsEditor";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function SettingsPage() {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("app_config")
    .select("id, data, updated_at")
    .in("id", ["targets", "roles"]);

  if (error) {
    return (
      <main className="px-4 sm:px-6 lg:px-10 py-6 max-w-[1100px] mx-auto">
        <h1 className="text-2xl font-semibold mb-2">Settings</h1>
        <p className="text-red-600">Failed to load config: {error.message}</p>
        <p className="text-sm text-gray-500 mt-2">
          Make sure the <code>app_config</code> table exists. Run{" "}
          <code>supabase_schema.sql</code> in the SQL editor.
        </p>
      </main>
    );
  }

  const byId = Object.fromEntries((data ?? []).map((r) => [r.id, r]));

  return (
    <SettingsEditor
      initialTargets={byId.targets?.data ?? { targets: [] }}
      initialRoles={byId.roles?.data ?? {}}
      targetsUpdatedAt={byId.targets?.updated_at ?? null}
      rolesUpdatedAt={byId.roles?.updated_at ?? null}
    />
  );
}

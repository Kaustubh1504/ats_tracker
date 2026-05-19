import { createClient } from "@/utils/supabase/server";
import { Dashboard } from "@/components/Dashboard";
import type { Job } from "@/lib/types";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function Page() {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("jobs")
    .select("*")
    .order("first_seen", { ascending: false })
    .limit(2000);

  if (error) {
    return (
      <main className="p-8">
        <h1 className="text-2xl font-semibold mb-2">ATS Tracker</h1>
        <p className="text-red-600">Failed to load jobs: {error.message}</p>
        <p className="text-sm text-gray-500 mt-2">
          Check that the <code>jobs</code> table exists and RLS allows anon
          select. Run <code>supabase_schema.sql</code> in the SQL editor.
        </p>
      </main>
    );
  }

  return <Dashboard initialJobs={(data ?? []) as Job[]} />;
}

export type JobStatus =
  | "new"
  | "interested"
  | "applied"
  | "interview"
  | "rejected"
  | "offer"
  | "skip";

export type Job = {
  id: string;
  global_id: string;
  company: string;
  title: string;
  location: string | null;
  apply_url: string | null;
  description: string | null;
  source: "live" | "dataset";
  ats_type: string | null;
  is_remote: boolean | null;
  salary_summary: string | null;
  posted_at: string | null;
  first_seen: string;
  status: JobStatus;
  priority: boolean;
  notes: string;
  updated_at: string;
};

export const STATUSES: JobStatus[] = [
  "new",
  "interested",
  "applied",
  "interview",
  "rejected",
  "offer",
  "skip",
];

export const STATUS_COLORS: Record<JobStatus, string> = {
  new: "bg-blue-100 text-blue-800 border-blue-200",
  interested: "bg-amber-100 text-amber-800 border-amber-200",
  applied: "bg-violet-100 text-violet-800 border-violet-200",
  interview: "bg-fuchsia-100 text-fuchsia-800 border-fuchsia-200",
  offer: "bg-emerald-100 text-emerald-800 border-emerald-200",
  rejected: "bg-rose-100 text-rose-800 border-rose-200",
  skip: "bg-gray-100 text-gray-600 border-gray-200",
};

export const PRIORITY_COMPANIES = new Set([
  "anthropic",
  "openai",
  "stripe",
  "figma",
  "databricks",
  "notion",
  "vercel",
  "linear",
  "perplexity",
  "ramp",
  "plaid",
  "cohere",
  "supabase",
]);

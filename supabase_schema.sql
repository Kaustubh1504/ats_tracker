-- ATS_Tracker — Supabase schema
-- Run this in Supabase SQL Editor: https://supabase.com/dashboard/project/jgiadyrbgzudgefccvhw/sql/new

-- =========================================================================
-- jobs: the master table of every internship the watcher has ever seen
-- =========================================================================
create table if not exists public.jobs (
  id              uuid primary key default gen_random_uuid(),
  global_id       text unique not null,
  company         text not null,
  title           text not null,
  location        text,
  apply_url       text,
  description     text,
  source          text not null,                       -- 'live' | 'dataset'
  ats_type        text,
  is_remote       boolean,
  salary_summary  text,
  posted_at       text,
  first_seen      timestamptz not null default now(),

  -- Triage fields (user-editable from the webapp)
  status          text not null default 'new'
                  check (status in ('new','interested','applied','interview','rejected','offer','skip')),
  priority        boolean not null default false,
  notes           text not null default '',
  updated_at      timestamptz not null default now()
);

create index if not exists jobs_first_seen_idx on public.jobs (first_seen desc);
create index if not exists jobs_company_idx on public.jobs (company);
create index if not exists jobs_status_idx on public.jobs (status);
create index if not exists jobs_priority_idx on public.jobs (priority) where priority = true;

-- Auto-update updated_at on row change
create or replace function public.touch_updated_at() returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end $$;

drop trigger if exists jobs_touch_updated_at on public.jobs;
create trigger jobs_touch_updated_at before update on public.jobs
  for each row execute function public.touch_updated_at();

-- =========================================================================
-- RLS: single-user mode. Allow anon read+write on jobs.
-- (For multi-user, replace with auth-based policies later.)
-- =========================================================================
alter table public.jobs enable row level security;

drop policy if exists "anon read jobs"  on public.jobs;
drop policy if exists "anon write jobs" on public.jobs;
drop policy if exists "anon update jobs" on public.jobs;

create policy "anon read jobs"   on public.jobs for select to anon using (true);
create policy "anon write jobs"  on public.jobs for insert to anon with check (true);
create policy "anon update jobs" on public.jobs for update to anon using (true) with check (true);

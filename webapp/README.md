# ATS Tracker — webapp

Triage UI for the internship watcher. Reads from Supabase, lets you set status,
priority, and notes per role. Sort by recency, filter by company, search by
title — the things Discord couldn't do.

## Local development

```bash
cd webapp
npm install
npm run dev
# open http://localhost:3000
```

`.env.local` already has the Supabase URL + publishable key.

## Deploy to Vercel

1. Push the repo to GitHub.
2. On vercel.com → **Add New Project** → import this repo.
3. **Root Directory** → set to `webapp` (important — the watcher lives at repo
   root, the Next app is nested).
4. Add env vars (Settings → Environment Variables):
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`
5. Deploy. First build takes ~2 min.

## Data flow

```
watcher.py (GitHub Actions, hourly)
   └── Supabase `jobs` table  ◀──── webapp reads / writes
                              ◀──── Discord & email summary on each run with new rows
```

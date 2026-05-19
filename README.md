# Summer 2027 internship watcher

Polls jobhive for US Summer 2027 internships in software / AI / ML / cloud /
network roles and posts new ones to a Discord webhook. Deduplicates against
`data/seen.csv`, which is committed back to the repo by GitHub Actions.

```
summer2027/
├── watcher.py
├── config/
│   ├── targets.json        # live-scrape companies (edit me)
│   └── roles.json          # search queries & filter regexes (edit me)
├── data/
│   └── seen.csv            # dedupe store — committed by Actions
├── requirements.txt
└── .github/workflows/
    └── watch.yml
```

## Setup (GitHub Actions)

1. **Push this folder to a GitHub repo.** Public or private both fine —
   free-tier minutes are plenty for this workload (~150 min/month).
2. **Settings → Secrets and variables → Actions → New repository secret.**
   - Name: `DISCORD_WEBHOOK_URL`
   - Value: your Discord webhook URL.
3. **Actions tab → enable workflows** if prompted.
4. **Settings → Actions → General → Workflow permissions** → make sure
   "Read and write permissions" is selected. (This is what lets the
   workflow commit `data/seen.csv` back.)

That's it. The workflow runs the live scrape every 15 minutes and the
dataset sweep once a day at 09:00 UTC. The first live run will post a
backlog of currently-open Summer 2027 roles to Discord — expected, all
subsequent runs only post net-new ones.

To trigger a run manually for testing: **Actions tab → Summer 2027 watcher
→ Run workflow.**

## How dedupe works

- On startup, the watcher reads every `global_id` in `data/seen.csv` into
  an in-memory set.
- Every job posted to Discord gets one new row appended to `seen.csv`.
- The workflow commits `seen.csv` back to the repo at the end of each run.
- The next run pulls the latest, reads `seen.csv`, and starts where the
  previous one left off.

This is more reliable than `actions/cache` (caches can be evicted; the
repo can't be). The CSV grows ~80 bytes per row, so even at 50 new jobs
per day for a full year it's < 2 MB.

## Editing the watch list

`config/targets.json` — add or remove entries:

```json
{ "ats": "greenhouse", "slug": "anthropic" }
```

`ats` must be a jobhive scraper id (greenhouse, lever, ashby, etc.). `slug`
is the company's identifier on that ATS — usually the URL path segment
(`boards.greenhouse.io/<slug>`, `jobs.lever.co/<slug>`). For big-tech
endpoints (amazon, apple, google, tiktok, uber, meta, tesla) the slug is
ignored but must be present.

`config/roles.json` — regexes are standard Python `re` syntax. Escape
backslashes (`\\b`, not `\b`) because this is JSON.

Edits to either config take effect on the next workflow run. No code
changes needed.

## Local development

```bash
pip install -r requirements.txt
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."

python watcher.py --once-live      # smoke-test the live path
python watcher.py --once-dataset   # smoke-test the dataset path
python watcher.py --once           # both passes once
python watcher.py                  # long-running scheduler
```

`data/seen.csv` is updated in place. If you ever want to "reset" the
watcher and reposting everything, just delete the file (the script will
recreate it on next run).

## Caveats with Actions

- **Cron drift.** GitHub Actions cron is best-effort. During peak load it
  can run 5–20 minutes late. For real 15-minute cadence you'd need an
  always-on host (Railway, Render, Fly). For internship hunting this is
  fine — postings stay up for days, not minutes.
- **Concurrency.** The workflow uses `concurrency: group: watcher` so the
  live and dataset runs serialize, and the push step retries with
  `--rebase` if it loses a race. If you see a workflow fail with "push
  rejected", the retry usually resolves it; just rerun.
- **Meta and Tesla scrapers** need Browserbase (paid service) per the
  jobhive README. Don't add them to `targets.json` unless you set
  `BROWSERBASE_API_KEY` and `BROWSERBASE_PROJECT_ID` as repo secrets.

## Troubleshooting

- **No posts on first run.** Check Actions tab → recent run → look at the
  "Run watcher" log. You should see `Collected N candidate rows` and
  `Posted N new role(s) (..., no-match=M)`. If `no-match` is huge, the
  regex is too tight — usually because postings don't say "2027"
  literally. Loosen `year_patterns` in `roles.json` temporarily and rerun.
- **`scraper failed: 429`** for a specific company. Drop that entry from
  `targets.json`; that ATS is throttling you.
- **`seen.csv` push conflicts.** The retry block should handle it, but if
  it keeps failing, run the workflow manually with `workflow_dispatch` and
  the rebased state will catch up.
# ats_tracker

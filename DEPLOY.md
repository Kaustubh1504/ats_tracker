# Deploy

Two pieces to deploy:

- **Webapp** → Vercel (Next.js, free hobby tier)
- **Watcher** → Raspberry Pi (systemd, 24/7)

Both read/write the same Supabase project. Webapp shows jobs and edits config.
Pi runs the scrape on a schedule.

---

## 1. Supabase schema

If you haven't already, run [supabase_schema.sql](supabase_schema.sql) in the
Supabase SQL editor. Creates `jobs` and `app_config` tables with permissive
anon RLS (single-user mode).

## 2. Seed the config table

Imports your local `config/targets.json` + `config/roles.json` into the
`app_config` table so the webapp has something to show and the watcher
has something to fetch.

```bash
set -a; source .env; set +a
.venv/bin/python scripts/seed_config.py
```

After this, the webapp's `Settings` page is the source of truth — local
files become a cache/fallback only.

## 3. Webapp → Vercel

```bash
# In the GitHub UI, push the repo first (if you haven't):
git push origin main

# Then on vercel.com:
```

1. **Add New Project** → import the GitHub repo
2. **Root Directory**: `webapp` ← critical, the watcher lives at repo root, Next app is nested
3. **Build Command**: leave default (`next build`)
4. **Environment Variables** (Production + Preview + Development):
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`
5. **Deploy** — first build takes ~2 min
6. Copy the assigned URL (e.g. `https://ats-tracker-xxx.vercel.app`) — set it as `WEBAPP_URL` in `.env` so summary emails link back

Updates: any `git push origin main` triggers a redeploy.

## 4. Watcher → Raspberry Pi

```bash
# On the Pi
sudo apt update && sudo apt install python3.12-venv git -y

cd ~ && git clone https://github.com/Kaustubh1504/ats_tracker.git
cd ats_tracker

python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# Copy your .env from your laptop or recreate it
nano .env
chmod 600 .env

# Smoke-test once (should see "Loaded config from Supabase" in the log)
set -a; source .env; set +a
.venv/bin/python watcher.py --once-live

# Install as a service (edit User/path in ats-tracker.service if needed)
sudo cp ats-tracker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ats-tracker

# Tail the logs
journalctl -u ats-tracker -f
```

## How config edits flow

```
Webapp Settings page  →  edit  →  Supabase app_config table
                                        │
                                        ▼
                       Pi watcher (next hourly tick)
                                        │
                                        ▼
                  local config/*.json updated as cache
                  scrapers use the new targets/roles
```

No service restart needed when you edit settings — the watcher pulls fresh
config on every `live_check`/`dataset_check` tick. If Supabase is unreachable,
it falls back to the locally cached `config/*.json`.

## Troubleshooting

- **Webapp shows "Failed to load jobs/config"** — run [supabase_schema.sql](supabase_schema.sql).
- **Watcher always says "Loaded config from local files"** — seed_config.py wasn't run, or the env vars are missing on the Pi.
- **Settings page edits don't take effect** — wait one polling interval (default 60 min). To force a refresh: `sudo systemctl restart ats-tracker`.
- **GitHub Actions still running after Pi takeover** — disable the workflow in repo settings, or delete the file (already removed in this repo).

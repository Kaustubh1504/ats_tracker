"""One-time seed of app_config table from local targets.json + roles.json.

Run once after creating the table (supabase_schema.sql). Subsequent edits
should happen through the webapp Settings page.

    .venv/bin/python scripts/seed_config.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

try:
    from supabase import create_client
except ImportError:
    sys.exit("pip install supabase first")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    sys.exit("SUPABASE_URL and SUPABASE_KEY must be set in the env (try: source .env)")

repo_root = Path(__file__).resolve().parent.parent
targets_path = repo_root / "config" / "targets.json"
roles_path = repo_root / "config" / "roles.json"

targets = json.loads(targets_path.read_text())
roles = json.loads(roles_path.read_text())

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

for cfg_id, payload in (("targets", targets), ("roles", roles)):
    res = sb.table("app_config").upsert(
        {"id": cfg_id, "data": payload}, on_conflict="id"
    ).execute()
    print(f"✓ Seeded {cfg_id}: {len(payload.get('targets', payload) if isinstance(payload, dict) else [])} entries / "
          f"{sum(len(v) if isinstance(v, list) else 0 for v in payload.values())} list items")

print("\nDone. The watcher will fetch this on its next run; the webapp Settings page now reflects it.")

"""One-time backfill of data/seen.csv into the Supabase `jobs` table.

Pre-Supabase runs only wrote to the CSV. This script reads every row and
upserts (insert-or-update on global_id conflict) it into the table so that
Supabase becomes the complete source of truth for dedupe.

    .venv/bin/python scripts/backfill_seen.py

Idempotent — safe to run multiple times. Rows already in Supabase are
silently overwritten with the same data.
"""
from __future__ import annotations

import csv
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
    sys.exit("SUPABASE_URL and SUPABASE_KEY must be set (try: source .env)")

repo_root = Path(__file__).resolve().parent.parent
csv_path = repo_root / "data" / "seen.csv"
if not csv_path.exists():
    sys.exit(f"No CSV at {csv_path} — nothing to backfill")

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# Read CSV
rows: list[dict] = []
with csv_path.open("r", newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        gid = (row.get("global_id") or "").strip()
        if not gid:
            continue
        rows.append({
            "global_id": gid,
            "company": (row.get("company") or "Unknown")[:200],
            "title": (row.get("title") or "Untitled")[:300],
            "location": (row.get("location") or "")[:200] or None,
            "source": row.get("source") or "live",
            "posted_at": (row.get("posted_at") or "") or None,
            # Use first_seen from CSV when present so backfill keeps the
            # original "when did we first notice this" timestamp.
            "first_seen": (row.get("first_seen") or "") or None,
        })

print(f"Read {len(rows)} rows from {csv_path}")
if not rows:
    sys.exit("Nothing to upsert.")

# Upsert in batches — Supabase recommends ≤500 rows per request.
BATCH = 500
upserted = 0
for i in range(0, len(rows), BATCH):
    batch = rows[i : i + BATCH]
    # Strip None first_seen so the table default (now()) kicks in for empty values.
    cleaned = [
        {k: v for k, v in r.items() if v is not None}
        for r in batch
    ]
    try:
        sb.table("jobs").upsert(cleaned, on_conflict="global_id").execute()
        upserted += len(batch)
        print(f"  upserted {upserted}/{len(rows)}")
    except Exception as e:
        sys.exit(f"Batch starting at row {i} failed: {e}")

print(f"\nDone. {upserted} rows synced to Supabase jobs table.")
print("Pi can now run without seen.csv — Supabase is the source of truth.")

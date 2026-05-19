"""
Summer 2027 internship watcher — CSV-backed dedupe, GitHub-Actions-friendly.

  • Live scrape (--once-live):
      Hits ATS APIs directly for the companies in config/targets.json.

  • Dataset sweep (--once-dataset):
      Runs jobhive.search() across the queries in config/roles.json.

  • Default (no args):
      Long-running APScheduler: live every LIVE_POLL_MINUTES, dataset every
      DATASET_POLL_HOURS. Useful for always-on hosts. GitHub Actions should
      use --once-live or --once-dataset and let cron drive the cadence.

Dedupe lives in data/seen.csv. Loaded on startup, appended to on every new
post. Commit it back to the repo so each Actions run starts where the last
one ended.

Required env
------------
    DISCORD_WEBHOOK_URL   Discord webhook URL

Optional env
------------
    CONFIG_DIR            Directory containing targets.json + roles.json
                          (default: ./config)
    SEEN_CSV              Path to dedupe CSV (default: ./data/seen.csv)
    LIVE_POLL_MINUTES     Live scrape interval  (default: 15)
    DATASET_POLL_HOURS    Dataset sweep interval (default: 24)
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests
from apscheduler.schedulers.blocking import BlockingScheduler

try:
    from jobhive import search
    from jobhive.scrapers import get_scraper
except ImportError:
    sys.exit("jobhive is not installed. Run: pip install 'jobhive-py[parquet,scrapers]'")


# =========================================================================== #
# Config
# =========================================================================== #

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", "config"))
SEEN_CSV = Path(os.environ.get("SEEN_CSV", "data/seen.csv"))
LIVE_POLL_MINUTES = int(os.environ.get("LIVE_POLL_MINUTES", "15"))
DATASET_POLL_HOURS = int(os.environ.get("DATASET_POLL_HOURS", "24"))
POST_DELAY_SEC = 1.0

CSV_COLUMNS = ["global_id", "company", "title", "location", "source", "posted_at", "first_seen"]


@dataclass(frozen=True)
class Target:
    ats: str
    slug: str


@dataclass
class Config:
    targets: list[Target]
    dataset_queries: list[str]
    title_re: re.Pattern
    intern_re: re.Pattern
    year_re: re.Pattern
    country: str


def _load_json(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"Config file missing: {path}")
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        sys.exit(f"Invalid JSON in {path}: {e}")


def load_config(config_dir: Path) -> Config:
    targets_doc = _load_json(config_dir / "targets.json")
    roles_doc = _load_json(config_dir / "roles.json")

    targets: list[Target] = []
    for i, entry in enumerate(targets_doc.get("targets") or []):
        ats, slug = entry.get("ats"), entry.get("slug")
        if not ats or not slug:
            log.warning("targets.json[%d] missing ats/slug, skipping: %r", i, entry)
            continue
        targets.append(Target(ats=ats.strip().lower(), slug=slug.strip()))

    def _compile(patterns: Iterable[str], name: str) -> re.Pattern:
        joined = "|".join(patterns)
        if not joined:
            sys.exit(f"roles.json: {name} is empty")
        try:
            return re.compile(joined, re.IGNORECASE)
        except re.error as e:
            sys.exit(f"roles.json: bad regex in {name}: {e}")

    return Config(
        targets=targets,
        dataset_queries=list(roles_doc.get("dataset_queries") or []),
        title_re=_compile(roles_doc.get("title_patterns") or [], "title_patterns"),
        intern_re=_compile(roles_doc.get("intern_patterns") or [], "intern_patterns"),
        year_re=_compile(roles_doc.get("year_patterns") or [], "year_patterns"),
        country=(roles_doc.get("country") or "US").strip().upper(),
    )


# =========================================================================== #
# Logging
# =========================================================================== #

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  [%(name)s]  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("watcher")
live_log = logging.getLogger("watcher.live")
ds_log = logging.getLogger("watcher.dataset")


# =========================================================================== #
# CSV dedupe store
# =========================================================================== #

class SeenStore:
    """In-memory set of global_ids backed by an append-only CSV."""

    def __init__(self, path: Path):
        self.path = path
        self._ids: set[str] = set()
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Write header so subsequent appends don't need to check.
            with self.path.open("w", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=CSV_COLUMNS).writeheader()
            log.info("Created new dedupe CSV at %s", self.path)
            return

        with self.path.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                gid = (row.get("global_id") or "").strip()
                if gid:
                    self._ids.add(gid)
        log.info("Loaded %d seen ids from %s", len(self._ids), self.path)

    def __contains__(self, gid: str) -> bool:
        return gid in self._ids

    def add(self, row: dict, source: str) -> None:
        gid = (row.get("global_id") or "").strip()
        if not gid or gid in self._ids:
            return
        self._ids.add(gid)
        with self.path.open("a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=CSV_COLUMNS).writerow({
                "global_id": gid,
                "company": (row.get("company") or "")[:200],
                "title": (row.get("title") or "")[:300],
                "location": (row.get("location") or "")[:200],
                "source": source,
                "posted_at": str(row.get("posted_at") or ""),
                "first_seen": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })


# =========================================================================== #
# Job → dict normaliser
# =========================================================================== #

def job_to_dict(job) -> dict:
    if isinstance(job, dict):
        return job
    if dataclasses.is_dataclass(job):
        return dataclasses.asdict(job)
    if hasattr(job, "model_dump"):
        return job.model_dump()
    if hasattr(job, "dict"):
        return job.dict()
    if hasattr(job, "__dict__"):
        return dict(job.__dict__)
    raise TypeError(f"Cannot convert {type(job)!r} to dict")


# =========================================================================== #
# Filtering
# =========================================================================== #

US_LOCATION_MARKERS = (
    "united states", "usa", " u.s.", " us ", ", us",
    " ca", " ny", " wa", " tx", " ma", " il", " co", " ga", " fl",
    "california", "new york", "seattle", "san francisco", "bay area",
    "boston", "austin", "chicago", "atlanta", "denver",
    "remote - us", "remote, us", "remote (us)", "us remote",
)


def is_in_country(row: dict, country: str) -> bool:
    iso = (row.get("country_iso") or "").strip().upper()
    if iso == country:
        return True
    if iso and iso != country:
        return False
    if country != "US":
        return True
    loc = (row.get("location") or "").lower()
    return any(m in loc for m in US_LOCATION_MARKERS) if loc else False


def matches_role(row: dict, cfg: Config) -> bool:
    title = str(row.get("title") or "")
    desc = str(row.get("description") or "")
    blob = f"{title}\n{desc}"

    if not cfg.intern_re.search(blob):
        return False
    if not cfg.year_re.search(blob):
        return False
    if cfg.title_re.search(title):
        return True
    if re.search(r"\bintern\b", title, re.IGNORECASE) and cfg.title_re.search(desc):
        return True
    return False


# =========================================================================== #
# Discord
# =========================================================================== #

def build_embed(row: dict, source: str) -> dict:
    title = (row.get("title") or "Untitled role")[:250]
    company = row.get("company") or "Unknown company"
    url = row.get("apply_url") or row.get("url") or ""

    fields = []
    if row.get("location"):
        fields.append({"name": "Location", "value": str(row["location"])[:1000], "inline": True})
    if row.get("is_remote"):
        fields.append({"name": "Remote", "value": "Yes", "inline": True})
    if row.get("salary_summary"):
        fields.append({"name": "Salary", "value": str(row["salary_summary"])[:1000], "inline": True})
    elif row.get("salary_min") or row.get("salary_max"):
        s_min = row.get("salary_min") or "?"
        s_max = row.get("salary_max") or "?"
        cur = row.get("salary_currency") or ""
        fields.append({"name": "Salary", "value": f"{s_min}–{s_max} {cur}".strip(), "inline": True})
    if row.get("ats_type"):
        fields.append({"name": "ATS", "value": str(row["ats_type"]), "inline": True})
    fields.append({"name": "Source", "value": source, "inline": True})

    desc_src = str(row.get("description") or "")
    if len(desc_src) > 400:
        desc_src = desc_src[:400].rsplit(" ", 1)[0] + "…"

    return {
        "title": f"{title} — {company}",
        "url": url,
        "description": desc_src or None,
        "fields": fields,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def post_to_discord(row: dict, source: str) -> bool:
    if not WEBHOOK_URL:
        log.error("DISCORD_WEBHOOK_URL is not set; cannot post.")
        return False

    payload = {"embeds": [build_embed(row, source)]}
    try:
        r = requests.post(WEBHOOK_URL, json=payload, timeout=15)
    except requests.RequestException as e:
        log.warning("Discord POST failed: %s", e)
        return False

    if r.status_code == 429:
        wait = float(r.json().get("retry_after", 2))
        log.info("Rate limited; sleeping %.1fs", wait)
        time.sleep(wait)
        return post_to_discord(row, source)

    if not r.ok:
        log.warning("Discord %s: %s", r.status_code, r.text[:200])
        return False
    return True


# =========================================================================== #
# Shared pipeline
# =========================================================================== #

def process_rows(
    rows: list[dict],
    source: str,
    seen: SeenStore,
    cfg: Config,
) -> tuple[int, int, int, int]:
    posted = skipped_seen = skipped_country = skipped_match = 0
    for row in rows:
        gid = row.get("global_id")
        if not gid:
            continue
        if gid in seen:
            skipped_seen += 1
            continue
        if not is_in_country(row, cfg.country):
            skipped_country += 1
            continue
        if not matches_role(row, cfg):
            skipped_match += 1
            continue

        if post_to_discord(row, source):
            seen.add(row, source)
            posted += 1
            time.sleep(POST_DELAY_SEC)
    return posted, skipped_seen, skipped_country, skipped_match


# =========================================================================== #
# Modes
# =========================================================================== #

def live_check(cfg: Config, seen: SeenStore) -> None:
    live_log.info("Live scrape of %d targets…", len(cfg.targets))
    rows: list[dict] = []
    for t in cfg.targets:
        try:
            jobs = get_scraper(t.ats, t.slug).fetch()
        except Exception as e:
            live_log.warning("%s/%s scraper failed: %s", t.ats, t.slug, e)
            continue
        for job in jobs or []:
            try:
                rows.append(job_to_dict(job))
            except TypeError as e:
                live_log.warning("Unconvertible job from %s/%s: %s", t.ats, t.slug, e)
        # Gentle stagger to avoid looking botty to any single ATS host.
        time.sleep(1.0)

    live_log.info("Collected %d candidate rows", len(rows))
    posted, s_seen, s_country, s_match = process_rows(rows, "live", seen, cfg)
    live_log.info(
        "Posted %d new role(s)  (seen=%d, non-%s=%d, no-match=%d)",
        posted, s_seen, cfg.country, s_country, s_match,
    )


def dataset_check(cfg: Config, seen: SeenStore) -> None:
    ds_log.info("Dataset sweep across %d queries…", len(cfg.dataset_queries))
    location_hint = "United States" if cfg.country == "US" else None
    by_id: dict[str, dict] = {}
    for query in cfg.dataset_queries:
        try:
            kwargs = {"query": query}
            if location_hint:
                kwargs["location"] = location_hint
            df = search(**kwargs)
        except Exception as e:
            ds_log.warning("search(%r) failed: %s", query, e)
            continue
        if df is None or len(df) == 0:
            continue
        for row in df.to_dict(orient="records"):
            gid = row.get("global_id")
            if gid:
                by_id.setdefault(gid, row)

    ds_log.info("Collected %d unique candidate rows", len(by_id))
    posted, s_seen, s_country, s_match = process_rows(
        list(by_id.values()), "dataset", seen, cfg
    )
    ds_log.info(
        "Posted %d new role(s)  (seen=%d, non-%s=%d, no-match=%d)",
        posted, s_seen, cfg.country, s_country, s_match,
    )


# =========================================================================== #
# Entrypoint
# =========================================================================== #

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once-live", action="store_true", help="One live scrape, then exit")
    parser.add_argument("--once-dataset", action="store_true", help="One dataset sweep, then exit")
    parser.add_argument("--once", action="store_true", help="Both passes once, then exit")
    args = parser.parse_args()

    if not WEBHOOK_URL:
        log.warning("DISCORD_WEBHOOK_URL is not set — matches will be logged but not posted.")

    cfg = load_config(CONFIG_DIR)
    seen = SeenStore(SEEN_CSV)
    log.info(
        "Config: %d targets, %d dataset queries, country=%s, %d previously seen",
        len(cfg.targets), len(cfg.dataset_queries), cfg.country, len(seen._ids),
    )

    if args.once_live:
        live_check(cfg, seen); return
    if args.once_dataset:
        dataset_check(cfg, seen); return
    if args.once:
        live_check(cfg, seen); dataset_check(cfg, seen); return

    # Long-running mode: both immediately, then on schedule.
    live_check(cfg, seen)
    dataset_check(cfg, seen)

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(lambda: live_check(cfg, seen),    "interval",
                      minutes=LIVE_POLL_MINUTES,  max_instances=1, id="live")
    scheduler.add_job(lambda: dataset_check(cfg, seen), "interval",
                      hours=DATASET_POLL_HOURS,   max_instances=1, id="dataset")
    log.info(
        "Scheduler started — live every %d min, dataset every %d h. Ctrl-C to quit.",
        LIVE_POLL_MINUTES, DATASET_POLL_HOURS,
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Shutting down.")


if __name__ == "__main__":
    main()

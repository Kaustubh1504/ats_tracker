"""
Internship watcher — writes new postings to Supabase, sends a single Discord +
email summary per run.

  • Live scrape (--once-live):
      Hits ATS APIs directly for the companies in config/targets.json.

  • Dataset sweep (--once-dataset):
      Runs jobhive.search() across the queries in config/roles.json.

Dedupe is dual-tracked: an in-memory CSV (data/seen.csv) for cheap re-run
gating, and Supabase's unique constraint on global_id for the actual storage.

Required env
------------
    SUPABASE_URL          https://<project>.supabase.co
    SUPABASE_KEY          anon/publishable key (RLS policies allow anon writes)

Optional env
------------
    DISCORD_WEBHOOK_URL   Webhook for the per-run summary ping
    RESEND_API_KEY        Resend API key (for the per-run email summary)
    NOTIFY_EMAIL          Where to send the run summary email
    NOTIFY_FROM_EMAIL     'From' address (default: onboarding@resend.dev)
    WEBAPP_URL            Link to the webapp, included in summary messages
    CONFIG_DIR            Directory containing targets.json + roles.json (default: ./config)
    SEEN_CSV              Path to dedupe CSV (default: ./data/seen.csv)
    LIVE_POLL_MINUTES     Live scrape interval  (default: 60)
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
from concurrent.futures import ThreadPoolExecutor, as_completed
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

try:
    from supabase import create_client, Client
except ImportError:
    sys.exit("supabase client not installed. Run: pip install supabase")


# =========================================================================== #
# Config
# =========================================================================== #

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL")
NOTIFY_FROM_EMAIL = os.environ.get("NOTIFY_FROM_EMAIL", "onboarding@resend.dev")
WEBAPP_URL = os.environ.get("WEBAPP_URL")

CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", "config"))
SEEN_CSV = Path(os.environ.get("SEEN_CSV", "data/seen.csv"))
LIVE_POLL_MINUTES = int(os.environ.get("LIVE_POLL_MINUTES", "60"))
DATASET_POLL_HOURS = int(os.environ.get("DATASET_POLL_HOURS", "24"))
SCRAPE_WORKERS = int(os.environ.get("SCRAPE_WORKERS", "8"))
SCRAPE_TIMEOUT_SEC = float(os.environ.get("SCRAPE_TIMEOUT_SEC", "120"))

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
    title_block_re: re.Pattern | None
    country: str


def _load_json(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"Config file missing: {path}")
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        sys.exit(f"Invalid JSON in {path}: {e}")


def _fetch_remote_config(sb: "Client | None") -> tuple[dict | None, dict | None]:
    """Fetch targets + roles JSON from app_config table. Returns (targets, roles) or (None, None)."""
    if sb is None:
        return None, None
    try:
        resp = sb.table("app_config").select("id, data").in_("id", ["targets", "roles"]).execute()
    except Exception as e:
        log.warning("Remote config fetch failed: %s", e)
        return None, None
    rows = {r["id"]: r["data"] for r in (resp.data or [])}
    return rows.get("targets"), rows.get("roles")


def _write_local_cache(config_dir: Path, targets_doc: dict, roles_doc: dict) -> None:
    """Persist whatever config we used this run as the offline fallback."""
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "targets.json").write_text(json.dumps(targets_doc, indent=2))
        (config_dir / "roles.json").write_text(json.dumps(roles_doc, indent=2))
    except OSError as e:
        log.warning("Couldn't cache config to %s: %s", config_dir, e)


def load_config(config_dir: Path, sb: "Client | None" = None) -> Config:
    remote_targets, remote_roles = _fetch_remote_config(sb)
    if remote_targets is not None and remote_roles is not None:
        targets_doc, roles_doc = remote_targets, remote_roles
        log.info("Loaded config from Supabase (app_config table).")
        _write_local_cache(config_dir, targets_doc, roles_doc)
    else:
        targets_doc = _load_json(config_dir / "targets.json")
        roles_doc = _load_json(config_dir / "roles.json")
        log.info("Loaded config from local files (Supabase unavailable or empty).")

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

    block_patterns = roles_doc.get("title_block_patterns") or []
    title_block_re = None
    if block_patterns:
        try:
            title_block_re = re.compile("|".join(block_patterns), re.IGNORECASE)
        except re.error as e:
            sys.exit(f"roles.json: bad regex in title_block_patterns: {e}")

    return Config(
        targets=targets,
        dataset_queries=list(roles_doc.get("dataset_queries") or []),
        title_re=_compile(roles_doc.get("title_patterns") or [], "title_patterns"),
        intern_re=_compile(roles_doc.get("intern_patterns") or [], "intern_patterns"),
        title_block_re=title_block_re,
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
# Supabase
# =========================================================================== #

def get_supabase() -> Client | None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        log.warning("SUPABASE_URL / SUPABASE_KEY not set — Supabase writes disabled.")
        return None
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        log.error("Failed to init Supabase client: %s", e)
        return None


def _truncate(value, limit: int) -> str | None:
    s = str(value or "").strip()
    if not s:
        return None
    return s[:limit]


def write_to_supabase(sb: Client, row: dict, source: str) -> bool:
    gid = (row.get("global_id") or "").strip()
    if not gid:
        return False

    payload = {
        "global_id": gid,
        "company": _truncate(row.get("company"), 200) or "Unknown",
        "title": _truncate(row.get("title"), 300) or "Untitled",
        "location": _truncate(row.get("location"), 200),
        "apply_url": _truncate(row.get("apply_url") or row.get("url"), 1000),
        "description": _truncate(row.get("description"), 8000),
        "source": source,
        "ats_type": _truncate(row.get("ats_type"), 80),
        "is_remote": bool(row["is_remote"]) if row.get("is_remote") is not None else None,
        "salary_summary": _truncate(row.get("salary_summary"), 200),
        "posted_at": _truncate(row.get("posted_at"), 80),
    }
    try:
        sb.table("jobs").upsert(payload, on_conflict="global_id").execute()
        return True
    except Exception as e:
        log.warning("Supabase upsert failed for %s: %s", gid, e)
        return False


# =========================================================================== #
# CSV dedupe store (belt-and-suspenders alongside Supabase's unique constraint)
# =========================================================================== #

class SeenStore:
    """In-memory set of global_ids. Source of truth is the Supabase `jobs`
    table; the CSV is an append-only offline cache used when Supabase is
    unreachable at startup."""

    def __init__(self, path: Path, sb: "Client | None" = None):
        self.path = path
        self._ids: set[str] = set()
        if sb is not None:
            self._load_from_supabase(sb)
        # CSV always merges in too — covers pre-Supabase entries and any
        # row that made it to the CSV cache but not the table.
        self._load_from_csv()
        log.info("Dedupe set size after merge: %d", len(self._ids))

    def _load_from_supabase(self, sb: "Client") -> bool:
        try:
            ids: set[str] = set()
            page = 1000
            offset = 0
            while True:
                resp = (
                    sb.table("jobs")
                    .select("global_id")
                    .range(offset, offset + page - 1)
                    .execute()
                )
                rows = resp.data or []
                ids.update(r["global_id"] for r in rows if r.get("global_id"))
                if len(rows) < page:
                    break
                offset += page
            self._ids = ids
            log.info("Loaded %d seen ids from Supabase (jobs table)", len(self._ids))
            return True
        except Exception as e:
            log.warning("Supabase dedupe load failed (%s); falling back to CSV cache", e)
            return False

    def _load_from_csv(self) -> None:
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
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
        log.info("Loaded %d seen ids from CSV cache %s", len(self._ids), self.path)

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

US_EXPLICIT_MARKERS = (
    "united states", "usa", "u.s.a", "u.s.",
    ", us", "remote - us", "remote, us", "remote (us)", "us remote",
)

US_CITY_MARKERS = (
    "new york", "san francisco", "los angeles", "seattle", "boston",
    "austin", "chicago", "atlanta", "denver", "bay area",
    "silicon valley", "washington d.c.", "washington, dc",
)

_US_STATE_CODES = (
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN "
    "MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA "
    "WA WV WI WY DC"
).split()
US_STATE_RE = re.compile(r",\s*(" + "|".join(_US_STATE_CODES) + r")\b", re.IGNORECASE)


def is_in_country(row: dict, country: str) -> bool:
    iso = (row.get("country_iso") or "").strip().upper()
    if iso == country:
        return True
    if iso and iso != country:
        return False
    if country != "US":
        return True
    loc = row.get("location") or ""
    if not loc:
        return False
    loc_lower = loc.lower()
    if any(m in loc_lower for m in US_EXPLICIT_MARKERS):
        return True
    if any(m in loc_lower for m in US_CITY_MARKERS):
        return True
    return bool(US_STATE_RE.search(loc))


def matches_role(row: dict, cfg: Config) -> str:
    title = str(row.get("title") or "")
    desc = str(row.get("description") or "")
    blob = f"{title}\n{desc}"

    if not cfg.intern_re.search(blob):
        return "no_intern"
    if cfg.title_block_re is not None and cfg.title_block_re.search(title):
        return "blocked"
    if cfg.title_re.search(title):
        return "ok"
    if re.search(r"\bintern\b", title, re.IGNORECASE) and cfg.title_re.search(desc):
        return "ok"
    return "no_title"


# =========================================================================== #
# Notifications — sent once per run, only if there are new jobs
# =========================================================================== #

def send_discord_summary(source: str, new_rows: list[dict]) -> None:
    if not WEBHOOK_URL or not new_rows:
        return

    count = len(new_rows)
    preview_lines = []
    for r in new_rows[:10]:
        title = (r.get("title") or "Untitled")[:80]
        company = r.get("company") or "?"
        url = str(r.get("apply_url") or r.get("url") or "")
        if url:
            preview_lines.append(f"• [**{title}**]({url}) — {company}")
        else:
            preview_lines.append(f"• **{title}** — {company}")
    if count > 10:
        preview_lines.append(f"…and {count - 10} more")
    preview = "\n".join(preview_lines)

    embed = {
        "title": f"🆕 {count} new internship{'s' if count != 1 else ''} ({source})",
        "description": preview,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if WEBAPP_URL:
        embed["url"] = WEBAPP_URL

    try:
        r = requests.post(WEBHOOK_URL, json={"embeds": [embed]}, timeout=15)
        if not r.ok:
            log.warning("Discord summary %s: %s", r.status_code, r.text[:200])
    except requests.RequestException as e:
        log.warning("Discord summary POST failed: %s", e)


def send_email_summary(source: str, new_rows: list[dict]) -> None:
    if not RESEND_API_KEY or not NOTIFY_EMAIL or not new_rows:
        return

    count = len(new_rows)

    # Per-company tally — sorted by count desc, then company asc.
    per_company: dict[str, int] = {}
    for r in new_rows:
        co = (r.get("company") or "Unknown").strip() or "Unknown"
        per_company[co] = per_company.get(co, 0) + 1
    company_breakdown = sorted(per_company.items(), key=lambda kv: (-kv[1], kv[0].lower()))

    breakdown_html = "".join(
        f'<tr>'
        f'<td style="padding:6px 12px;border-bottom:1px solid #f0f0f0;font-weight:500">{co}</td>'
        f'<td style="padding:6px 12px;border-bottom:1px solid #f0f0f0;text-align:right;color:#666;font-variant-numeric:tabular-nums">{n}</td>'
        f'</tr>'
        for co, n in company_breakdown
    )

    dashboard_link = f'<p><a href="{WEBAPP_URL}" style="color:#2563eb">Open dashboard →</a></p>' if WEBAPP_URL else ""

    body_html = f"""
    <div style="font-family:-apple-system,system-ui,sans-serif;max-width:560px;margin:0 auto">
      <h2 style="margin-bottom:4px">{count} new internship{'s' if count != 1 else ''}</h2>
      <p style="color:#666;margin-top:0">source: <code>{source}</code> · {len(company_breakdown)} compan{'ies' if len(company_breakdown) != 1 else 'y'}</p>
      {dashboard_link}
      <table style="border-collapse:collapse;width:100%;margin-top:12px;font-size:14px">
        <tbody>
          {breakdown_html}
        </tbody>
      </table>
    </div>
    """

    try:
        r = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={
                "from": NOTIFY_FROM_EMAIL,
                "to": [NOTIFY_EMAIL],
                "subject": f"[ATS] {count} new — {source}",
                "html": body_html,
            },
            timeout=15,
        )
        if not r.ok:
            log.warning("Resend %s: %s", r.status_code, r.text[:200])
    except requests.RequestException as e:
        log.warning("Email summary failed: %s", e)


def send_run_summary(source: str, new_rows: list[dict]) -> None:
    if not new_rows:
        return
    send_discord_summary(source, new_rows)
    send_email_summary(source, new_rows)


# =========================================================================== #
# Shared pipeline
# =========================================================================== #

def process_rows(
    rows: list[dict],
    source: str,
    seen: SeenStore,
    cfg: Config,
    sb: Client | None,
) -> tuple[dict, list[dict]]:
    counts = {"posted": 0, "seen": 0, "non_country": 0,
              "no_intern": 0, "blocked": 0, "no_title": 0}
    new_rows: list[dict] = []

    for row in rows:
        gid = row.get("global_id")
        if not gid:
            continue
        if gid in seen:
            counts["seen"] += 1
            continue
        if not is_in_country(row, cfg.country):
            counts["non_country"] += 1
            continue
        reason = matches_role(row, cfg)
        if reason != "ok":
            counts[reason] += 1
            continue

        if sb is not None and not write_to_supabase(sb, row, source):
            continue

        seen.add(row, source)
        new_rows.append(row)
        counts["posted"] += 1

    return counts, new_rows


# =========================================================================== #
# Modes
# =========================================================================== #

def _fetch_one_target(t: Target) -> tuple[Target, list[dict], Exception | None, float]:
    """Fetch a single target. Runs inside a worker thread."""
    start = time.monotonic()
    try:
        jobs = get_scraper(t.ats, t.slug).fetch()
    except Exception as e:
        return (t, [], e, time.monotonic() - start)
    out: list[dict] = []
    for job in jobs or []:
        try:
            out.append(job_to_dict(job))
        except TypeError:
            pass
    return (t, out, None, time.monotonic() - start)


def live_check(seen: SeenStore, sb: Client | None, cfg: Config | None = None) -> None:
    if cfg is None:
        cfg = load_config(CONFIG_DIR, sb)
    live_log.info("Live scrape of %d targets (workers=%d)…", len(cfg.targets), SCRAPE_WORKERS)
    rows: list[dict] = []
    failed = 0
    started = time.monotonic()

    with ThreadPoolExecutor(max_workers=SCRAPE_WORKERS) as ex:
        futures = {ex.submit(_fetch_one_target, t): t for t in cfg.targets}
        for fut in as_completed(futures):
            t = futures[fut]
            try:
                _, target_rows, err, elapsed = fut.result(timeout=SCRAPE_TIMEOUT_SEC)
            except Exception as e:
                live_log.warning("%s/%s timed out or crashed: %s", t.ats, t.slug, e)
                failed += 1
                continue
            if err is not None:
                live_log.warning("%s/%s scraper failed in %.1fs: %s", t.ats, t.slug, elapsed, err)
                failed += 1
                continue
            rows.extend(target_rows)
            if elapsed > 30:
                live_log.info("%s/%s slow: %.1fs, %d jobs", t.ats, t.slug, elapsed, len(target_rows))

    live_log.info(
        "Collected %d candidate rows from %d targets (%d failed) in %.1fs",
        len(rows), len(cfg.targets) - failed, failed, time.monotonic() - started,
    )
    c, new_rows = process_rows(rows, "live", seen, cfg, sb)
    live_log.info(
        "Posted %d  (seen=%d, non-%s=%d, no_intern=%d, blocked=%d, no_title=%d)",
        c["posted"], c["seen"], cfg.country, c["non_country"],
        c["no_intern"], c["blocked"], c["no_title"],
    )
    send_run_summary("live", new_rows)


def dataset_check(seen: SeenStore, sb: Client | None, cfg: Config | None = None) -> None:
    if cfg is None:
        cfg = load_config(CONFIG_DIR, sb)
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
    c, new_rows = process_rows(list(by_id.values()), "dataset", seen, cfg, sb)
    ds_log.info(
        "Posted %d  (seen=%d, non-%s=%d, no_intern=%d, blocked=%d, no_title=%d)",
        c["posted"], c["seen"], cfg.country, c["non_country"],
        c["no_intern"], c["blocked"], c["no_title"],
    )
    send_run_summary("dataset", new_rows)


# =========================================================================== #
# Entrypoint
# =========================================================================== #

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once-live", action="store_true", help="One live scrape, then exit")
    parser.add_argument("--once-dataset", action="store_true", help="One dataset sweep, then exit")
    parser.add_argument("--once", action="store_true", help="Both passes once, then exit")
    args = parser.parse_args()

    sb = get_supabase()
    seen = SeenStore(SEEN_CSV, sb)
    cfg = load_config(CONFIG_DIR, sb)  # one-time startup load just for the boot log
    log.info(
        "Config: %d targets, %d queries, country=%s, seen=%d, supabase=%s, discord=%s, email=%s",
        len(cfg.targets), len(cfg.dataset_queries), cfg.country, len(seen._ids),
        "on" if sb else "off",
        "on" if WEBHOOK_URL else "off",
        "on" if (RESEND_API_KEY and NOTIFY_EMAIL) else "off",
    )

    if args.once_live:
        live_check(seen, sb, cfg); return
    if args.once_dataset:
        dataset_check(seen, sb, cfg); return
    if args.once:
        live_check(seen, sb, cfg); dataset_check(seen, sb, cfg); return

    # Long-running mode: each scheduled tick reloads config so webapp edits
    # take effect on the next run without restarting the service.
    live_check(seen, sb, cfg)
    dataset_check(seen, sb, cfg)

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(lambda: live_check(seen, sb),    "interval",
                      minutes=LIVE_POLL_MINUTES,  max_instances=1, id="live")
    scheduler.add_job(lambda: dataset_check(seen, sb), "interval",
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

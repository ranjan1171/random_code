"""
run_greenhouse.py — Unified Greenhouse Pipeline: Scrape → Deduplicate → Apply

Single entry point that:
  1. Purges already-applied / processed jobs from JSON
  2. Scrapes 500+ Greenhouse companies dynamically
  3. Scores + deduplicates (DB + JSON + in-memory set)
  4. Applies sequentially to all new matched jobs
  5. Updates JSON + DB after every apply

Usage:
    python run_greenhouse.py                          # full pipeline
    python run_greenhouse.py --scrape-only            # scrape & score, no apply
    python run_greenhouse.py --apply-only             # apply from existing JSON
    python run_greenhouse.py --query "kafka python" --location "India" --min-score 65
    python run_greenhouse.py --max-apply 50           # cap apply run to N jobs
"""

import argparse
import asyncio
import json
import logging
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Set

# ── Path bootstrap ────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from config import APPLICATION, DB_PATH, MATCHING, PROFILE
from db.database import Database
from matcher.scorer import is_good_match, score_job
from scrapers.greenhouse_scraper import GreenhouseScraper
from applier.greenhouse_applier import GreenhouseApplier

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_greenhouse")

# ── Paths ─────────────────────────────────────────────────────────────────────
JSON_PATH = BASE_DIR / "greenhouse_matched_jobs.json"


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 1 — Deduplication helpers
# ═════════════════════════════════════════════════════════════════════════════

def _load_applied_ids_from_db(db_path: Path) -> Set[str]:
    """Return every job_id already recorded in the applications table."""
    applied: Set[str] = set()
    try:
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT job_id FROM applications").fetchall()
        conn.close()
        applied = {str(r[0]) for r in rows}
    except Exception as exc:
        logger.debug(f"DB read warning: {exc}")
    return applied


def _load_json_state(json_path: Path) -> Dict[str, Any]:
    """Load existing JSON file or return a blank scaffold."""
    if json_path.exists():
        try:
            with json_path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception as exc:
            logger.warning(f"Could not parse {json_path}: {exc} — starting fresh")
    return {"matched_jobs": []}


def _save_json(json_path: Path, data: Dict[str, Any]) -> None:
    with json_path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def _purge_and_collect_known_ids(
    data: Dict[str, Any],
    db_applied: Set[str],
) -> tuple[Dict[str, Any], Set[str]]:
    """
    Mark stale entries as applied and return:
      - updated data dict (every job present, stale ones flagged)
      - set of ALL known job IDs (DB + JSON) — used to skip during scrape
    """
    known_ids: Set[str] = set(db_applied)
    updated = 0
    clean_jobs: List[Dict] = []

    for j in data.get("matched_jobs", []):
        jid = str(j.get("id", ""))
        if jid in db_applied or j.get("applied") or j.get("processed"):
            j["applied"] = True
            updated += 1
            if jid:
                known_ids.add(jid)
        else:
            if jid:
                known_ids.add(jid)
        clean_jobs.append(j)

    data["matched_jobs"] = clean_jobs
    if updated:
        logger.info(f"🧹 Marked {updated} stale / already-applied jobs in JSON.")
    return data, known_ids


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 2 — Scrape + Score
# ═════════════════════════════════════════════════════════════════════════════

async def run_scrape(
    query: str,
    location: str,
    min_score: float,
    known_ids: Set[str],
    db: Database,
) -> List[Dict[str, Any]]:
    """
    Scrape Greenhouse, score every job, skip duplicates, persist new matches.
    Returns the full list of new matched jobs (score >= min_score, not duplicate).
    """
    scraper = GreenhouseScraper()
    logger.info("🌐 Discovering Greenhouse jobs …")

    all_jobs: List[Dict] = await scraper.search(query=query, location=location)
    await scraper.client.aclose()

    total_fetched = len(all_jobs)
    logger.info(f"📥 Fetched {total_fetched} raw listings from Greenhouse.")

    if not all_jobs:
        return []

    new_matches: List[Dict] = []
    skipped_dup = 0
    skipped_score = 0
    skipped_dealbreaker = 0

    for job in all_jobs:
        jid = str(job.get("id", ""))

        # ── Dedup ────────────────────────────────────────────────────
        if jid and jid in known_ids:
            skipped_dup += 1
            continue

        # ── Score ────────────────────────────────────────────────────
        score, details = score_job(job)
        job["score"] = round(score, 1)
        job["match_details"] = details
        job["is_dealbreaker"] = details.get("is_dealbreaker", False)
        job["scraped_at"] = datetime.now().isoformat()
        job["applied"] = False

        if job["is_dealbreaker"]:
            skipped_dealbreaker += 1
            if jid:
                known_ids.add(jid)
            continue

        if score < min_score:
            skipped_score += 1
            if jid:
                known_ids.add(jid)
            continue

        # ── New match ────────────────────────────────────────────────
        if jid:
            known_ids.add(jid)
        new_matches.append(job)
        db.upsert_job(job)

    logger.info(
        f"✅ Scoring done | new matches: {len(new_matches)} | "
        f"duplicates skipped: {skipped_dup} | "
        f"below threshold: {skipped_score} | "
        f"dealbreakers: {skipped_dealbreaker}"
    )
    return new_matches


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 3 — Merge new jobs into JSON
# ═════════════════════════════════════════════════════════════════════════════

def _merge_into_json(
    data: Dict[str, Any],
    new_matches: List[Dict],
    min_score: float,
    total_fetched: int,
) -> Dict[str, Any]:
    """
    Append new matches to the JSON store and refresh metadata.
    Existing entries (applied or not) are kept; only genuinely new ones added.
    """
    existing_ids = {str(j.get("id", "")) for j in data.get("matched_jobs", [])}
    added = 0
    for j in new_matches:
        if str(j.get("id", "")) not in existing_ids:
            data["matched_jobs"].append(j)
            added += 1

    # Sort all pending jobs by score desc so the best ones apply first
    pending = [j for j in data["matched_jobs"] if not j.get("applied")]
    applied_done = [j for j in data["matched_jobs"] if j.get("applied")]
    pending.sort(key=lambda x: x.get("score", 0), reverse=True)
    data["matched_jobs"] = pending + applied_done

    data["last_scraped_at"] = datetime.now().isoformat()
    data["total_fetched"] = total_fetched
    data["total_matched_pending"] = len(pending)
    data["min_score_threshold"] = min_score

    logger.info(f"📝 JSON updated: +{added} new jobs | {len(pending)} pending.")
    return data


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 4 — Batch Apply
# ═════════════════════════════════════════════════════════════════════════════

async def run_apply(
    data: Dict[str, Any],
    db: Database,
    max_apply: int,
    json_path: Path,
) -> tuple[int, int]:
    """
    Apply sequentially to all pending jobs. Writes JSON after every job.
    Returns (applied_count, failed_count).
    """
    APPLICATION["headless"] = False  # keep browser visible for CAPTCHA / verification

    pending = [
        j for j in data.get("matched_jobs", [])
        if not j.get("applied") and not j.get("processed")
    ]

    if not pending:
        logger.info("🎉 No pending jobs — nothing to apply to.")
        return 0, 0

    if max_apply and max_apply < len(pending):
        logger.info(f"⚡ Capping this run to {max_apply} jobs (--max-apply).")
        pending = pending[:max_apply]

    applier = GreenhouseApplier()
    applied_count = 0
    failed_count = 0

    print("\n" + "=" * 70)
    print(f"  🚀 Greenhouse Batch Applier")
    print(f"  Jobs to apply:  {len(pending)}")
    print(f"  Profile:        {PROFILE.get('name', 'Ranjan Kumar')}")
    print("=" * 70 + "\n")

    for idx, job in enumerate(pending, 1):
        score   = job.get("score", 0)
        title   = job.get("title", "")
        company = job.get("company", "")
        url     = job.get("url", "")
        jid     = str(job.get("id", ""))

        print(f"\n{'─' * 70}")
        print(f"  [{idx}/{len(pending)}] {title} @ {company}")
        print(f"  Score: {score}%  |  URL: {url}")
        print("─" * 70)

        try:
            result = await applier.apply(job)
        except Exception as exc:
            logger.error(f"Applier raised unexpected error: {exc}", exc_info=True)
            result = {"success": False, "status": "error", "message": str(exc)}

        success = result.get("success", False)
        status  = result.get("status", "failed")
        msg     = result.get("message", "")

        # ── Mark job in data dict ─────────────────────────────────────
        for stored_job in data["matched_jobs"]:
            if str(stored_job.get("id", "")) == jid:
                stored_job["applied"]    = True
                stored_job["processed"]  = True
                stored_job["applied_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                if not success:
                    stored_job["failure_reason"] = msg
                break

        # ── Persist to DB ─────────────────────────────────────────────
        db.record_application(
            job_id=jid,
            portal="greenhouse",
            application_url=url,
            cover_letter="",
            cv_version="default",
            notes=msg,
            status=status,
        )

        # ── Flush JSON immediately so we never lose progress ──────────
        _save_json(json_path, data)

        if success:
            applied_count += 1
            print(f"  ✅ APPLIED: {title} @ {company}")
        else:
            failed_count += 1
            print(f"  ⚠️  STATUS: {status} — {msg}")

        # Human-like delay between applications
        if idx < len(pending):
            delay = 3
            print(f"\n  ⏳ Waiting {delay}s …\n")
            await asyncio.sleep(delay)

    return applied_count, failed_count


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 5 — Main orchestrator
# ═════════════════════════════════════════════════════════════════════════════

async def main(
    query: str        = "",
    location: str     = "",
    min_score: float  = 60.0,
    scrape_only: bool = False,
    apply_only: bool  = False,
    max_apply: int    = 0,
) -> None:
    print("\n" + "=" * 70)
    print("  🌱 Greenhouse Pipeline  (scrape → deduplicate → apply)")
    print(f"  Profile  : {PROFILE.get('name', 'Ranjan Kumar')}")
    print(f"  Min score: {min_score}%")
    print(f"  Mode     : {'scrape-only' if scrape_only else 'apply-only' if apply_only else 'full pipeline'}")
    print("=" * 70 + "\n")

    db = Database(DB_PATH)

    # ── Step 1: Load current state ────────────────────────────────────
    data       = _load_json_state(JSON_PATH)
    db_applied = _load_applied_ids_from_db(DB_PATH)
    data, known_ids = _purge_and_collect_known_ids(data, db_applied)
    _save_json(JSON_PATH, data)   # persist the purge immediately

    total_fetched = 0

    # ── Step 2: Scrape (unless --apply-only) ─────────────────────────
    if not apply_only:
        new_matches = await run_scrape(query, location, min_score, known_ids, db)
        total_fetched = len(new_matches)  # rough; scraper returns raw list
        data = _merge_into_json(data, new_matches, min_score, total_fetched)
        _save_json(JSON_PATH, data)

        # Print match table
        pending = [j for j in data["matched_jobs"] if not j.get("applied")]
        print(f"\n{'=' * 70}")
        print(f"  🎯 PENDING JOBS ({len(pending)} total, score ≥ {min_score}%)")
        print(f"{'=' * 70}")
        for idx, j in enumerate(pending[:30], 1):
            print(
                f"  {idx:2d}. [{j['score']:5.1f}%] "
                f"{j['title'][:38]:<38} @ {j['company'][:20]:<20} ({j.get('location','')[:18]})"
            )
        if len(pending) > 30:
            print(f"  … and {len(pending) - 30} more (see {JSON_PATH.name})")
        print(f"{'=' * 70}\n")

    if scrape_only:
        print("💾 Scrape-only mode — exiting without applying.")
        return

    # ── Step 3: Apply ─────────────────────────────────────────────────
    applied_count, failed_count = await run_apply(data, db, max_apply, JSON_PATH)

    # ── Step 4: Final summary ─────────────────────────────────────────
    pending_after = len([j for j in data["matched_jobs"] if not j.get("applied")])
    print("\n" + "=" * 70)
    print("  🏁 PIPELINE COMPLETE")
    print(f"  Successfully applied : {applied_count}")
    print(f"  Failed / skipped     : {failed_count}")
    print(f"  Still pending        : {pending_after}")
    print(f"  JSON saved to        : {JSON_PATH.resolve()}")
    print("=" * 70 + "\n")


# ═════════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Unified Greenhouse scrape → deduplicate → apply pipeline"
    )
    parser.add_argument("--query",       type=str,   default="",    help="Job title / skill filter")
    parser.add_argument("--location",    type=str,   default="",    help="Location filter (e.g. 'India')")
    parser.add_argument("--min-score",   type=float, default=60.0,  help="Minimum match score %% (default 60)")
    parser.add_argument("--scrape-only", action="store_true",       help="Scrape and score only, skip applying")
    parser.add_argument("--apply-only",  action="store_true",       help="Apply from existing JSON, skip scraping")
    parser.add_argument("--max-apply",   type=int,   default=0,     help="Max jobs to apply this run (0 = no limit)")
    args = parser.parse_args()

    asyncio.run(main(
        query       = args.query,
        location    = args.location,
        min_score   = args.min_score,
        scrape_only = args.scrape_only,
        apply_only  = args.apply_only,
        max_apply   = args.max_apply,
    ))
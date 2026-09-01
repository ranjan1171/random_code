"""
run_dashboard_and_apply.py — Start dashboard on localhost:5000 + apply continuously to all remaining Greenhouse jobs.

Usage:
    python run_dashboard_and_apply.py
"""

import asyncio
import json
import logging
import os
import re
import sys
import threading
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))
os.chdir(str(BASE_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(name)s - %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler("logs/run_dashboard_and_apply.log", encoding="utf-8", mode="a"),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger("runner")

from config import DB_PATH, PROFILE, DASHBOARD_PORT, APPLICATION
from db.database import Database
from dashboard.app import run_dashboard
from applier.greenhouse_applier import GreenhouseApplier

APPLICATION["headless"] = False


def log_live_activity(message: str, level: str = "info"):
    """Write to activity log so dashboard displays it live."""
    try:
        with open("logs/activity.log", "a", encoding="utf-8") as f:
            ts = datetime.now().strftime("%H:%M:%S")
            f.write(f"[{ts}] [{level.upper()}] {message}\n")
    except Exception:
        pass


def start_dashboard_thread(db: Database, port: int = 5000):
    """Start Flask dashboard in a background daemon thread."""
    def _run():
        try:
            run_dashboard(db, orchestrator=None, port=port)
        except Exception as e:
            logger.error(f"Dashboard error: {e}")

    t = threading.Thread(target=_run, daemon=True, name="dashboard")
    t.start()
    logger.info(f"✅ Dashboard started at http://localhost:{port}")
    return t


async def apply_remaining_jobs(db: Database):
    """Continuously apply to all remaining unapplied Greenhouse jobs."""

    # 1. Load jobs
    json_path = BASE_DIR / "greenhouse_matched_jobs.json"
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    jobs = data.get("matched_jobs", data) if isinstance(data, dict) else data

    # 2. Get comprehensive set of applied IDs, URLs, and unique Job Tokens from DB
    with db._get_conn() as conn:
        db_records = conn.execute(
            "SELECT job_id, application_url FROM applications WHERE status='applied'"
        ).fetchall()
        applied_ids = {str(r[0]) for r in db_records if r[0]}
        applied_urls = {str(r[1]).lower().strip() for r in db_records if r[1]}
        
        # Extract numerical tokens (e.g. 8106815, 8741978002)
        applied_tokens = set()
        for r in db_records:
            for text in [str(r[0]), str(r[1])]:
                applied_tokens.update(re.findall(r'\d{6,}', text))

    # 3. 5-Layer Bulletproof Deduplication & Dealbreaker Filtering
    dealbreakers = PROFILE.get("dealbreakers", [])
    unapplied = []
    for j in jobs:
        jid = str(j.get("id", ""))
        url = str(j.get("url", "")).lower().strip()
        tokens = set(re.findall(r'\d{6,}', f"{jid} {url}"))
        
        # 5-Layer Duplicate check:
        is_already_applied = (
            jid in applied_ids
            or url in applied_urls
            or j.get("applied") is True
            or j.get("status") == "applied"
            or bool(tokens & applied_tokens)
        )
        if is_already_applied:
            continue
            
        title_lower = (j.get("title") or "").lower()
        desc_lower = (j.get("description") or "").lower()[:500]
        combined = f"{title_lower} {desc_lower}"
        if any(db_kw in combined for db_kw in dealbreakers):
            continue
            
        unapplied.append(j)

    logger.info(f"Found {len(unapplied)} verified fresh unapplied jobs (100% deduplicated against {len(db_records)} DB records).")
    log_live_activity(f"Found {len(unapplied)} unapplied jobs to process.", "info")

    if not unapplied:
        logger.info("All matched jobs have already been applied!")
        log_live_activity("All matched jobs have already been applied!", "info")
        return []

    applier = GreenhouseApplier()
    applied_count = 0
    results = []

    for idx, job in enumerate(unapplied, 1):
        title = job.get("title", "Unknown")
        company = job.get("company", "Unknown")
        job_id = job.get("id") or f"{company}_{idx}"
        url = job.get("url")
        score = job.get("score", 0)

        logger.info("\n" + "=" * 70)
        logger.info(f"[{idx}/{len(unapplied)}] Applying: {title} @ {company} (Score: {score}%)")
        logger.info(f"URL: {url}")
        logger.info("=" * 70)
        log_live_activity(f"Applying [{idx}/{len(unapplied)}]: {title} @ {company}", "info")

        try:
            res = await applier.apply(job)
            success = res.get("success", False)
            status = res.get("status", "failed")
            msg = res.get("message", "")

            results.append({
                "index": idx,
                "company": company,
                "title": title,
                "url": url,
                "success": success,
                "status": status,
                "message": msg
            })

            if success:
                logger.info(f"✅ SUCCESS: {title} @ {company} — {msg}")
                log_live_activity(f"✅ SUCCESS: {title} @ {company}", "success")
                
                db.record_application(
                    job_id=str(job_id),
                    portal="greenhouse",
                    application_url=url,
                    status="applied"
                )
                job["applied"] = True
                job["status"] = "applied"
                job["applied_at"] = datetime.now().isoformat()
                applied_count += 1
                
                # Persist JSON progress
                try:
                    with open(json_path, "w", encoding="utf-8") as f:
                        if isinstance(data, dict):
                            data["matched_jobs"] = jobs
                            json.dump(data, f, indent=2)
                        else:
                            json.dump(jobs, f, indent=2)
                except Exception as je:
                    logger.debug(f"JSON save error: {je}")

            else:
                logger.warning(f"❌ NOT APPLIED: {title} @ {company} — {msg}")
                log_live_activity(f"❌ SKIPPED: {title} @ {company} ({msg[:60]})", "warning")

        except Exception as e:
            logger.error(f"💥 Error on {title} @ {company}: {e}")
            log_live_activity(f"💥 Error on {company}: {e}", "error")
            results.append({
                "index": idx,
                "company": company,
                "title": title,
                "url": url,
                "success": False,
                "status": "crashed",
                "message": str(e)
            })

        await asyncio.sleep(3)

    await applier.close()
    logger.info(f"\nCompleted run! Total new applications submitted: {applied_count}")
    log_live_activity(f"Completed run! Total submitted: {applied_count}", "info")
    return results


def main():
    db = Database(DB_PATH)

    port = 5000
    start_dashboard_thread(db, port=port)

    import time
    time.sleep(1)

    logger.info(f"\n{'='*70}")
    logger.info(f"Dashboard running at: http://localhost:{port}")
    logger.info(f"Starting continuous job application runner...")
    logger.info(f"{'='*70}\n")

    results = asyncio.run(apply_remaining_jobs(db))

    logger.info(f"\n{'='*70}")
    logger.info(f"Pipeline complete! Dashboard still running at http://localhost:{port}")
    logger.info(f"Press Ctrl+C to stop.")
    logger.info(f"{'='*70}\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")


if __name__ == "__main__":
    main()

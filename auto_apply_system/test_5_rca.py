"""
Test runner for 5 jobs with deep RCA logging and blocker pinpointing.
Enforces rule: never re-apply to already successfully applied jobs.
"""
import asyncio
import json
import logging
import os
import sys
import time

# Ensure proper path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import PROFILE, DB_PATH
from applier.greenhouse_applier import GreenhouseApplier
from db.database import Database

# Configure clear logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)-7s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("rca_runner")

JSON_PATH = "greenhouse_matched_jobs.json"

def get_unapplied_jobs(limit=5):
    if not os.path.exists(JSON_PATH):
        logger.error(f"File not found: {JSON_PATH}")
        return []
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    all_jobs = data.get("matched_jobs", [])
    
    # Check SQLite DB to be 100% sure we don't re-apply
    db = Database(DB_PATH)
    applied_urls = set()
    try:
        with db._get_conn() as conn:
            rows = conn.execute("""
                SELECT j.url FROM jobs j
                JOIN applications a ON a.job_id = j.id
                WHERE a.status IN ('applied', 'applied_live', 'success')
            """).fetchall()
            for r in rows:
                if r[0]:
                    applied_urls.add(r[0].strip())
    except Exception as e:
        logger.warning(f"Could not read DB applied jobs: {e}")

    unapplied = []
    for j in all_jobs:
        url = j.get("url", "").strip()
        is_json_applied = j.get("applied") and j.get("success")
        is_db_applied = url in applied_urls
        if not is_json_applied and not is_db_applied:
            unapplied.append(j)
            if len(unapplied) == limit:
                break
    return unapplied

def update_job_status(job, success: bool, reason: str = ""):
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    for j in data.get("matched_jobs", []):
        if j.get("url") == job.get("url"):
            j["applied"] = True
            j["success"] = success
            j["processed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            if not success:
                j["failure_reason"] = reason
            else:
                j.pop("failure_reason", None)
            break
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

async def main():
    jobs = get_unapplied_jobs(5)
    if not jobs:
        logger.info("No unapplied jobs found!")
        return

    logger.info(f"Loaded {len(jobs)} unapplied jobs for RCA test batch.")
    for idx, j in enumerate(jobs, 1):
        logger.info(f"  [{idx}] {j.get('title')} @ {j.get('company')} (URL: {j.get('url')})")

    applier = GreenhouseApplier()
    
    results = []
    for idx, job in enumerate(jobs, 1):
        title = job.get("title", "Unknown")
        company = job.get("company", "Unknown")
        url = job.get("url", "")
        
        logger.info("\n" + "="*70)
        logger.info(f"[{idx}/5] TESTING: {title} @ {company}")
        logger.info(f"URL: {url}")
        logger.info("="*70)
        
        t0 = time.time()
        try:
            res = await applier.apply(job)
            elapsed = time.time() - t0
            success = res.get("success", False)
            status = res.get("status", "unknown")
            msg = res.get("message", "")
            
            logger.info(f"\nRESULT for [{idx}/5] {title} @ {company}:")
            logger.info(f"  Success: {success}")
            logger.info(f"  Status : {status}")
            logger.info(f"  Message: {msg}")
            logger.info(f"  Elapsed: {elapsed:.1f}s")
            
            update_job_status(job, success=success, reason=msg)
            results.append({
                "job": f"{title} @ {company}",
                "success": success,
                "status": status,
                "message": msg,
                "elapsed": f"{elapsed:.1f}s"
            })
        except Exception as e:
            elapsed = time.time() - t0
            logger.error(f"EXCEPTION for [{idx}/5] {title} @ {company}: {e}", exc_info=True)
            update_job_status(job, success=False, reason=str(e))
            results.append({
                "job": f"{title} @ {company}",
                "success": False,
                "status": "error",
                "message": str(e),
                "elapsed": f"{elapsed:.1f}s"
            })
        
        # Brief pause between jobs
        await asyncio.sleep(2)

    await applier.close()
    
    logger.info("\n" + "="*70)
    logger.info("RCA BATCH SUMMARY (5 JOBS)")
    logger.info("="*70)
    for r in results:
        mark = "✓ SUCCESS" if r["success"] else "✗ FAILED "
        logger.info(f"{mark} | {r['job']} | {r['message']} ({r['elapsed']})")
    logger.info("="*70)

if __name__ == "__main__":
    asyncio.run(main())

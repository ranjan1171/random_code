"""
apply_diverse_5.py — Apply to 5 unapplied jobs from 5 DIFFERENT companies.
Never repeats already applied jobs (checked via SQLite DB and applied flag).
"""

import asyncio
import json
import logging
import os
import sys
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
LOG_FILE = "logs/diverse_5.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(name)s - %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8", mode="a"),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger("diverse_5")

from config import DB_PATH, PROFILE
from db.database import Database
from applier.greenhouse_applier import GreenhouseApplier

async def main():
    db = Database(DB_PATH)
    
    # 1. Load jobs
    with open("greenhouse_matched_jobs.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    jobs = data.get("matched_jobs", data) if isinstance(data, dict) else data

    # 2. Get set of applied job IDs from DB
    with db._get_conn() as conn:
        applied_ids = {row[0] for row in conn.execute("SELECT job_id FROM applications WHERE status='applied'").fetchall()}

    # 3. Filter unapplied AND filter out dealbreaker titles (Senior, Staff, Lead etc.)
    dealbreakers = PROFILE.get("dealbreakers", [])
    unapplied = []
    for j in jobs:
        if str(j.get("id")) in applied_ids or j.get("applied"):
            continue
        title_lower = (j.get("title") or "").lower()
        desc_lower = (j.get("description") or "").lower()[:500]
        combined = f"{title_lower} {desc_lower}"
        is_dealbreaker = any(db in combined for db in dealbreakers)
        if is_dealbreaker:
            continue
        unapplied.append(j)
    
    logger.info(f"Found {len(unapplied)} unapplied jobs after dealbreaker filtering")
    
    # 4. Pick 5 diverse companies
    selected_5 = []
    seen_companies = set()
    for j in unapplied:
        company = (j.get("company") or "Unknown").strip()
        if company not in seen_companies:
            selected_5.append(j)
            seen_companies.add(company)
            if len(selected_5) == 5:
                break
                
    if len(selected_5) < 5:
        for j in unapplied:
            if j not in selected_5:
                selected_5.append(j)
                if len(selected_5) == 5:
                    break

    logger.info("=" * 70)
    logger.info(f"Targeting 5 Diverse Unapplied Jobs across different companies:")
    for idx, j in enumerate(selected_5, 1):
        logger.info(f"  {idx}. [{j.get('company')}] {j.get('title')}")
        logger.info(f"     URL: {j.get('url')}")
    logger.info("=" * 70)

    applier = GreenhouseApplier()
    results = []

    for idx, job in enumerate(selected_5, 1):
        title = job.get("title", "Unknown")
        company = job.get("company", "Unknown")
        job_id = job.get("id")
        url = job.get("url")

        logger.info("\n" + "-" * 70)
        logger.info(f"[{idx}/5] Applying to: {title} @ {company}")
        logger.info(f"URL: {url}")
        logger.info("-" * 70)

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
                logger.info(f"✅ SUCCESS: {title} @ {company}")
                # Update DB and JSON
                db.record_application(
                    job_id=str(job_id),
                    portal="greenhouse",
                    application_url=url,
                    status="applied"
                )
                job["applied"] = True
                job["status"] = "applied"
                job["applied_at"] = datetime.now().isoformat()
            else:
                logger.warning(f"❌ FAILED: {title} @ {company} — {msg}")

        except Exception as e:
            logger.error(f"💥 CRASH on {title} @ {company}: {e}")
            results.append({
                "index": idx,
                "company": company,
                "title": title,
                "url": url,
                "success": False,
                "status": "crashed",
                "message": str(e)
            })

        await asyncio.sleep(2)

    # Save updated JSON
    if isinstance(data, dict):
        data["matched_jobs"] = jobs
        with open("greenhouse_matched_jobs.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    else:
        with open("greenhouse_matched_jobs.json", "w", encoding="utf-8") as f:
            json.dump(jobs, f, indent=2)

    logger.info("\n" + "=" * 70)
    logger.info("FINAL 5 DIVERSE JOBS SUMMARY:")
    for r in results:
        status_icon = "✅" if r["success"] else "❌"
        logger.info(f"  {status_icon} [{r['company']}] {r['title']} -> {r['status']} ({r['message']})")
    logger.info("=" * 70)

    # Clean up browser
    await applier.close()

if __name__ == "__main__":
    asyncio.run(main())

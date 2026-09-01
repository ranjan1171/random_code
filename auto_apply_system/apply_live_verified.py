"""
apply_live_verified.py — Run live verified applications using GreenhouseApplier with visible browser.
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

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
        logging.FileHandler("logs/live_verified_apply.log", encoding="utf-8", mode="a"),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger("live_apply")

from config import DB_PATH, PROFILE, APPLICATION
from db.database import Database
from applier.greenhouse_applier import GreenhouseApplier

# Non-headless mode to see form interactions and confirmation
APPLICATION["headless"] = False


async def main():
    db = Database(DB_PATH)
    
    target_jobs = [
        {
            "title": "Intermediate Backend Engineer - Database Change Management",
            "company": "GitLab",
            "url": "https://job-boards.greenhouse.io/gitlab/jobs/8722304002",
            "portal": "greenhouse"
        },
        {
            "title": "Software Engineer - Data Movement Platform",
            "company": "Reddit",
            "url": "https://job-boards.greenhouse.io/reddit/jobs/7997866",
            "portal": "greenhouse"
        },
        {
            "title": "Software Engineer, AI Enablement",
            "company": "Chime",
            "url": "https://boards.greenhouse.io/chime/jobs/8578967002?gh_jid=8578967002",
            "portal": "greenhouse"
        },
        {
            "title": "Software Engineer, ML Platform",
            "company": "Gusto",
            "url": "https://job-boards.greenhouse.io/gusto/jobs/8073232",
            "portal": "greenhouse"
        },
        {
            "title": "Software Engineer (Backend), Enterprise",
            "company": "Scale AI",
            "url": "https://job-boards.greenhouse.io/scaleai/jobs/4630032005",
            "portal": "greenhouse"
        }
    ]
    
    applier = GreenhouseApplier()
    
    for idx, job in enumerate(target_jobs, 1):
        logger.info("\n" + "=" * 70)
        logger.info(f"[{idx}/{len(target_jobs)}] LIVE APPLYING TO: {job['title']} @ {job['company']}")
        logger.info(f"URL: {job['url']}")
        logger.info("=" * 70)
        
        try:
            result = await applier.apply(job)
            success = result.get("success", False)
            status = result.get("status", "failed")
            msg = result.get("message", "")
            
            if success:
                logger.info(f"✅ CONFIRMED APPLIED: {job['title']} @ {job['company']} — {msg}")
                db.record_application(
                    job_id=str(job.get("id", f"{job['company']}_{idx}")),
                    portal="greenhouse",
                    application_url=job["url"],
                    status="applied"
                )
            else:
                logger.warning(f"❌ APPLICATION NOT COMPLETED: {job['title']} @ {job['company']} — {msg}")
        except Exception as e:
            logger.error(f"Error during application: {e}", exc_info=True)
            
        await asyncio.sleep(4)
        
    await applier.close()
    logger.info("\nAll target applications processed.")


if __name__ == "__main__":
    asyncio.run(main())

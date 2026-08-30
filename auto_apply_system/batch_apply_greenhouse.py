"""
batch_apply_greenhouse.py — Batch Runner for Greenhouse Auto-Applier.

Applies sequentially to all matched jobs in `greenhouse_matched_jobs.json`
starting from the highest match score.
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import List, Dict, Any

# Setup paths
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from config import DB_PATH, APPLICATION
from db.database import Database
from applier.greenhouse_applier import GreenhouseApplier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("batch_apply_greenhouse")


async def main():
    json_path = BASE_DIR / "greenhouse_matched_jobs.json"
    if not json_path.exists():
        print(f"❌ File not found: {json_path}")
        print("Run `python scrape_greenhouse.py` first.")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    jobs: List[Dict[str, Any]] = data.get("matched_jobs", [])
    if not jobs:
        print("❌ No matched jobs found in JSON file.")
        return

    # Ensure browser is visible so human verification / screenshots work smoothly
    APPLICATION["headless"] = False

    db = Database(DB_PATH)
    applier = GreenhouseApplier()

    # Filter out already applied jobs
    pending_jobs = []
    for j in jobs:
        if j.get("applied") or db.already_applied(j["id"]):
            continue
        pending_jobs.append(j)

    print("\n" + "=" * 70)
    print("  🚀 Greenhouse Auto-Applier — Sequential Batch")
    print(f"  Total matched jobs in file: {len(jobs)}")
    print(f"  Jobs remaining to apply:  {len(pending_jobs)}")
    print("=" * 70 + "\n")

    if not pending_jobs:
        print("🎉 All matched jobs have already been applied to!")
        return

    applied_count = 0
    failed_count = 0

    for idx, job in enumerate(pending_jobs, 1):
        score = job.get("score", 0)
        title = job.get("title", "")
        company = job.get("company", "")
        url = job.get("url", "")

        print("\n" + "─" * 70)
        print(f"  [{idx}/{len(pending_jobs)}] Applying to: {title} @ {company}")
        print(f"  Score: {score}%  |  URL: {url}")
        print("─" * 70)

        result = await applier.apply(job)

        status = result.get("status", "failed")
        msg = result.get("message", "")

        if result.get("success"):
            applied_count += 1
            job["applied"] = True
            job["applied_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

            db.record_application(
                job_id=job["id"],
                portal="greenhouse",
                application_url=url,
                cover_letter="",
                cv_version="default",
                notes=msg,
                status="applied"
            )

            print(f"  ✅ SUCCESS: Applied to {title} @ {company}")
        else:
            failed_count += 1
            job["applied"] = True
            job["processed"] = True
            job["failed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            job["failure_reason"] = msg

            db.record_application(
                job_id=job["id"],
                portal="greenhouse",
                application_url=url,
                cover_letter="",
                cv_version="default",
                notes=msg,
                status=status
            )

            print(f"  ⚠️ STATUS: {status} — {msg}")

        # Update JSON file after each application
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        # Human-like pause between applications
        if idx < len(pending_jobs):
            delay = 2
            print(f"\n  ⏳ Delay {delay}s before next application...\n")
            await asyncio.sleep(delay)

    print("\n" + "=" * 70)
    print("  🏁 BATCH APPLICATION COMPLETE")
    print(f"  Successfully applied: {applied_count}")
    print(f"  Failed / skipped:    {failed_count}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())

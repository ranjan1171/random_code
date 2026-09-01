"""
watch_apply.py - Watch-Mode Batch Runner for Greenhouse Auto-Applier.

Applies to N jobs (default 15) with:
 - Live color terminal dashboard
 - Per-application RCA tracking
 - Full failure reason breakdown at end
 - Screenshots saved automatically
 - live_rca.json for external monitoring
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))
os.chdir(str(BASE_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

GREEN   = "\033[92m"
RED     = "\033[91m"
YELLOW  = "\033[93m"
CYAN    = "\033[96m"
MAGENTA = "\033[95m"
BLUE    = "\033[94m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
RESET   = "\033[0m"

os.makedirs("logs", exist_ok=True)
LOG_FILE = "logs/watch_apply.log"

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)-8s] %(name)s - %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8", mode="a"),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger("watch_apply")

from config import DB_PATH, APPLICATION
from db.database import Database
from applier.greenhouse_applier import GreenhouseApplier

rca = {
    "session_start": datetime.now().isoformat(),
    "total_attempted": 0,
    "succeeded": 0,
    "failed": 0,
    "applications": [],
    "failure_reasons": {},
}


def save_rca():
    try:
        with open(BASE_DIR / "logs" / "live_rca.json", "w", encoding="utf-8") as f:
            json.dump(rca, f, indent=2, default=str)
    except Exception:
        pass


def banner():
    now = datetime.now().strftime("%H:%M:%S")
    print(f"\n{BOLD}{CYAN}" + "="*70 + RESET)
    print(f"{BOLD}{CYAN}   GREENHOUSE AUTO-APPLIER - WATCH MODE  ({now}){RESET}")
    print(f"{BOLD}{CYAN}" + "="*70 + RESET + "\n")


def print_job_header(idx, total, job):
    title   = job.get("title", "Unknown")
    company = job.get("company", "Unknown")
    url     = job.get("url", "")
    score   = job.get("score", 0)
    print(f"\n{BOLD}{BLUE}" + "-"*70 + RESET)
    print(f"{BOLD}  [{idx}/{total}]  {title}  @  {company}{RESET}")
    print(f"  {DIM}Score: {score}%   URL: {url[:65]}{RESET}")
    print(f"{BOLD}{BLUE}" + "-"*70 + RESET)


def print_result(result, job, elapsed):
    title   = job.get("title", "")
    company = job.get("company", "")
    msg     = result.get("message", "")
    status  = result.get("status", "failed")
    if result.get("success"):
        print(f"\n{GREEN}{BOLD}  SUCCESS: {title} @ {company}{RESET}")
        print(f"  {GREEN}{msg}{RESET}")
    else:
        print(f"\n{RED}{BOLD}  FAILED : {title} @ {company}{RESET}")
        print(f"  {RED}Status : {status}{RESET}")
        print(f"  {RED}Reason : {msg}{RESET}")
    print(f"  {DIM}Elapsed: {elapsed:.1f}s{RESET}")


def print_running_summary():
    s  = rca["succeeded"]
    f  = rca["failed"]
    total = s + f
    rate  = (s / total * 100) if total > 0 else 0
    col = GREEN if rate >= 50 else RED
    print(f"\n{BOLD}{MAGENTA}  Running totals: {total} attempted | {s} OK | {f} FAILED | {col}{rate:.1f}%{RESET}{MAGENTA} success rate{RESET}")


def print_final_rca():
    print(f"\n\n{BOLD}{CYAN}" + "="*70 + RESET)
    print(f"{BOLD}{CYAN}   ROOT CAUSE ANALYSIS (RCA) - Session Complete{RESET}")
    print(f"{BOLD}{CYAN}" + "="*70 + RESET + "\n")
    total = rca["succeeded"] + rca["failed"]
    rate  = (rca["succeeded"] / total * 100) if total > 0 else 0
    col = GREEN if rate >= 50 else RED
    print(f"{BOLD}Overall Success Rate: {col}{rate:.1f}%{RESET}  ({rca['succeeded']}/{total})")
    if rca["failure_reasons"]:
        print(f"\n{BOLD}{YELLOW}--- Failure Reasons ---{RESET}")
        for reason, count in sorted(rca["failure_reasons"].items(), key=lambda x: -x[1]):
            print(f"  {RED}{count:2d}x{RESET}  {reason[:70]}")
    print(f"\n{BOLD}{YELLOW}--- Application Details ---{RESET}")
    for app in rca["applications"]:
        icon = "OK  " if app["success"] else "FAIL"
        msg  = app.get("message", "")[:50]
        print(f"  [{icon}]  {app['title'][:35]:<36} @ {app['company'][:20]:<21}  {DIM}{msg}{RESET}")
    print(f"\n{DIM}Full log: {LOG_FILE}{RESET}")
    print(f"{DIM}RCA JSON: logs/live_rca.json{RESET}")
    print(f"{DIM}Screenshots: logs/greenhouse_*.png{RESET}\n")


async def run_batch(n_jobs=15):
    json_path = BASE_DIR / "greenhouse_matched_jobs.json"
    if not json_path.exists():
        print(f"{RED}greenhouse_matched_jobs.json not found! Run scrape_greenhouse.py first.{RESET}")
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    all_jobs = data.get("matched_jobs", [])
    if not all_jobs:
        print(f"{RED}No matched jobs in JSON.{RESET}")
        sys.exit(1)

    APPLICATION["headless"] = False
    db      = Database(DB_PATH)
    applier = GreenhouseApplier()

    pending = [j for j in all_jobs if not j.get("applied") and not db.already_applied(j.get("id", ""))]
    pending = pending[:n_jobs]

    banner()
    print(f"  Total in JSON      : {len(all_jobs)}")
    print(f"  Pending (unapplied): {len(pending)}")
    print(f"  Will attempt       : {len(pending)}")
    print(f"\n  Log: {LOG_FILE}")
    print(f"  RCA: logs/live_rca.json (updates after each application)")
    print(f"\n  Starting in 3 seconds...")
    await asyncio.sleep(3)

    total = len(pending)
    for idx, job in enumerate(pending, 1):
        title   = job.get("title", "Unknown")
        company = job.get("company", "Unknown")
        url     = job.get("url", "")

        print_job_header(idx, total, job)
        logger.info(f"[RCA] START {idx}/{total}: {title} @ {company}")
        logger.info(f"[RCA] URL: {url}")

        t0 = time.time()
        try:
            result = await applier.apply(job)
        except Exception as exc:
            logger.exception(f"[RCA] UNCAUGHT: {title} @ {company}: {exc}")
            result = {"success": False, "status": "failed",
                      "message": f"Uncaught exception: {type(exc).__name__}: {exc}",
                      "application_url": url}

        elapsed = time.time() - t0
        rca["total_attempted"] += 1

        app_entry = {
            "idx": idx, "title": title, "company": company, "url": url,
            "score": job.get("score", 0), "success": result.get("success", False),
            "status": result.get("status", "failed"), "message": result.get("message", ""),
            "elapsed": round(elapsed, 1), "timestamp": datetime.now().isoformat(),
        }

        if result.get("success"):
            rca["succeeded"] += 1
            job["applied"]    = True
            job["applied_at"] = datetime.now().isoformat()
            try:
                db.record_application(
                    job_id=job.get("id", ""), portal="greenhouse",
                    application_url=url, cover_letter="", cv_version="default",
                    notes=result.get("message", ""), status="applied"
                )
            except Exception as dbe:
                logger.warning(f"[RCA] DB write error: {dbe}")
        else:
            rca["failed"] += 1
            job["applied"]        = True
            job["processed"]      = True
            job["failed_at"]      = datetime.now().isoformat()
            job["failure_reason"] = result.get("message", "")
            reason_key = result.get("message", "Unknown")[:80]
            rca["failure_reasons"][reason_key] = rca["failure_reasons"].get(reason_key, 0) + 1
            try:
                db.record_application(
                    job_id=job.get("id", ""), portal="greenhouse",
                    application_url=url, cover_letter="", cv_version="default",
                    notes=result.get("message", ""), status=result.get("status", "failed")
                )
            except Exception as dbe:
                logger.warning(f"[RCA] DB write error: {dbe}")

        rca["applications"].append(app_entry)
        save_rca()

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        print_result(result, job, elapsed)
        print_running_summary()
        logger.info(f"[RCA] DONE {idx}/{total}: {'SUCCESS' if result.get('success') else 'FAILED'} ({elapsed:.1f}s) - {result.get('message','')[:80]}")

        if idx < total:
            print(f"\n  Waiting 3s before next application...\n")
            await asyncio.sleep(3)

    print_final_rca()
    save_rca()

    try:
        from applier.base_applier import _browser_manager
        if _browser_manager:
            await _browser_manager.stop()
    except Exception:
        pass


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Watch-mode Greenhouse batch applier with live RCA")
    parser.add_argument("--n", type=int, default=15, help="Number of jobs to apply (default: 15)")
    args = parser.parse_args()
    try:
        asyncio.run(run_batch(n_jobs=args.n))
    except KeyboardInterrupt:
        print(f"\nInterrupted by user. Partial RCA:")
        print_final_rca()

"""
main.py — Main orchestrator for the Auto Job Apply System.
Coordinates scraping, matching, applying, and email monitoring.

Usage:
    python main.py               # Run dashboard + full system
    python main.py --dry-run     # Scrape + match, NO applying
    python main.py --scrape-only # Just scrape and score jobs
    python main.py --dashboard   # Just launch the dashboard
    python main.py --test        # Test connectivity of all components
"""

import argparse
import asyncio
import logging
import sys
import threading
import time
import os
import random
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

# Force UTF-8 on Windows stdout/stderr to prevent cp1252 charmap encoding errors
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Setup paths first ──
sys.path.insert(0, str(Path(__file__).parent))
os.chdir(Path(__file__).parent)

from config import (
    PORTALS, SEARCH_QUERIES, APPLICATION, DB_PATH,
    LOG_DIR, DASHBOARD_PORT, MATCHING
)
from db.database import Database
from matcher.scorer import score_job, is_good_match
from email_monitor.monitor import EmailMonitor


# ────────────────────────────────────────────
# Logging setup
# ────────────────────────────────────────────

LOG_DIR.mkdir(exist_ok=True)
log_file = LOG_DIR / "app.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(log_file), encoding="utf-8"),
    ]
)
logger = logging.getLogger("main")



# ────────────────────────────────────────────
# Scraper registry
# ────────────────────────────────────────────

def get_scrapers():
    """Instantiate enabled scrapers."""
    scrapers = {}

    if PORTALS["linkedin"]["enabled"]:
        from scrapers.linkedin_scraper import LinkedInScraper
        scrapers["linkedin"] = LinkedInScraper()

    if PORTALS["naukri"]["enabled"]:
        from scrapers.naukri_scraper import NaukriScraper
        scrapers["naukri"] = NaukriScraper()

    if PORTALS["indeed"]["enabled"]:
        from scrapers.indeed_scraper import IndeedScraper
        scrapers["indeed"] = IndeedScraper()

    if PORTALS["wellfound"]["enabled"]:
        from scrapers.wellfound_scraper import WellfoundScraper
        scrapers["wellfound"] = WellfoundScraper()

    if PORTALS["internshala"]["enabled"]:
        from scrapers.internshala_scraper import IntershalaScraper
        scrapers["internshala"] = IntershalaScraper()

    if PORTALS["freehire"]["enabled"]:
        from scrapers.freehire_scraper import FreehireScraper
        scrapers["freehire"] = FreehireScraper()

    return scrapers


# ────────────────────────────────────────────
# Applier registry
# ────────────────────────────────────────────

def get_applier(portal: str, email_monitor: EmailMonitor = None):
    """Get the applier for a given portal."""
    if portal == "linkedin":
        from applier.linkedin_applier import LinkedInApplier
        return LinkedInApplier(email_monitor)
    elif portal == "naukri":
        from applier.naukri_applier import NaukriApplier
        return NaukriApplier(email_monitor)
    elif portal == "indeed":
        from applier.indeed_applier import IndeedApplier
        return IndeedApplier(email_monitor)
    return None


# ────────────────────────────────────────────
# Orchestrator
# ────────────────────────────────────────────

class JobOrchestrator:
    """Main system orchestrator — scrape → match → apply."""

    def __init__(self, db: Database, email_monitor: EmailMonitor):
        self.db = db
        self.email_monitor = email_monitor
        self.is_running = False
        self._stop_event = threading.Event()
        self._appliers: Dict[str, Any] = {}

    def start(self):
        """Start continuous operation (runs in a thread)."""
        self.is_running = True
        self._stop_event.clear()
        self._stats = {"applied": 0, "failed": 0, "skipped": 0}
        t = threading.Thread(target=self._run_loop, daemon=True)
        t.start()

    def stop(self):
        """Signal the system to stop."""
        self.is_running = False
        self._stop_event.set()
        logger.info("[Orchestrator] Stop signal sent")

    def _run_loop(self):
        """Continuous run loop: scrape + apply every hour."""
        logger.info("[Orchestrator] Starting continuous run loop")
        while not self._stop_event.is_set():
            try:
                asyncio.run(self._run_cycle(dry_run=False))
            except Exception as e:
                logger.error(f"[Orchestrator] Cycle error: {e}", exc_info=True)
            # Wait 60 minutes (or until stopped)
            logger.info("[Orchestrator] Cycle complete. Next run in 60 minutes.")
            self._stop_event.wait(timeout=3600)
        self.is_running = False
        logger.info("[Orchestrator] Stopped")

    def run_once(self, dry_run: bool = False):
        """Run one scrape+apply cycle synchronously."""
        self._stats = {"applied": 0, "failed": 0, "skipped": 0}
        asyncio.run(self._run_cycle(dry_run=dry_run))

    async def _run_cycle(self, dry_run: bool = False):
        """One full scrape → score → apply cycle."""
        start_t = time.time()
        mode = "DRY RUN" if dry_run else "APPLY MODE"
        logger.info(f"\n{'='*60}\n[Orchestrator] Starting cycle — {mode}\n{'='*60}")

        scrapers = get_scrapers()
        total_scraped = 0
        total_matched = 0
        total_applied = 0
        total_failed = 0

        # ── PHASE 1: SCRAPE ──────────────────────────────────
        all_jobs: List[Dict] = []

        for query_cfg in SEARCH_QUERIES:
            query = query_cfg["q"]
            location = query_cfg["location"]

            for portal_name, scraper in scrapers.items():
                if self._stop_event.is_set():
                    break
                try:
                    logger.info(f"[Scraper] {portal_name}: '{query}' in '{location}'")
                    jobs = await scraper.search(query, location, jobage=7)  # Last 7 days
                    all_jobs.extend(jobs)
                    total_scraped += len(jobs)

                    # Polite delay between portals
                    await asyncio.sleep(random.uniform(2, 5))

                except Exception as e:
                    logger.error(f"[Scraper] {portal_name} error: {e}")

        # Deduplicate by URL
        seen_urls = set()
        unique_jobs = []
        for job in all_jobs:
            url = job.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_jobs.append(job)

        logger.info(f"[Scraper] Scraped {total_scraped} total, {len(unique_jobs)} unique")

        # ── PHASE 2: SCORE + FILTER ──────────────────────────
        matched_jobs = []
        for job in unique_jobs:
            score, details = score_job(job)
            job["score"] = score
            job["match_details"] = details
            job["is_dealbreaker"] = details.get("is_dealbreaker", False)

            is_new = self.db.upsert_job(job)

            if is_new:
                logger.debug(
                    f"[Matcher] {score:.0f}% — {job['title']} @ {job.get('company','?')} "
                    f"[{job.get('portal','?')}]"
                )

            if is_good_match(score) and not job["is_dealbreaker"]:
                matched_jobs.append(job)
                total_matched += 1

        logger.info(f"[Matcher] {total_matched}/{len(unique_jobs)} jobs match profile (≥{MATCHING['min_score']}%)")

        # Sort by score descending
        matched_jobs.sort(key=lambda j: j["score"], reverse=True)

        # ── PHASE 3: APPLY ───────────────────────────────────
        if dry_run:
            logger.info("[DryRun] Skipping application phase")
            self._print_matches(matched_jobs[:20])
        else:
            await self._apply_to_matches(matched_jobs)

        # Record run stats
        duration = time.time() - start_t
        n_applied = self._stats.get("applied", 0)
        n_failed = self._stats.get("failed", 0)
        for portal_name in scrapers:
            self.db.record_run_stats(
                portal=portal_name,
                scraped=total_scraped,
                matched=total_matched,
                applied=n_applied,
                failed=n_failed,
                duration_s=duration,
            )

        # Close scrapers
        for scraper in scrapers.values():
            try:
                await scraper.close()
            except Exception:
                pass

        logger.info(
            "\n" + "=" * 60 + "\n"
            f"[Orchestrator] Cycle complete in {duration:.0f}s\n"
            f"  Scraped: {total_scraped}  |  Matched: {total_matched}  |  "
            f"Applied: {n_applied}  |  Failed: {n_failed}\n"
            + "=" * 60
        )

    async def _apply_to_matches(self, matched_jobs: List[Dict]):
        """Apply to all matched jobs, respecting daily limits."""
        daily_limit = APPLICATION["max_daily"]
        delay = APPLICATION["apply_delay_seconds"]

        today_applied = self.db.get_stats()["applied_today"]
        remaining_today = daily_limit - today_applied

        if remaining_today <= 0:
            logger.info(f"[Applier] Daily limit ({daily_limit}) reached. Skipping applications.")
            return

        # Filter out jobs already applied to (by applications table OR job status)
        pending = []
        for job in matched_jobs:
            if self.db.already_applied(job["id"]):
                continue
            if job.get("status") == "applied":
                continue
            pending.append(job)

        to_apply = pending[:remaining_today]
        logger.info(
            f"[Applier] {len(matched_jobs)} matched, {len(pending)} pending, "
            f"applying to top {len(to_apply)} (daily limit: {daily_limit}, used: {today_applied})"
        )

        if not to_apply:
            logger.info("[Applier] Nothing new to apply to.")
            return

        for job in to_apply:
            if self._stop_event.is_set():
                break

            portal = job.get("portal", "")
            applier = self._get_or_create_applier(portal)

            if applier is None:
                logger.info(f"[Applier] No applier for portal '{portal}' — skipping '{job['title']}'")
                self.db.update_job_status(job["id"], "skipped")
                self._stats["skipped"] = self._stats.get("skipped", 0) + 1
                continue

            logger.info(
                f"[Applier] --> {job['title'][:50]} @ {(job.get('company') or '?')[:25]} "
                f"| {job['score']:.0f}% match | {portal}"
            )

            result = await applier.apply_safe(job)
            status = result.get("status", "failed")

            if result["success"]:
                self._stats["applied"] = self._stats.get("applied", 0) + 1
                self.db.record_application(
                    job_id=job["id"],
                    portal=portal,
                    application_url=result.get("application_url", job.get("url", "")),
                    cover_letter="",
                    cv_version="default",
                    notes=result.get("message", ""),
                )
                logger.info(f"[Applier] APPLIED: {job['title']} @ {job.get('company')}")
            else:
                self._stats["failed"] = self._stats.get("failed", 0) + 1
                self.db.update_job_status(job["id"], status)
                msg = result.get("message", "")
                if status == "skipped":
                    logger.info(f"[Applier] SKIPPED: {job['title']} — {msg}")
                elif status == "already_applied":
                    logger.info(f"[Applier] ALREADY APPLIED: {job['title']}")
                else:
                    logger.warning(f"[Applier] FAILED: {job['title']} — {msg}")

            # Human-like delay between applications
            actual_delay = delay * random.uniform(0.5, 1.5)
            logger.info(f"[Applier] Waiting {actual_delay:.0f}s before next...")
            await asyncio.sleep(actual_delay)

    def _get_or_create_applier(self, portal: str):
        """Get or create a cached applier for a portal."""
        if portal not in self._appliers:
            applier = get_applier(portal, self.email_monitor)
            self._appliers[portal] = applier
        return self._appliers[portal]

    def _print_matches(self, jobs: List[Dict]):
        """Print top matches for dry-run mode."""
        logger.info(f"\n{'─'*60}")
        logger.info(f"TOP {len(jobs)} MATCHES (Dry Run — not applying)")
        logger.info(f"{'─'*60}")
        for i, job in enumerate(jobs, 1):
            logger.info(
                f"{i:2d}. [{job['score']:5.1f}%] {job['title'][:45]} @ "
                f"{(job.get('company') or '?')[:25]} ({job.get('portal')}) "
                f"— {job.get('url', '')[:60]}"
            )
        logger.info(f"{'─'*60}")


# ────────────────────────────────────────────
# Test mode
# ────────────────────────────────────────────

async def run_tests():
    """Test connectivity of all components."""
    logger.info("=== Running Component Tests ===")
    all_ok = True

    # Test DB
    logger.info("[Test] Database...")
    try:
        db = Database(DB_PATH)
        stats = db.get_stats()
        logger.info(f"[Test] ✓ Database OK — {stats['total_scraped']} jobs stored")
    except Exception as e:
        logger.error(f"[Test] ✗ Database: {e}")
        all_ok = False

    # Test scrapers
    logger.info("[Test] Scrapers (quick search test)...")
    try:
        from scrapers.linkedin_scraper import LinkedInScraper
        scraper = LinkedInScraper()
        jobs = await scraper.search("backend developer", "Pune", page=0)
        logger.info(f"[Test] ✓ LinkedIn scraper OK — got {len(jobs)} jobs")
        await scraper.close()
    except Exception as e:
        logger.error(f"[Test] ✗ LinkedIn scraper: {e}")

    try:
        from scrapers.freehire_scraper import FreehireScraper
        scraper = FreehireScraper()
        jobs = await scraper.search("backend", "India")
        logger.info(f"[Test] ✓ Freehire scraper OK — got {len(jobs)} jobs")
        await scraper.close()
    except Exception as e:
        logger.error(f"[Test] ✗ Freehire scraper: {e}")

    # Test matcher
    logger.info("[Test] Matcher...")
    try:
        test_job = {
            "title": "Backend Engineer - Python/Kafka",
            "company": "Razorpay",
            "location": "Bangalore, India",
            "description": "We need a backend engineer with Python, Kafka, distributed systems experience. "
                           "Knowledge of REST APIs, microservices, and low-latency systems is required.",
        }
        score, details = score_job(test_job)
        logger.info(f"[Test] ✓ Matcher OK — Test job score: {score:.1f}% (expected >70%)")
        if score < 50:
            logger.warning(f"[Test] Matcher score seems low: {score:.1f}%")
    except Exception as e:
        logger.error(f"[Test] ✗ Matcher: {e}")
        all_ok = False

    # Test CAPTCHA
    logger.info("[Test] CAPTCHA solver...")
    from captcha.solver import captcha_solver
    if captcha_solver.has_solver:
        logger.info("[Test] ✓ CAPTCHA solver configured with API key")
    else:
        logger.info("[Test] ℹ CAPTCHA solver in stealth-only mode (no API key)")

    # Test email
    logger.info("[Test] Email monitor...")
    monitor = EmailMonitor()
    if monitor.enabled:
        logger.info("[Test] ✓ Gmail credentials configured")
    else:
        logger.info("[Test] ℹ Gmail not configured (optional)")

    # Test Playwright
    logger.info("[Test] Playwright browser...")
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto("about:blank")
            await browser.close()
        logger.info("[Test] ✓ Playwright OK")
    except Exception as e:
        logger.error(f"[Test] ✗ Playwright: {e}")
        logger.error("  Run: pip install playwright && playwright install chromium")
        all_ok = False

    logger.info(f"\n=== Tests {'PASSED ✓' if all_ok else 'FAILED ✗ (check above)'} ===")
    return all_ok


# ────────────────────────────────────────────
# Entry point
# ────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Auto Job Apply System — Automated job application for Ranjan Kumar"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Scrape and score jobs but don't apply")
    parser.add_argument("--scrape-only", action="store_true",
                        help="Only scrape jobs, no scoring or applying")
    parser.add_argument("--dashboard", action="store_true",
                        help="Launch dashboard only (no scraping)")
    parser.add_argument("--test", action="store_true",
                        help="Test all component connectivity")
    parser.add_argument("--no-dashboard", action="store_true",
                        help="Run without dashboard (CLI only)")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("  Auto Job Apply System — Ranjan Kumar")
    logger.info(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # Initialize database
    db = Database(DB_PATH)
    logger.info(f"Database: {DB_PATH}")

    # Initialize email monitor
    email_monitor = EmailMonitor(db=db)
    email_monitor.add_callback(lambda e: logger.info(
        f"[Email] {e['email_type'].upper()}: '{e['subject'][:60]}'"
    ))

    # Test mode
    if args.test:
        success = asyncio.run(run_tests())
        sys.exit(0 if success else 1)

    # Dashboard only
    if args.dashboard:
        from dashboard.app import run_dashboard
        logger.info(f"Dashboard: http://localhost:{DASHBOARD_PORT}")
        run_dashboard(db, port=DASHBOARD_PORT)
        return

    # Start email monitoring
    email_monitor.start()

    # Create orchestrator
    orchestrator = JobOrchestrator(db, email_monitor)

    # Start dashboard in background thread
    if not args.no_dashboard:
        from dashboard.app import run_dashboard
        dash_thread = threading.Thread(
            target=run_dashboard,
            args=(db, orchestrator, DASHBOARD_PORT),
            daemon=True
        )
        dash_thread.start()
        logger.info(f"Dashboard: http://localhost:{DASHBOARD_PORT}")

    # Run according to mode
    if args.dry_run:
        logger.info("[Mode] Dry run — scraping and matching only")
        orchestrator.run_once(dry_run=True)
    elif args.scrape_only:
        logger.info("[Mode] Scrape only")
        orchestrator.run_once(dry_run=True)
    else:
        logger.info("[Mode] Full system — scraping + applying (continuous)")
        logger.info(f"Press Ctrl+C to stop. Dashboard: http://localhost:{DASHBOARD_PORT}")

        # Run first cycle immediately
        orchestrator.run_once(dry_run=False)

        # Then start continuous loop
        orchestrator.start()
        try:
            while True:
                time.sleep(10)
        except KeyboardInterrupt:
            logger.info("\nStopping system...")
            orchestrator.stop()
            email_monitor.stop()

    email_monitor.stop()
    logger.info("System stopped.")


if __name__ == "__main__":
    main()

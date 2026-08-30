"""
applier/linkedin_applier.py — LinkedIn Easy Apply automation.
Handles LinkedIn's multi-step Easy Apply modal with Playwright.
"""

import logging
import asyncio
import random

from config import PROFILE, APPLICATION
from applier.base_applier import BaseApplier, get_browser_manager
from applier.form_filler import FormFiller
from captcha.solver import captcha_solver
import os

logger = logging.getLogger(__name__)

LINKEDIN_LOGIN_URL = "https://www.linkedin.com/login"
LINKEDIN_JOBS_URL = "https://www.linkedin.com/jobs/"


class LinkedInApplier(BaseApplier):
    portal_name = "linkedin"
    login_url = LINKEDIN_LOGIN_URL

    def __init__(self, email_monitor=None):
        super().__init__(email_monitor)
        self.form_filler = FormFiller()

    async def login(self) -> bool:
        """Log in to LinkedIn with cookie persistence."""
        if self._logged_in:
            return True

        email = PROFILE.get("email", "")
        password = os.environ.get("LINKEDIN_PASSWORD", "")

        if not password:
            logger.warning("[LinkedIn] No password set. Set LINKEDIN_PASSWORD in .env")
            return False

        # Get browser manager FIRST (before creating page) so cookies load into context
        manager = await get_browser_manager()

        # ── PHASE 1: Try saved cookies first ──────────────────────────────────
        cookies_loaded = await manager.load_cookies("linkedin")
        page = await self._get_page()  # page created AFTER cookies are in context

        if cookies_loaded:
            logger.info("[LinkedIn] Cookies loaded — checking if session is valid...")
            try:
                await page.goto("https://www.linkedin.com/feed/", timeout=20000)
                await page.wait_for_load_state("domcontentloaded", timeout=10000)
                await asyncio.sleep(2)
                current = page.url
                if any(w in current for w in ["feed", "/jobs/", "mynetwork", "dashboard"]):
                    logger.info("[LinkedIn] Session restored from cookies — already logged in!")
                    self._logged_in = True
                    return True
                else:
                    logger.info(f"[LinkedIn] Saved cookies expired (at: {current}) — doing fresh login")
                    manager.clear_cookies("linkedin")
            except Exception as e:
                logger.warning(f"[LinkedIn] Cookie check failed: {e} — doing fresh login")
                manager.clear_cookies("linkedin")

        # ── PHASE 2: Fresh login via JS fill ──────────────────────────────────
        logger.info("[LinkedIn] Performing fresh login...")
        await page.goto("https://www.linkedin.com/login", timeout=30000)
        await page.wait_for_load_state("domcontentloaded", timeout=15000)
        await self._human_delay(2, 3)

        # Check if already logged in (redirected away from login)
        if any(w in page.url for w in ["feed", "/jobs/", "mynetwork"]):
            logger.info("[LinkedIn] Already logged in (redirected)")
            self._logged_in = True
            await manager.save_cookies("linkedin")
            return True

        try:
            # Use JS to fill form — LinkedIn uses React with auto-generated IDs
            filled = await page.evaluate("""
                (args) => {
                    const [email, password] = args;
                    const allInputs = Array.from(document.querySelectorAll('input'));
                    const emailInput = allInputs.find(i =>
                        i.type === 'email' || i.autocomplete === 'username'
                    );
                    const pwdInput = allInputs.find(i =>
                        i.type === 'password' || i.autocomplete === 'current-password'
                    );
                    if (!emailInput || !pwdInput) {
                        return {ok: false, msg: 'email=' + !!emailInput + ' pwd=' + !!pwdInput};
                    }
                    const setter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value'
                    ).set;
                    setter.call(emailInput, email);
                    emailInput.dispatchEvent(new Event('input', {bubbles: true}));
                    emailInput.dispatchEvent(new Event('change', {bubbles: true}));
                    setter.call(pwdInput, password);
                    pwdInput.dispatchEvent(new Event('input', {bubbles: true}));
                    pwdInput.dispatchEvent(new Event('change', {bubbles: true}));
                    return {ok: true, emailId: emailInput.id, pwdId: pwdInput.id};
                }
            """, [email, password])

            if not filled or not filled.get("ok"):
                logger.error(f"[LinkedIn] JS fill failed: {filled}")
                await self._take_screenshot(page, "linkedin_login_jsfill_failed")
                return False

            logger.info(f"[LinkedIn] Filled credentials via JS (ids: {filled.get('emailId')}, {filled.get('pwdId')})")
            await self._human_delay(0.8, 1.5)

            # Submit the form
            submitted = False
            for sel in ["button[type='submit']", "button:has-text('Sign in')", "button[aria-label='Sign in']", ".sign-in-form__submit-button"]:
                try:
                    btn = page.locator(sel).first
                    if await btn.count() > 0:
                        await btn.click(timeout=5000)
                        submitted = True
                        logger.info(f"[LinkedIn] Clicked submit via: {sel}")
                        break
                except Exception:
                    continue
            if not submitted:
                # Fallback: focus password field and press Enter (always works)
                logger.info("[LinkedIn] No submit button found — pressing Enter on password field")
                await page.evaluate("""
                    () => {
                        const pwd = document.querySelector('input[type=password]');
                        if (pwd) { pwd.focus(); }
                    }
                """)
                await page.keyboard.press("Enter")

            await page.wait_for_load_state("domcontentloaded", timeout=20000)
            await self._human_delay(3, 4)

        except Exception as e:
            logger.error(f"[LinkedIn] Login form fill error: {e}")
            await self._take_screenshot(page, "linkedin_login_error")
            return False

        # ── PHASE 3: Handle security challenge (wait for manual solve) ─────────
        if any(w in page.url for w in ["checkpoint", "challenge", "captcha", "verification"]):
            logger.warning(
                "\n" + "=" * 65 + "\n"
                "[LinkedIn] SECURITY CHALLENGE DETECTED!\n"
                "  A browser window should be open. Please:\n"
                "  1. Check your phone/email for a verification code\n"
                "  2. Enter it in the browser\n"
                "  3. The system will continue automatically once done.\n"
                "  (Waiting up to 3 minutes...)\n"
                + "=" * 65
            )
            # Wait up to 3 minutes for user to complete challenge
            for _ in range(36):
                await asyncio.sleep(5)
                current = page.url
                if any(w in current for w in ["feed", "/jobs/", "mynetwork", "dashboard", "home"]):
                    logger.info("[LinkedIn] Challenge solved! Continuing...")
                    break
            else:
                logger.error("[LinkedIn] Challenge not solved within 3 minutes")
                await self._take_screenshot(page, "linkedin_challenge_timeout")
                return False

        # ── Verify login success ──────────────────────────────────────────────
        current = page.url
        logger.info(f"[LinkedIn] Post-login URL: {current}")

        if any(w in current for w in ["feed", "/jobs/", "mynetwork", "dashboard", "home"]):
            logger.info("[LinkedIn] Login successful! Saving cookies...")
            await manager.save_cookies("linkedin")
            self._logged_in = True
            return True
        elif "login" not in current and "authwall" not in current and "signin" not in current:
            logger.info("[LinkedIn] Login appears successful — saving cookies")
            await manager.save_cookies("linkedin")
            self._logged_in = True
            return True
        else:
            logger.error(f"[LinkedIn] Login failed — still at: {current}")
            await self._take_screenshot(page, "linkedin_login_failed")
            return False

    async def apply(self, job: dict) -> dict:
        """Apply to a LinkedIn job using Easy Apply."""
        url = job.get("url", "")
        title = job.get("title", "")
        company = job.get("company", "")

        logger.info(f"[LinkedIn] Applying to: {title} @ {company}")

        # Always login first — job pages redirect to login wall without session
        if not self._logged_in:
            if not await self.login():
                return {"success": False, "status": "failed",
                        "message": "LinkedIn login failed", "application_url": url}

        page = await self._get_page()

        try:
            await page.goto(url, timeout=25000)
            await self._wait_for_navigation(page)
            await self._human_delay(2, 4)

            # Detect login wall / auth wall redirect
            current_url = page.url
            if any(w in current_url for w in ["login", "authwall", "checkpoint", "signin"]):
                logger.warning(f"[LinkedIn] Auth wall detected — attempting re-login")
                self._logged_in = False
                if not await self.login():
                    return {"success": False, "status": "failed",
                            "message": "Redirected to auth wall, re-login failed",
                            "application_url": url}
                await page.goto(url, timeout=25000)
                await self._wait_for_navigation(page)
                await self._human_delay(2, 3)

            # Look for Easy Apply button with multiple selectors
            easy_apply_selectors = [
                "button.jobs-apply-button",
                "button[data-job-id]",
                "button:has-text('Easy Apply')",
                ".jobs-apply-button--top-card",
                "[data-control-name='jobdetails_topcard_inapply']",
                "button.artdeco-button--primary:has-text('Apply')",
            ]

            easy_apply_btn = None
            for sel in easy_apply_selectors:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=3000):
                        btn_text = await btn.text_content() or ""
                        if "Easy Apply" in btn_text or "easy" in btn_text.lower():
                            easy_apply_btn = btn
                            logger.info(f"[LinkedIn] Found Easy Apply button: '{btn_text.strip()}'")
                            break
                except Exception:
                    continue

            if easy_apply_btn is None:
                # Check if there's any Apply button (might be external)
                try:
                    any_btn = page.locator("button:has-text('Apply')").first
                    if await any_btn.is_visible(timeout=2000):
                        btn_text = await any_btn.text_content() or ""
                        logger.info(f"[LinkedIn] Found Apply button (not Easy Apply): '{btn_text.strip()}' — external job")
                    else:
                        logger.info(f"[LinkedIn] No Apply button found for '{title}'")
                except Exception:
                    pass

                return {
                    "success": False,
                    "status": "skipped",
                    "message": "No Easy Apply button — external application required",
                    "application_url": url,
                }

            # Click Easy Apply
            await easy_apply_btn.click()
            await self._human_delay(1.5, 3)

            # Handle the multi-step modal
            success = await self._handle_easy_apply_modal(page, job)

            if success:
                logger.info(f"[LinkedIn] Applied to: {title} @ {company}")
                return {
                    "success": True,
                    "status": "applied",
                    "message": "Easy Apply submitted successfully",
                    "application_url": url,
                }
            else:
                return {
                    "success": False,
                    "status": "failed",
                    "message": "Easy Apply modal failed or could not complete",
                    "application_url": url,
                }

        except Exception as e:
            logger.error(f"[LinkedIn] Apply error: {e}")
            await self._take_screenshot(page, "linkedin_apply_error")
            return {"success": False, "status": "failed", "message": str(e), "application_url": url}

    async def _handle_easy_apply_modal(self, page, job: dict) -> bool:
        """Navigate through LinkedIn's multi-step Easy Apply modal."""
        max_steps = 8  # LinkedIn modals typically have 1-5 steps

        for step in range(max_steps):
            await self._human_delay(1, 2)

            # Check if modal is still open
            modal = page.locator(".jobs-easy-apply-modal, [role='dialog']").first
            if not await modal.is_visible(timeout=5000):
                logger.info(f"[LinkedIn] Modal closed at step {step}")
                break

            # Fill any visible form fields
            await self.form_filler.fill_form(page, job)
            await self.form_filler.handle_selects(page)
            await self._human_delay(1, 2)

            # Check for "Submit application" button (final step)
            submit_btn = modal.locator("button:has-text('Submit application')").first
            if await submit_btn.is_visible(timeout=2000):
                await self._human_click(page, "button:has-text('Submit application')")
                await self._human_delay(2, 4)
                logger.info("[LinkedIn] Submitted application!")

                # Dismiss success dialog
                try:
                    dismiss = page.locator("button:has-text('Done'), button:has-text('Dismiss')").first
                    if await dismiss.is_visible(timeout=3000):
                        await self._human_click(page, "button:has-text('Done'), button:has-text('Dismiss')")
                except Exception:
                    pass
                return True

            # Look for "Review" button (second-to-last step)
            review_btn = modal.locator("button:has-text('Review')").first
            if await review_btn.is_visible(timeout=2000):
                await self._human_click(page, "button:has-text('Review')")
                continue

            # Look for "Next" button
            next_btn = modal.locator("button:has-text('Next'), button[aria-label='Continue to next step']").first
            if await next_btn.is_visible(timeout=2000):
                await self._human_click(page, "button:has-text('Next')")
                continue

            # Handle file upload if needed
            file_input = modal.locator("input[type='file']").first
            if await file_input.is_visible(timeout=2000):
                cv_path = PROFILE.get("cv_pdf_path", "")
                if cv_path and __import__("os").path.exists(cv_path):
                    await file_input.set_input_files(cv_path)
                    logger.info("[LinkedIn] Uploaded CV")
                    await self._human_delay(1, 2)
                    continue

            # Handle CAPTCHA
            solved = await captcha_solver.detect_and_solve(page)
            if not solved:
                logger.error("[LinkedIn] CAPTCHA not solved in modal")
                return False

            # If nothing matched, try clicking any visible primary button
            any_btn = modal.locator("button.artdeco-button--primary").last
            if await any_btn.is_visible(timeout=2000):
                await any_btn.click()
                continue

            logger.warning(f"[LinkedIn] Step {step}: No recognizable button found")
            break

        # Check if we successfully applied (look for success indicators)
        success_indicators = page.locator(
            ":has-text('Application submitted'), :has-text('applied'), "
            ".artdeco-inline-feedback--success"
        )
        return await success_indicators.count() > 0

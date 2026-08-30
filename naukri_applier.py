"""
applier/naukri_applier.py — Naukri.com Quick Apply automation.
Handles Naukri's login, profile-based apply, and Quick Apply forms.
"""

import logging
import re
import os

from config import PROFILE
from applier.base_applier import BaseApplier
from applier.form_filler import FormFiller
from captcha.solver import captcha_solver

logger = logging.getLogger(__name__)

NAUKRI_LOGIN_URL = "https://www.naukri.com/nlogin/login"
NAUKRI_HOMEPAGE = "https://www.naukri.com"


class NaukriApplier(BaseApplier):
    portal_name = "naukri"
    login_url = NAUKRI_LOGIN_URL

    def __init__(self, email_monitor=None):
        super().__init__(email_monitor)
        self.form_filler = FormFiller()

    async def login(self) -> bool:
        """Log in to Naukri.com."""
        if self._logged_in:
            return True

        email = PROFILE.get("email", "")
        password = os.environ.get("NAUKRI_PASSWORD", "")

        if not password:
            logger.warning("[Naukri] No password set. Set NAUKRI_PASSWORD in .env")
            return False

        page = await self._get_page()
        logger.info("[Naukri] Logging in...")

        await page.goto(NAUKRI_LOGIN_URL)
        await self._wait_for_navigation(page)
        await self._human_delay(2, 3)

        try:
            # Handle cookie/popup banners
            for dismiss_sel in ["#cookie-banner .accept", ".login_layer .close-btn", "#loginPopup .crossIcon"]:
                try:
                    btn = page.locator(dismiss_sel).first
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        await self._human_delay(0.5, 1)
                except Exception:
                    pass

            # Fill login form
            await self._human_type(page, '#usernameField', email)
            await self._human_delay(0.5, 1.0)
            await self._human_type(page, '#passwordField', password)
            await self._human_delay(0.5, 1.0)

            # Click login button
            await self._human_click(page, "button[type='submit']:has-text('Login')")
            await self._wait_for_navigation(page, timeout=20000)
            await self._human_delay(2, 4)

            # Handle CAPTCHA
            if "verify" in page.url.lower() or await page.locator(".g-recaptcha, .h-captcha").is_visible(timeout=2000):
                logger.info("[Naukri] CAPTCHA detected during login")
                solved = await captcha_solver.detect_and_solve(page)
                if not solved:
                    logger.error("[Naukri] CAPTCHA not solved")
                    return False
                await self._wait_for_navigation(page)

            # Check login success
            if "naukri.com" in page.url and "nlogin" not in page.url:
                logger.info("[Naukri] Login successful!")
                self._logged_in = True
                return True

            logger.error(f"[Naukri] Login failed — at: {page.url}")
            await self._take_screenshot(page, "naukri_login_failed")
            return False

        except Exception as e:
            logger.error(f"[Naukri] Login error: {e}")
            await self._take_screenshot(page, "naukri_login_error")
            return False

    async def apply(self, job: dict) -> dict:
        """Apply to a Naukri job using Quick Apply or full form."""
        url = job.get("url", "")
        title = job.get("title", "")
        company = job.get("company", "")

        logger.info(f"[Naukri] Applying to: {title} @ {company}")

        if not self._logged_in:
            if not await self.login():
                return {"success": False, "status": "failed",
                        "message": "Login failed", "application_url": url}

        page = await self._get_page()

        try:
            await page.goto(url)
            await self._wait_for_navigation(page)
            await self._human_delay(2, 3)

            # Handle "Already Applied" indicator
            already = page.locator(":has-text('Applied'), .already-applied, [class*='alreadyApplied']").first
            if await already.is_visible(timeout=3000):
                logger.info(f"[Naukri] Already applied to: {title}")
                return {"success": False, "status": "already_applied",
                        "message": "Already applied", "application_url": url}

            # Find Apply button
            apply_btn = page.locator(
                "button:has-text('Apply'), "
                "a:has-text('Apply'), "
                "[class*='apply-button'], "
                "#apply-button"
            ).first

            if not await apply_btn.is_visible(timeout=5000):
                logger.info(f"[Naukri] No apply button found for '{title}'")
                return {"success": False, "status": "skipped",
                        "message": "No apply button", "application_url": url}

            # Click apply
            await self._human_click(page, "button:has-text('Apply'), a:has-text('Apply')")
            await self._human_delay(1.5, 3)

            # Handle any modal or new page
            success = await self._handle_apply_flow(page, job)

            if success:
                logger.info(f"[Naukri] ✓ Applied to: {title} @ {company}")
                return {"success": True, "status": "applied",
                        "message": "Applied successfully", "application_url": url}
            else:
                return {"success": False, "status": "failed",
                        "message": "Apply flow failed", "application_url": url}

        except Exception as e:
            logger.error(f"[Naukri] Apply error: {e}")
            await self._take_screenshot(page, "naukri_apply_error")
            return {"success": False, "status": "failed", "message": str(e), "application_url": url}

    async def _handle_apply_flow(self, page, job: dict) -> bool:
        """Handle Naukri's apply flow (Quick Apply or full form)."""
        max_steps = 5

        for step in range(max_steps):
            await self._human_delay(1, 2)

            # Check for success indicators
            success_sels = [
                ":has-text('Application submitted')",
                ":has-text('Successfully applied')",
                ":has-text('applied successfully')",
                "[class*='success-message']",
                "[class*='application-success']",
            ]
            for sel in success_sels:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=2000):
                        return True
                except Exception:
                    pass

            # Fill any form fields
            await self.form_filler.fill_form(page, job)
            await self.form_filler.handle_selects(page)
            await self._human_delay(1, 1.5)

            # Submit / Apply button
            for submit_text in ["Submit", "Apply Now", "Apply", "Send Application", "Confirm"]:
                try:
                    btn = page.locator(f"button:has-text('{submit_text}')").last
                    if await btn.is_visible(timeout=2000):
                        await self._human_click(page, f"button:has-text('{submit_text}')")
                        await self._human_delay(2, 3)
                        break
                except Exception:
                    pass

            # CAPTCHA check
            await captcha_solver.detect_and_solve(page)

        # Final check
        for sel in [":has-text('Applied')", ":has-text('Thank you')", "[class*='success']"]:
            try:
                if await page.locator(sel).first.is_visible(timeout=3000):
                    return True
            except Exception:
                pass

        return False

"""
applier/indeed_applier.py — Indeed India job apply automation.
Handles Indeed's application flow (redirect to company site or Indeed form).
"""

import logging
import os

from config import PROFILE
from applier.base_applier import BaseApplier
from applier.form_filler import FormFiller
from captcha.solver import captcha_solver

logger = logging.getLogger(__name__)

INDEED_LOGIN_URL = "https://secure.indeed.com/account/login"


class IndeedApplier(BaseApplier):
    portal_name = "indeed"
    login_url = INDEED_LOGIN_URL

    def __init__(self, email_monitor=None):
        super().__init__(email_monitor)
        self.form_filler = FormFiller()

    async def login(self) -> bool:
        """Log in to Indeed."""
        if self._logged_in:
            return True

        email = PROFILE.get("email", "")
        password = os.environ.get("INDEED_PASSWORD", "")

        if not password:
            logger.info("[Indeed] No password — will attempt guest apply")
            return True  # Indeed allows guest applications

        page = await self._get_page()
        logger.info("[Indeed] Logging in...")

        await page.goto(INDEED_LOGIN_URL)
        await self._wait_for_navigation(page)
        await self._human_delay(1, 2)

        try:
            # Click "Sign in with email"
            email_btn = page.locator("a:has-text('Sign in with email'), button:has-text('Email')").first
            if await email_btn.is_visible(timeout=3000):
                await email_btn.click()
                await self._human_delay(1, 2)

            await self._human_type(page, "#emailAddress-input, [name='__email']", email)
            await self._human_delay(0.5, 1)
            await self._human_click(page, "button:has-text('Continue')")
            await self._wait_for_navigation(page)
            await self._human_delay(1, 2)

            await self._human_type(page, "#password-input, [name='password']", password)
            await self._human_delay(0.5, 1)
            await self._human_click(page, "button:has-text('Sign in')")
            await self._wait_for_navigation(page, timeout=20000)
            await self._human_delay(2, 3)

            # Handle OTP
            if self.email_monitor and await page.locator("[name='code'], [name='otp']").is_visible(timeout=3000):
                logger.info("[Indeed] OTP required — waiting for email...")
                otp = self.email_monitor.check_for_otp(timeout=120)
                if otp:
                    await self._human_type(page, "[name='code'], [name='otp']", otp)
                    await self._human_click(page, "button:has-text('Continue'), button:has-text('Verify')")
                    await self._wait_for_navigation(page)

            self._logged_in = True
            return True

        except Exception as e:
            logger.warning(f"[Indeed] Login error: {e} — proceeding as guest")
            self._logged_in = True
            return True

    async def apply(self, job: dict) -> dict:
        """Apply to an Indeed job."""
        url = job.get("url", "")
        title = job.get("title", "")
        company = job.get("company", "")

        logger.info(f"[Indeed] Applying to: {title} @ {company}")

        if not self._logged_in:
            await self.login()

        page = await self._get_page()

        try:
            await page.goto(url)
            await self._wait_for_navigation(page)
            await self._human_delay(2, 3)

            # Check for Indeed apply button
            apply_btn_sels = [
                "button:has-text('Apply now')",
                "a:has-text('Apply now')",
                ".jobsearch-IndeedApplyButton",
                "[data-indeed-apply]",
                "#indeedApplyButton",
            ]

            apply_found = False
            for sel in apply_btn_sels:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=3000):
                        await btn.click()
                        apply_found = True
                        await self._human_delay(2, 3)
                        break
                except Exception:
                    pass

            if not apply_found:
                return {"success": False, "status": "skipped",
                        "message": "No Indeed apply button", "application_url": url}

            # Handle the apply flow
            success = await self._handle_apply_flow(page, job)

            if success:
                logger.info(f"[Indeed] ✓ Applied to: {title} @ {company}")
                return {"success": True, "status": "applied",
                        "message": "Applied via Indeed", "application_url": url}
            else:
                return {"success": False, "status": "failed",
                        "message": "Indeed apply flow failed", "application_url": url}

        except Exception as e:
            logger.error(f"[Indeed] Apply error: {e}")
            await self._take_screenshot(page, "indeed_apply_error")
            return {"success": False, "status": "failed", "message": str(e), "application_url": url}

    async def _handle_apply_flow(self, page, job: dict) -> bool:
        """Handle Indeed's multi-step apply flow."""
        max_steps = 8

        for step in range(max_steps):
            await self._human_delay(1, 2)

            # Success detection
            for text in ["Application submitted", "applied successfully", "Thank you for applying"]:
                if text.lower() in (await page.content()).lower():
                    return True

            # Fill visible form fields
            await self.form_filler.fill_form(page, job)
            await self.form_filler.handle_selects(page)
            await self._human_delay(1, 1.5)

            # Handle CAPTCHA
            await captcha_solver.detect_and_solve(page)

            # Next / Submit buttons
            for btn_text in ["Submit your application", "Submit", "Continue", "Next", "Apply"]:
                try:
                    btn = page.locator(f"button:has-text('{btn_text}')").last
                    if await btn.is_visible(timeout=2000):
                        await self._human_click(page, f"button:has-text('{btn_text}')")
                        await self._human_delay(2, 3)
                        break
                except Exception:
                    pass

        return "application" in (await page.content()).lower()

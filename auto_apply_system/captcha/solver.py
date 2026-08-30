"""
captcha/solver.py — CAPTCHA solving module.
Strategy (in order):
  1. CapSolver API (if key configured)
  2. 2Captcha API (if key configured)
  3. Stealth evasion (no CAPTCHA triggered = best outcome)
  4. Manual pause (screenshot + notify user to solve)
"""

import asyncio
import base64
import logging
import time
from typing import Optional, Dict, Any

import httpx

from config import CAPTCHA as CAPTCHA_CONFIG

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# CapSolver API
# ──────────────────────────────────────────────────────────────

CAPSOLVER_API = "https://api.capsolver.com"


async def _capsolver_solve_recaptcha_v2(
    site_key: str, page_url: str, api_key: str
) -> Optional[str]:
    """Solve reCAPTCHA v2 via CapSolver."""
    async with httpx.AsyncClient(timeout=10) as client:
        # Create task
        create_resp = await client.post(f"{CAPSOLVER_API}/createTask", json={
            "clientKey": api_key,
            "task": {
                "type": "ReCaptchaV2Task",
                "websiteURL": page_url,
                "websiteKey": site_key,
            }
        })
        data = create_resp.json()
        if data.get("errorId", 0) != 0:
            logger.error(f"[CapSolver] Create task error: {data.get('errorDescription')}")
            return None

        task_id = data.get("taskId")
        logger.info(f"[CapSolver] Task created: {task_id}")

        # Poll for result
        deadline = time.time() + CAPTCHA_CONFIG["timeout_seconds"]
        while time.time() < deadline:
            await asyncio.sleep(5)
            result_resp = await client.post(f"{CAPSOLVER_API}/getTaskResult", json={
                "clientKey": api_key,
                "taskId": task_id,
            })
            result = result_resp.json()
            status = result.get("status")

            if status == "ready":
                token = result.get("solution", {}).get("gRecaptchaResponse")
                logger.info("[CapSolver] reCAPTCHA solved!")
                return token
            elif status == "processing":
                continue
            else:
                logger.error(f"[CapSolver] Unexpected status: {status}")
                return None

        logger.error("[CapSolver] Timeout waiting for CAPTCHA solution")
        return None


async def _capsolver_solve_hcaptcha(
    site_key: str, page_url: str, api_key: str
) -> Optional[str]:
    """Solve hCAPTCHA via CapSolver."""
    async with httpx.AsyncClient(timeout=10) as client:
        create_resp = await client.post(f"{CAPSOLVER_API}/createTask", json={
            "clientKey": api_key,
            "task": {
                "type": "HCaptchaTask",
                "websiteURL": page_url,
                "websiteKey": site_key,
            }
        })
        data = create_resp.json()
        if data.get("errorId", 0) != 0:
            logger.error(f"[CapSolver] hCaptcha error: {data.get('errorDescription')}")
            return None

        task_id = data.get("taskId")
        deadline = time.time() + CAPTCHA_CONFIG["timeout_seconds"]

        while time.time() < deadline:
            await asyncio.sleep(5)
            result_resp = await client.post(f"{CAPSOLVER_API}/getTaskResult", json={
                "clientKey": api_key,
                "taskId": task_id,
            })
            result = result_resp.json()
            if result.get("status") == "ready":
                token = result.get("solution", {}).get("gRecaptchaResponse")
                logger.info("[CapSolver] hCaptcha solved!")
                return token

        return None


# ──────────────────────────────────────────────────────────────
# 2Captcha API (fallback)
# ──────────────────────────────────────────────────────────────

TWOCAPTCHA_API = "https://2captcha.com"


async def _2captcha_solve_recaptcha_v2(
    site_key: str, page_url: str, api_key: str
) -> Optional[str]:
    """Solve reCAPTCHA v2 via 2Captcha."""
    async with httpx.AsyncClient(timeout=10) as client:
        # Submit CAPTCHA
        submit = await client.get(f"{TWOCAPTCHA_API}/in.php", params={
            "key": api_key,
            "method": "userrecaptcha",
            "googlekey": site_key,
            "pageurl": page_url,
            "json": "1",
        })
        data = submit.json()
        if data.get("status") != 1:
            logger.error(f"[2Captcha] Submit error: {data.get('request')}")
            return None

        captcha_id = data.get("request")
        logger.info(f"[2Captcha] Submitted, id={captcha_id}")

        # Poll
        deadline = time.time() + CAPTCHA_CONFIG["timeout_seconds"]
        while time.time() < deadline:
            await asyncio.sleep(10)
            result = await client.get(f"{TWOCAPTCHA_API}/res.php", params={
                "key": api_key,
                "action": "get",
                "id": captcha_id,
                "json": "1",
            })
            result_data = result.json()
            if result_data.get("status") == 1:
                logger.info("[2Captcha] CAPTCHA solved!")
                return result_data.get("request")
            elif result_data.get("request") == "CAPCHA_NOT_READY":
                continue
            else:
                logger.error(f"[2Captcha] Error: {result_data.get('request')}")
                return None

        return None


# ──────────────────────────────────────────────────────────────
# Main Solver Interface
# ──────────────────────────────────────────────────────────────

class CaptchaSolver:
    """
    Unified CAPTCHA solver. Tries CapSolver → 2Captcha → returns None
    (caller should handle fallback to manual or skip).
    """

    def __init__(self):
        self.capsolver_key = CAPTCHA_CONFIG.get("capsolver_api_key", "")
        self.twocaptcha_key = CAPTCHA_CONFIG.get("two_captcha_api_key", "")
        self.has_solver = bool(self.capsolver_key or self.twocaptcha_key)

        if not self.has_solver:
            logger.info(
                "[CaptchaSolver] No API key configured. "
                "Running in stealth-only mode (CAPTCHA bypass via browser evasion)."
            )

    async def solve_recaptcha_v2(self, site_key: str, page_url: str) -> Optional[str]:
        """Attempt to solve reCAPTCHA v2. Returns token or None."""
        for attempt in range(CAPTCHA_CONFIG.get("max_retries", 3)):
            logger.info(f"[CaptchaSolver] Solving reCAPTCHA v2 (attempt {attempt+1})")

            if self.capsolver_key:
                token = await _capsolver_solve_recaptcha_v2(site_key, page_url, self.capsolver_key)
                if token:
                    return token

            if self.twocaptcha_key:
                token = await _2captcha_solve_recaptcha_v2(site_key, page_url, self.twocaptcha_key)
                if token:
                    return token

            if attempt < CAPTCHA_CONFIG.get("max_retries", 3) - 1:
                await asyncio.sleep(10)

        logger.warning("[CaptchaSolver] All CAPTCHA solve attempts failed")
        return None

    async def solve_hcaptcha(self, site_key: str, page_url: str) -> Optional[str]:
        """Attempt to solve hCAPTCHA. Returns token or None."""
        if self.capsolver_key:
            return await _capsolver_solve_hcaptcha(site_key, page_url, self.capsolver_key)
        logger.warning("[CaptchaSolver] No API key — cannot solve hCAPTCHA")
        return None

    async def inject_recaptcha_token(self, page: Any, token: str):
        """
        Inject a solved reCAPTCHA token into the page.
        'page' is a Playwright page object.
        """
        await page.evaluate(f"""
            document.getElementById('g-recaptcha-response').innerHTML = '{token}';
            if (typeof ___grecaptcha_cfg !== 'undefined') {{
                Object.entries(___grecaptcha_cfg.clients).forEach(([k, v]) => {{
                    if (v && v.R && v.R.callback) v.R.callback('{token}');
                }});
            }}
        """)
        logger.info("[CaptchaSolver] Injected reCAPTCHA token into page")

    async def detect_and_solve(self, page: Any) -> bool:
        """
        Auto-detect and solve any CAPTCHA on the current page.
        Returns True if CAPTCHA was detected+solved (or not present), False if failed.
        """
        page_url = page.url

        # Check for reCAPTCHA
        recaptcha_frame = page.frame_locator("iframe[src*='recaptcha']").first
        try:
            site_key_el = page.locator('[data-sitekey]').first
            site_key = await site_key_el.get_attribute("data-sitekey", timeout=3000)
            if site_key:
                logger.info(f"[CaptchaSolver] Detected reCAPTCHA (sitekey={site_key[:8]}...)")
                token = await self.solve_recaptcha_v2(site_key, page_url)
                if token:
                    await self.inject_recaptcha_token(page, token)
                    return True
                return False
        except Exception:
            pass

        # Check for hCAPTCHA
        try:
            hcaptcha_el = page.locator('[data-hcaptcha-widget-id], iframe[src*="hcaptcha"]').first
            site_key = await hcaptcha_el.get_attribute("data-sitekey", timeout=3000)
            if site_key:
                logger.info(f"[CaptchaSolver] Detected hCAPTCHA (sitekey={site_key[:8]}...)")
                token = await self.solve_hcaptcha(site_key, page_url)
                if token:
                    await page.evaluate(f"""
                        document.querySelector('[name="h-captcha-response"]').value = '{token}';
                    """)
                    return True
                return False
        except Exception:
            pass

        return True  # No CAPTCHA detected


# Singleton instance
captcha_solver = CaptchaSolver()

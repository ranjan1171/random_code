"""
applier/base_applier.py — Abstract base class for all job appliers.
Handles Playwright browser lifecycle, stealth setup, and common form operations.
"""

import asyncio
import logging
import random
import time
from abc import ABC, abstractmethod
from typing import Optional, Any, Dict

from config import APPLICATION, PROFILE

logger = logging.getLogger(__name__)


class BrowserManager:
    """Manages a shared stealth Playwright browser instance."""

    COOKIES_DIR = "session_cookies"

    def __init__(self):
        self._browser = None
        self._context = None
        self._playwright = None

    async def start(self):
        """Launch a stealth Playwright browser."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error(
                "Playwright not installed. Run: "
                "pip install playwright playwright-stealth && playwright install chromium"
            )
            raise

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=APPLICATION["headless"],
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-extensions",
                "--disable-plugins-discovery",
                "--no-first-run",
                "--disable-infobars",
            ],
        )

        self._context = await self._browser.new_context(
            viewport=APPLICATION["viewport"],
            user_agent=APPLICATION["user_agent"],
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            permissions=["geolocation"],
            extra_http_headers={
                "Accept-Language": "en-IN,en;q=0.9,hi;q=0.7",
            },
        )

        logger.info("[BrowserManager] Stealth browser started")
        return self._context

    async def new_page(self):
        """Open a new stealth page."""
        if not self._context:
            await self.start()
        page = await self._context.new_page()

        # Apply stealth patches
        try:
            from playwright_stealth import Stealth
            await Stealth().apply_stealth_async(page)
        except Exception:
            try:
                from playwright_stealth import stealth_async
                await stealth_async(page)
            except Exception as e:
                logger.debug(f"[BrowserManager] Stealth wrapper skipped: {e}")

        # Additional anti-detection JS patches
        await page.add_init_script("""
            // Overwrite navigator.webdriver
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            // Overwrite languages
            Object.defineProperty(navigator, 'languages', { get: () => ['en-IN', 'en'] });
            // Overwrite platform
            Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
        """)
        return page

    async def save_cookies(self, portal: str):
        """Save browser context cookies to disk for reuse across runs."""
        import json, os
        os.makedirs(self.COOKIES_DIR, exist_ok=True)
        path = os.path.join(self.COOKIES_DIR, f"{portal}_cookies.json")
        if self._context:
            cookies = await self._context.cookies()
            with open(path, "w") as f:
                json.dump(cookies, f)
            logger.info(f"[BrowserManager] Saved {len(cookies)} cookies for '{portal}' → {path}")
            return True
        return False

    async def load_cookies(self, portal: str) -> bool:
        """Load previously saved cookies. Returns True if cookies were loaded."""
        import json, os
        path = os.path.join(self.COOKIES_DIR, f"{portal}_cookies.json")
        if not os.path.exists(path):
            return False
        if not self._context:
            await self.start()
        try:
            with open(path) as f:
                cookies = json.load(f)
            await self._context.add_cookies(cookies)
            logger.info(f"[BrowserManager] Loaded {len(cookies)} cookies for '{portal}'")
            return True
        except Exception as e:
            logger.warning(f"[BrowserManager] Failed to load cookies for '{portal}': {e}")
            return False

    def clear_cookies(self, portal: str):
        """Delete saved cookies (e.g. after a session expires)."""
        import os
        path = os.path.join(self.COOKIES_DIR, f"{portal}_cookies.json")
        if os.path.exists(path):
            os.remove(path)
            logger.info(f"[BrowserManager] Cleared cookies for '{portal}'")

    async def stop(self):
        """Close browser and playwright."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("[BrowserManager] Browser stopped")



# Shared browser manager (singleton-like)
_browser_manager: Optional[BrowserManager] = None


async def get_browser_manager() -> BrowserManager:
    global _browser_manager
    if _browser_manager is None:
        _browser_manager = BrowserManager()
        await _browser_manager.start()
    return _browser_manager


class BaseApplier(ABC):
    """
    Abstract base class for portal-specific job appliers.
    Provides human-like typing, clicking, and form operations.
    """

    portal_name: str = "unknown"
    login_url: str = ""

    def __init__(self, email_monitor=None):
        self.email_monitor = email_monitor
        self._logged_in = False
        self._page = None

    async def _get_page(self):
        """Get or create a Playwright page."""
        if self._page is None or self._page.is_closed():
            manager = await get_browser_manager()
            self._page = await manager.new_page()
        return self._page

    # ─────────────────────────────────────────────
    # Human-like interaction helpers
    # ─────────────────────────────────────────────

    async def _human_delay(self, min_s: float = 0.5, max_s: float = 2.0):
        """Random human-like delay."""
        return

    async def _human_type(self, page, selector: str, text: str, clear: bool = True):
        """Type text like a human — with per-character delays and occasional pauses."""
        element = page.locator(selector).first
        await element.click()
        if clear:
            await element.fill("")
        await self._human_delay(0.2, 0.5)

        for char in text:
            await element.type(char, delay=random.randint(40, 130))
            # Occasional thinking pause
            if random.random() < 0.03:
                await self._human_delay(0.3, 0.8)

    async def _human_click(self, page, selector: str):
        """Click element with human-like movement."""
        element = page.locator(selector).first
        await self._human_delay(0.2, 0.6)
        box = await element.bounding_box()
        if box:
            # Click slightly off-center (not pixel-perfect)
            x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
            y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
            await page.mouse.move(x + random.uniform(-5, 5), y + random.uniform(-5, 5))
            await self._human_delay(0.1, 0.3)
            await page.mouse.click(x, y)
        else:
            await element.click()

    async def _scroll_into_view(self, page, selector: str):
        """Scroll element into view with smooth-ish motion."""
        element = page.locator(selector).first
        await element.scroll_into_view_if_needed()
        await self._human_delay(0.3, 0.8)

    async def _wait_for_navigation(self, page, timeout: int = 15000):
        """Wait for page navigation to complete."""
        try:
            await page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception:
            await page.wait_for_load_state("domcontentloaded", timeout=timeout)

    async def _take_screenshot(self, page, label: str = "debug"):
        """Take screenshot for debugging. Auto-cleans old PNGs to prevent disk bloat."""
        try:
            path = f"logs/{label}_{int(time.time())}.png"
            await page.screenshot(path=path)
            logger.info(f"Screenshot saved: {path}")
            # Auto-cleanup: keep only the latest 20 PNG files
            try:
                import glob
                png_files = sorted(glob.glob("logs/*.png"), key=os.path.getmtime)
                if len(png_files) > 20:
                    for old_file in png_files[:-20]:
                        try:
                            os.remove(old_file)
                        except Exception:
                            pass
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"Screenshot failed: {e}")

    # ─────────────────────────────────────────────
    # Abstract methods
    # ─────────────────────────────────────────────

    @abstractmethod
    async def login(self) -> bool:
        """
        Login to the portal. Returns True on success.
        Should handle OTP via email_monitor if needed.
        """
        pass

    @abstractmethod
    async def apply(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply to a job posting. Returns result dict:
        {
            'success': bool,
            'status': str,  # 'applied' | 'skipped' | 'failed' | 'already_applied'
            'message': str,
            'application_url': str,
        }
        """
        pass

    async def apply_safe(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """
        Safe wrapper around apply() — catches all exceptions.
        """
        try:
            return await self.apply(job)
        except Exception as e:
            logger.error(f"[{self.portal_name}] Apply failed for {job.get('title')}: {e}")
            return {
                "success": False,
                "status": "failed",
                "message": str(e),
                "application_url": job.get("url", ""),
            }

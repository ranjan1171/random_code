"""
scrapers/base_scraper.py — Abstract base class for all job scrapers.
All portal-specific scrapers inherit from this.
"""

import uuid
import hashlib
import logging
import asyncio
import time
import random
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

# Shared stealth headers — rotated for each scraper
STEALTH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9,hi;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
}


def make_job_id(portal: str, url: str) -> str:
    """Create a deterministic job ID from portal + URL."""
    raw = f"{portal}:{url}"
    return hashlib.md5(raw.encode()).hexdigest()


class BaseScraper(ABC):
    """
    Abstract base class for job scrapers.
    Provides HTTP client, retry logic, and common job normalization.
    """

    portal_name: str = "unknown"
    request_delay: float = 2.0      # seconds between requests
    max_retries: int = 4

    def __init__(self):
        self.client = httpx.AsyncClient(
            headers=STEALTH_HEADERS,
            timeout=30,
            follow_redirects=True,
        )
        self._last_request_time = 0.0

    async def _throttle(self):
        """Enforce polite request delay with ±50% jitter."""
        elapsed = time.time() - self._last_request_time
        delay = self.request_delay * (0.5 + random.random())
        if elapsed < delay:
            await asyncio.sleep(delay - elapsed)
        self._last_request_time = time.time()

    async def _get(self, url: str, **kwargs) -> Optional[httpx.Response]:
        """HTTP GET with retry + exponential backoff."""
        await self._throttle()
        backoff = 2.0
        for attempt in range(self.max_retries):
            try:
                resp = await self.client.get(url, **kwargs)
                if resp.status_code == 429 or resp.status_code >= 500:
                    jitter = random.uniform(0.5, 1.5)
                    wait = backoff * jitter
                    logger.warning(
                        f"[{self.portal_name}] Rate limited ({resp.status_code}), "
                        f"waiting {wait:.1f}s (attempt {attempt+1})"
                    )
                    await asyncio.sleep(wait)
                    backoff = min(backoff * 2, 30)
                    continue
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                return resp
            except httpx.RequestError as e:
                logger.warning(f"[{self.portal_name}] Request error: {e}, retrying...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
        logger.error(f"[{self.portal_name}] Failed to fetch {url} after {self.max_retries} retries")
        return None

    async def _get_json(self, url: str, **kwargs) -> Optional[Dict]:
        """HTTP GET expecting JSON response."""
        resp = await self._get(url, **kwargs)
        if resp is None:
            return None
        try:
            return resp.json()
        except Exception as e:
            logger.warning(f"[{self.portal_name}] JSON parse error: {e}")
            return None

    def normalize_job(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize a raw job dict into the standard schema:
        {id, portal, title, company, location, url, description, scraped_at}
        """
        now = datetime.utcnow().isoformat()
        url = raw.get("url") or raw.get("applyUrl") or ""
        job_id = raw.get("id") or make_job_id(self.portal_name, url)

        return {
            "id": str(job_id),
            "portal": self.portal_name,
            "title": (raw.get("title") or "").strip(),
            "company": (raw.get("company") or "").strip(),
            "location": (raw.get("location") or "").strip(),
            "url": url.strip(),
            "description": (raw.get("description") or "").strip(),
            "scraped_at": raw.get("scraped_at", now),
            "status": "scraped",
            "score": 0,
            "match_details": {},
            "is_dealbreaker": False,
        }

    @abstractmethod
    async def search(self, query: str, location: str, **kwargs) -> List[Dict[str, Any]]:
        """
        Search for jobs matching the query and location.
        Returns a list of normalized job dicts.
        """
        pass

    @abstractmethod
    async def get_detail(self, job_id: str, url: str) -> Optional[Dict[str, Any]]:
        """
        Fetch full job description for a given job.
        Returns normalized job dict with full description, or None.
        """
        pass

    async def close(self):
        await self.client.aclose()

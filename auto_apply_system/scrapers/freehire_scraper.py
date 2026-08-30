"""
scrapers/freehire_scraper.py — Freehire.dev API scraper.
Uses the freehire.dev public REST API (same data source as the existing
TypeScript CLI tool). No API key required.
"""

import logging
from typing import List, Dict, Any, Optional

from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

FREEHIRE_API = "https://freehire.dev/api/v1/jobs"
FREEHIRE_FACETS = "https://freehire.dev/api/v1/jobs/facets"


def _region_for_location(location: str) -> Optional[str]:
    """Map location string to freehire region code."""
    loc = location.lower()
    if "remote" in loc:
        return None  # will add remote filter instead
    if any(x in loc for x in ["india", "pune", "bangalore", "bengaluru",
                                "hyderabad", "mumbai", "delhi", "chennai"]):
        return "apac"
    return None


def _category_for_query(query: str) -> Optional[str]:
    """Map query to freehire category code."""
    q = query.lower()
    if any(x in q for x in ["backend", "python", "node", "rust", "kafka", "api"]):
        return "backend"
    if any(x in q for x in ["devops", "infra", "platform", "sre", "k8s"]):
        return "devops"
    if any(x in q for x in ["ml", "machine learning", "ai", "data"]):
        return "ml_ai"
    if any(x in q for x in ["full stack", "fullstack"]):
        return "fullstack"
    return None


class FreehireScraper(BaseScraper):
    portal_name = "freehire"
    request_delay = 1.5  # freehire is a small API, be polite

    async def search(self, query: str, location: str, **kwargs) -> List[Dict[str, Any]]:
        """Search freehire.dev public API."""
        params: Dict[str, Any] = {
            "q": query,
            "limit": kwargs.get("count", 25),
            "page": kwargs.get("page", 1),
        }

        # Location facets
        region = _region_for_location(location)
        if region:
            params["region"] = region

        if "remote" in location.lower():
            params["remote"] = "remote"

        # Category facet
        category = _category_for_query(query)
        if category:
            params["category"] = category

        # Date filter
        jobage = kwargs.get("jobage")
        if jobage:
            params["posted_within_days"] = jobage

        logger.info(f"[Freehire] Searching: '{query}' in '{location}'")
        data = await self._get_json(FREEHIRE_API, params=params)

        if data is None:
            return []

        raw_results = data.get("results", [])
        logger.info(f"[Freehire] Found {len(raw_results)} jobs")

        normalized = []
        for r in raw_results:
            location_str = (
                ", ".join(r.get("cities", [])) or
                ", ".join(r.get("countries", [])) or
                ", ".join(r.get("regions", [])) or
                ("Remote" if r.get("work_mode") == "remote" else "")
            )

            raw = {
                "id": f"fh_{r.get('id') or r.get('public_slug', '')}",
                "title": r.get("title", ""),
                "company": r.get("company") or r.get("company_name", ""),
                "location": location_str,
                "url": r.get("url") or f"https://freehire.dev/jobs/{r.get('public_slug', '')}",
                "description": r.get("description") or r.get("snippet") or "",
            }
            normalized.append(self.normalize_job(raw))

        return normalized

    async def get_detail(self, job_id: str, url: str) -> Optional[Dict[str, Any]]:
        """Fetch freehire job detail by slug."""
        slug = job_id.replace("fh_", "")
        detail_url = f"https://freehire.dev/api/v1/jobs/{slug}"

        data = await self._get_json(detail_url)
        if data is None:
            return None

        location_str = (
            ", ".join(data.get("cities", [])) or
            ", ".join(data.get("countries", [])) or
            ("Remote" if data.get("work_mode") == "remote" else "")
        )

        return self.normalize_job({
            "id": job_id,
            "title": data.get("title", ""),
            "company": data.get("company") or data.get("company_name", ""),
            "location": location_str,
            "url": url,
            "description": data.get("description") or "",
        })

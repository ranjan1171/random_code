"""
scrapers/greenhouse_scraper.py — Dedicated Greenhouse Job Scraper.

Scrapes job listings from Greenhouse job boards (job-boards.greenhouse.io & boards.greenhouse.io)
using both official Greenhouse Board APIs and search discovery.
"""

import logging
import re
import html
import asyncio
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

from scrapers.base_scraper import BaseScraper, make_job_id

logger = logging.getLogger(__name__)

# NOTE: Excluded 'andurilindustries' and 'ubiquiti' per user directive
POPULAR_GREENHOUSE_SLUGS = [
    # Autonomous, Defense, Hardware & Robotics
    "axon", "appliedintuition", "skydio", "aurora", "nuro", "jobyaviation", "zipline",

    # Core Infrastructure, Databases & Cloud
    "elastic", "datadog", "github", "hashicorp", "grafanalabs", "confluent", "temporal",
    "mongodb", "yugabyte", "postman", "sentry", "cockroachlabs", "databento", "canonicaljobs",
    "cloudflare", "docker", "databricks", "snowflake", "harness", "buildkite", "circleci",

    # AI, ML & Data Engineering
    "scaleai", "openai", "anthropic", "pinecone", "qdrant", "weaviate", "anyscale",
    "astronomer", "prefect", "dbtlabs", "sigmoid", "sourcegraph", "weightsandbiases",

    # Developer Tools & Web Platforms
    "vercel", "supabase", "automattic", "gitlab", "retool", "linear", "raycast", "workos",
    "clerk", "resend", "posthog", "launchdarkly", "snyk", "semgrep", "gitguardian",

    # High-Growth Tech, Fintech & Enterprise
    "stripe", "discord", "figma", "notion", "coinbase", "reddit", "brex", "plaid", "ramp",
    "robinhood", "chime", "klarna", "toast", "rippling", "gusto", "doordash", "airbnb",
    "gardacp", "simpplr", "dashlane", "mozilla", "blockchain", "taskhuman", "neysanetwork"
]

class GreenhouseScraper(BaseScraper):
    """
    Dynamic Scraper for Greenhouse job postings.
    Discovers company job boards and postings dynamically via search queries
    and company board APIs.
    """

    portal_name = "greenhouse"
    request_delay = 0.5

    async def search(self, query: str = "", location: str = "", **kwargs) -> List[Dict[str, Any]]:
        """
        Dynamically discover and scrape Greenhouse jobs matching candidate skills.
        Queries Greenhouse board APIs directly across all configured top tech companies.
        """
        jobs: List[Dict[str, Any]] = []
        seen_urls = set()
        discovered_slugs = set(POPULAR_GREENHOUSE_SLUGS)

        logger.info(f"[GreenhouseScraper] Fetching job board APIs for {len(discovered_slugs)} top tech companies...")
        sem = asyncio.Semaphore(15)

        async def _fetch_safe(slug):
            async with sem:
                try:
                    return await self.fetch_company_jobs(slug)
                except Exception as e:
                    logger.debug(f"[GreenhouseScraper] Board API fetch for {slug} warning: {e}")
                    return []

        board_results = await asyncio.gather(*[_fetch_safe(s) for s in discovered_slugs])
        for comp_jobs in board_results:
            for j in comp_jobs:
                if j["url"] not in seen_urls:
                    seen_urls.add(j["url"])
                    if self._matches_filter(j, query, location):
                        jobs.append(j)

        logger.info(f"[GreenhouseScraper] Total Greenhouse jobs dynamically discovered: {len(jobs)}")
        return jobs

    async def fetch_company_jobs(self, company_slug: str) -> List[Dict[str, Any]]:
        """Fetch all open jobs for a specific company using Greenhouse public API."""
        url = f"https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs?content=true"
        resp = await self._get_json(url)
        if not resp or "jobs" not in resp:
            return []

        company_name = company_slug.replace("-", " ").title()
        raw_jobs = resp.get("jobs", [])
        parsed_jobs = []

        for item in raw_jobs:
            job_url = item.get("absolute_url") or f"https://job-boards.greenhouse.io/{company_slug}/jobs/{item.get('id')}"
            title = item.get("title", "")
            loc_dict = item.get("location", {})
            location_str = loc_dict.get("name", "Remote") if isinstance(loc_dict, dict) else str(loc_dict)
            
            # Clean HTML from description
            raw_content = item.get("content", "")
            clean_desc = self._clean_html(raw_content)

            parsed_jobs.append({
                "id": make_job_id("greenhouse", job_url),
                "portal": "greenhouse",
                "title": title,
                "company": company_name,
                "company_slug": company_slug,
                "location": location_str,
                "url": job_url,
                "description": clean_desc or f"{title} at {company_name} ({location_str})",
                "scraped_at": self._now_iso(),
            })

        return parsed_jobs

    def _matches_filter(self, job: Dict[str, Any], query: str, location: str) -> bool:
        """Check if a job matches search query and location filters."""
        if not query and not location:
            return True

        title_desc = f"{job['title']} {job['description']}".lower()
        job_loc = job["location"].lower()

        if query:
            keywords = [k.strip().lower() for k in query.split() if len(k) > 2]
            if not any(k in title_desc for k in keywords):
                return False

        if location:
            loc_lower = location.lower()
            if loc_lower not in job_loc and "remote" not in job_loc and "anywhere" not in job_loc:
                return False

        return True

    async def get_detail(self, job_id: str, url: str) -> Optional[Dict[str, Any]]:
        """Fetch full job description for a Greenhouse job URL if needed."""
        if "boards-api.greenhouse.io" in url or "content=true" in url:
            data = await self._get_json(url)
            if data:
                return {
                    "id": job_id,
                    "portal": self.portal_name,
                    "title": data.get("title", ""),
                    "company": data.get("company_slug", "").title(),
                    "location": data.get("location", {}).get("name", "Remote") if isinstance(data.get("location"), dict) else str(data.get("location", "")),
                    "url": url,
                    "description": self._clean_html(data.get("content", "")),
                    "scraped_at": self._now_iso(),
                }
        resp = await self._get(url)
        if resp:
            clean_text = self._clean_html(resp.text)
            return {
                "id": job_id,
                "portal": self.portal_name,
                "title": "Greenhouse Job",
                "company": "Company",
                "location": "Remote",
                "url": url,
                "description": clean_text,
                "scraped_at": self._now_iso(),
            }
        return None

    @staticmethod
    def _clean_html(raw_html: str) -> str:
        """Convert HTML description to clean plain text."""
        if not raw_html:
            return ""
        text = html.unescape(raw_html)
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</li>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    @staticmethod
    def _now_iso() -> str:
        from datetime import datetime
        return datetime.utcnow().isoformat() + "Z"

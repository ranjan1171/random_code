"""
scrapers/wellfound_scraper.py — Wellfound (AngelList Talent) job scraper.
Wellfound has a public GraphQL API that can be used for job search.
"""

import re
import json
import logging
from typing import List, Dict, Any, Optional

from scrapers.base_scraper import BaseScraper, make_job_id

logger = logging.getLogger(__name__)

WELLFOUND_BASE = "https://wellfound.com"
WELLFOUND_API = "https://wellfound.com/api/graphql"

# GraphQL query for job search
JOBS_QUERY = """
query JobSearchQuery($query: String!, $locationSlug: String, $page: Int) {
  talent {
    seoLandingPageJobListings(
      query: $query
      locationSlug: $locationSlug
      page: $page
    ) {
      startups {
        name
        companyUrl: url
        jobListings {
          id
          title
          remote
          locationNames
          description
          applyUrl
          liveStartAt
          jobType
          salary
          equityMin
          equityMax
        }
      }
      totalCount
    }
  }
}
"""

# Simple HTML scraper as fallback (public pages)
WELLFOUND_SEARCH_URL = "https://wellfound.com/role/l/software-engineer/india"


def _parse_wellfound_html(html: str) -> List[Dict]:
    """Parse Wellfound's public search page (JSON in page state)."""
    results = []

    # Try to extract Next.js page data
    data_m = re.search(r'<script id="__NEXT_DATA__" type="application/json">([\s\S]*?)</script>', html, re.I)
    if not data_m:
        return results

    try:
        page_data = json.loads(data_m.group(1))
        # Navigate the nested structure
        props = page_data.get("props", {}).get("pageProps", {})
        listings = (
            props.get("jobListings") or
            props.get("data", {}).get("jobListings") or
            []
        )

        for listing in listings:
            startup = listing.get("startup") or listing.get("company") or {}
            jl = listing.get("jobListing") or listing

            job_id = jl.get("id") or make_job_id("wellfound", jl.get("applyUrl", ""))
            location = ", ".join(jl.get("locationNames") or []) or (
                "Remote" if jl.get("remote") else "India"
            )

            results.append({
                "id": f"wf_{job_id}",
                "title": jl.get("title", ""),
                "company": startup.get("name") or startup.get("company", ""),
                "location": location,
                "url": jl.get("applyUrl") or f"{WELLFOUND_BASE}/jobs/{job_id}",
                "description": jl.get("description") or "",
            })
    except Exception as e:
        logger.debug(f"[Wellfound] JSON parse error: {e}")

    return results


class WellfoundScraper(BaseScraper):
    portal_name = "wellfound"
    request_delay = 3.0

    async def search(self, query: str, location: str, **kwargs) -> List[Dict[str, Any]]:
        """
        Search Wellfound for tech startup jobs.
        Falls back to public HTML scraping if GraphQL fails.
        """
        logger.info(f"[Wellfound] Searching: '{query}' in '{location}'")

        # Try public search page
        location_slug = "india"
        if "remote" in location.lower():
            location_slug = "remote"
        elif "bangalore" in location.lower() or "bengaluru" in location.lower():
            location_slug = "bangalore"
        elif "mumbai" in location.lower():
            location_slug = "mumbai"
        elif "hyderabad" in location.lower():
            location_slug = "hyderabad"
        elif "pune" in location.lower():
            location_slug = "pune"

        url = f"{WELLFOUND_BASE}/role/r/{self._query_to_slug(query)}/{location_slug}"
        resp = await self._get(url)

        if resp is None:
            return []

        raw_jobs = _parse_wellfound_html(resp.text)
        logger.info(f"[Wellfound] Found {len(raw_jobs)} jobs for '{query}' in '{location}'")

        return [self.normalize_job(j) for j in raw_jobs]

    def _query_to_slug(self, query: str) -> str:
        """Convert query to Wellfound URL slug."""
        slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
        # Map common queries to known Wellfound role slugs
        mappings = {
            "backend-engineer": "backend-engineer",
            "software-developer": "software-developer",
            "backend-developer": "backend-engineer",
            "python-developer": "python-developer",
            "software-engineer": "software-engineer",
        }
        return mappings.get(slug, "software-engineer")

    async def get_detail(self, job_id: str, url: str) -> Optional[Dict[str, Any]]:
        """Fetch Wellfound job details."""
        resp = await self._get(url)
        if resp is None:
            return None

        html = resp.text
        data_m = re.search(r'<script id="__NEXT_DATA__" type="application/json">([\s\S]*?)</script>', html, re.I)
        if not data_m:
            return None

        try:
            page_data = json.loads(data_m.group(1))
            props = page_data.get("props", {}).get("pageProps", {})
            jl = props.get("jobListing") or {}
            startup = props.get("startup") or {}

            return self.normalize_job({
                "id": job_id,
                "title": jl.get("title", ""),
                "company": startup.get("name", ""),
                "location": ", ".join(jl.get("locationNames") or []) or "India",
                "url": url,
                "description": jl.get("description") or "",
            })
        except Exception as e:
            logger.debug(f"[Wellfound] Detail parse error: {e}")
            return None

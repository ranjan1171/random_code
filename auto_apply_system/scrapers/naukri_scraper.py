"""
scrapers/naukri_scraper.py — Naukri.com job scraper.
Uses Naukri's internal search API (JSON) — discovered via browser network inspection.
No auth needed for reading. Login only needed for applying.
"""

import re
import logging
from typing import List, Dict, Any, Optional
from urllib.parse import quote

from scrapers.base_scraper import BaseScraper, make_job_id

logger = logging.getLogger(__name__)

# Naukri's internal API (reverse-engineered from browser network tab)
NAUKRI_API_URL = "https://www.naukri.com/jobapi/v3/search"
NAUKRI_HTML_SEARCH = "https://www.naukri.com"

# Headers required by Naukri's API — 406 occurs without these
NAUKRI_HEADERS_EXTRA = {
    "appid": "109",
    "systemid": "109",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Referer": "https://www.naukri.com/",
    "X-Requested-With": "XMLHttpRequest",
    "Naukri-Gw-Version": "2",
    "clientid": "d3skt0p",
}



def _extract_skills(job_data: Dict) -> str:
    """Extract skill tags from Naukri job data."""
    tags = job_data.get("tagsAndSkills", "") or ""
    key_skills = job_data.get("keySkills", {})
    if isinstance(key_skills, dict):
        label = key_skills.get("label", "")
        return f"{tags} {label}".strip()
    return tags


def _build_description(job_data: Dict) -> str:
    """Build a description string from Naukri job fields."""
    parts = []
    if job_data.get("jobDescription"):
        parts.append(job_data["jobDescription"])
    skills = _extract_skills(job_data)
    if skills:
        parts.append(f"Skills: {skills}")
    exp = job_data.get("experienceText")
    if exp:
        parts.append(f"Experience: {exp}")
    salary = job_data.get("placeholders", [{}])
    for ph in salary:
        if ph.get("type") == "salary":
            parts.append(f"Salary: {ph.get('label', '')}")
        if ph.get("type") == "experience":
            parts.append(f"Experience: {ph.get('label', '')}")
    return "\n".join(parts)


class NaukriScraper(BaseScraper):
    portal_name = "naukri"
    request_delay = 2.5

    def __init__(self):
        super().__init__()
        # Update client headers for Naukri
        self.client.headers.update(NAUKRI_HEADERS_EXTRA)

    async def search(self, query: str, location: str, **kwargs) -> List[Dict[str, Any]]:
        """Search Naukri using their internal JSON API."""
        page = kwargs.get("page", 1)
        count = kwargs.get("count", 20)

        # Build Naukri-specific URL path
        # Naukri uses keyword-in-location pattern in URL
        kw_slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
        loc_slug = re.sub(r"[^a-z0-9]+", "-", location.lower()).strip("-")

        params = {
            "noOfResults": str(count),
            "urlType": "search_by_keyword",
            "searchType": "adv",
            "keyword": query,
            "location": location,
            "pageNo": str(page),
            "sort": "r",           # r = relevance, d = date
            "functionAreaIdGte": "0",
        }

        logger.info(f"[Naukri] Searching: '{query}' in '{location}' (page {page})")

        resp = await self._get(NAUKRI_API_URL, params=params)
        if resp is None:
            return []

        try:
            data = resp.json()
        except Exception as e:
            logger.warning(f"[Naukri] JSON parse error: {e}")
            return []

        job_list = data.get("jobDetails", [])
        logger.info(f"[Naukri] Found {len(job_list)} jobs for '{query}' in '{location}'")

        results = []
        for job in job_list:
            url = job.get("jdURL", "") or job.get("jobId", "")
            if url and not url.startswith("http"):
                url = f"https://www.naukri.com{url}"

            job_id = job.get("jobId") or make_job_id("naukri", url)

            raw = {
                "id": f"nk_{job_id}",
                "title": job.get("title", ""),
                "company": job.get("companyName", ""),
                "location": ", ".join(job.get("placeholders", [{}])[0:1]),
                "url": url,
                "description": _build_description(job),
            }
            # Better location extraction
            for ph in job.get("placeholders", []):
                if ph.get("type") == "location":
                    raw["location"] = ph.get("label", raw["location"])
                    break

            results.append(self.normalize_job(raw))

        return results

    async def get_detail(self, job_id: str, url: str) -> Optional[Dict[str, Any]]:
        """Fetch full Naukri job page (HTML scrape)."""
        if not url.startswith("http"):
            url = f"https://www.naukri.com{url}"

        resp = await self._get(url)
        if resp is None:
            return None

        html = resp.text

        # Parse description from HTML
        desc_m = re.search(
            r'class="job-desc[^"]*"[^>]*>([\s\S]*?)</div>',
            html, re.I
        )
        description = ""
        if desc_m:
            description = re.sub(r"<[^>]+>", " ", desc_m.group(1))
            description = re.sub(r"\s+", " ", description).strip()

        skills_m = re.search(
            r'class="key-skill[^"]*"[^>]*>([\s\S]*?)</div>',
            html, re.I
        )
        if skills_m:
            skills_text = re.sub(r"<[^>]+>", " ", skills_m.group(1)).strip()
            description = f"{description}\n\nKey Skills: {skills_text}" if description else skills_text

        return self.normalize_job({
            "id": job_id,
            "url": url,
            "description": description,
        })

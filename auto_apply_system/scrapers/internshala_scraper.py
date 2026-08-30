"""
scrapers/internshala_scraper.py — Internshala job scraper.
Scrapes entry-level and fresher jobs from Internshala's public pages.
Good source for junior SDE, Backend Developer positions in India.
"""

import re
import json
import logging
from typing import List, Dict, Any, Optional
from urllib.parse import urlencode

from scrapers.base_scraper import BaseScraper, make_job_id

logger = logging.getLogger(__name__)

INTERNSHALA_BASE = "https://internshala.com"
INTERNSHALA_JOBS_URL = "https://internshala.com/jobs"
INTERNSHALA_API = "https://internshala.com/jobs/matching_preference"


def _parse_internshala_html(html: str, base_url: str = INTERNSHALA_BASE) -> List[Dict]:
    """Parse Internshala job listing cards."""
    results = []

    # Internshala embeds job data in JSON inside a script tag
    json_m = re.search(r'var listed_jobs\s*=\s*(\{[\s\S]*?\})\s*;', html)
    if json_m:
        try:
            listed = json.loads(json_m.group(1))
            jobs_list = listed.get("jobs_list", [])
            for job in jobs_list:
                job_id = str(job.get("id", ""))
                title = job.get("job_title", "") or job.get("title", "")
                company = job.get("company_name", "") or job.get("employer_name", "")
                location = ", ".join(job.get("location_names", [])) or job.get("location", "")
                url = job.get("job_detail_link") or f"{base_url}/jobs/detail/{job_id}"
                if url and not url.startswith("http"):
                    url = f"{base_url}{url}"

                if job_id and title:
                    results.append({
                        "id": f"is_{job_id}",
                        "title": title,
                        "company": company,
                        "location": location,
                        "url": url,
                        "description": job.get("job_description", ""),
                    })
            return results
        except Exception as e:
            logger.debug(f"[Internshala] JSON parse error: {e}")

    # HTML fallback: parse job containers
    # Job cards have class "individual_internship" or "individual_job"
    card_splits = re.split(r'class="(?:individual_internship|individual_job)[^"]*"', html)[1:]
    for card in card_splits[:20]:
        # ID
        id_m = re.search(r'data-internship_id="(\d+)"|data-job_id="(\d+)"', card)
        job_id = (id_m.group(1) or id_m.group(2)) if id_m else ""

        # Title
        title_m = re.search(r'class="job-internship-name[^"]*"[^>]*>\s*<[^>]+>\s*([^<]+)', card, re.I)
        title = title_m.group(1).strip() if title_m else ""

        # Company
        comp_m = re.search(r'class="company-name[^"]*"[^>]*>([^<]+)', card, re.I)
        company = comp_m.group(1).strip() if comp_m else ""

        # Location
        loc_m = re.search(r'class="location_link[^"]*"[^>]*>([^<]+)', card, re.I)
        location = loc_m.group(1).strip() if loc_m else ""

        if job_id and title:
            url = f"{base_url}/jobs/detail/{job_id}"
            results.append({
                "id": f"is_{job_id}",
                "title": title,
                "company": company,
                "location": location,
                "url": url,
                "description": "",
            })

    return results


class IntershalaScraper(BaseScraper):
    portal_name = "internshala"
    request_delay = 2.0

    async def search(self, query: str, location: str, **kwargs) -> List[Dict[str, Any]]:
        """Search Internshala jobs."""
        # Build Internshala search URL
        # Format: /jobs/keyword-city
        kw = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
        loc = re.sub(r"[^a-z0-9]+", "-", location.lower()).strip("-")

        # Internshala uses a path-based search URL
        search_url = f"{INTERNSHALA_JOBS_URL}/{kw}-jobs-in-{loc}"
        if "remote" in location.lower():
            search_url = f"{INTERNSHALA_JOBS_URL}/{kw}-jobs-work-from-home-jobs"

        logger.info(f"[Internshala] Searching: '{query}' in '{location}'")

        resp = await self._get(search_url)
        if resp is None:
            # Try simpler URL
            resp = await self._get(f"{INTERNSHALA_JOBS_URL}/{kw}-jobs")
            if resp is None:
                return []

        raw_jobs = _parse_internshala_html(resp.text)
        logger.info(f"[Internshala] Found {len(raw_jobs)} jobs")

        return [self.normalize_job(j) for j in raw_jobs]

    async def get_detail(self, job_id: str, url: str) -> Optional[Dict[str, Any]]:
        """Fetch full Internshala job details."""
        resp = await self._get(url)
        if resp is None:
            return None

        html = resp.text

        desc_m = re.search(
            r'class="internship-detail-description[^"]*"[^>]*>([\s\S]*?)</div>',
            html, re.I
        )
        description = ""
        if desc_m:
            description = re.sub(r"<[^>]+>", " ", desc_m.group(1))
            description = re.sub(r"\s+", " ", description).strip()

        skills_m = re.search(r'class="round_tabs_container[^"]*"[^>]*>([\s\S]*?)</div>', html, re.I)
        if skills_m:
            skills = re.findall(r"<[^>]+>([^<]+)</", skills_m.group(1))
            skills_text = ", ".join(s.strip() for s in skills if s.strip())
            if skills_text:
                description = f"{description}\n\nSkills Required: {skills_text}"

        return self.normalize_job({
            "id": job_id,
            "url": url,
            "description": description,
        })

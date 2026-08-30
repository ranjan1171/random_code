"""
scrapers/linkedin_scraper.py — LinkedIn job scraper.
Uses LinkedIn's public jobs-guest API (no auth needed for search).
Mirrors the logic from the existing TypeScript linkedin-search CLI.
"""

import re
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from scrapers.base_scraper import BaseScraper, make_job_id

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting"


def _clean(html: str) -> str:
    """Strip HTML tags and decode common entities."""
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = (text
            .replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            .replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " "))
    return re.sub(r"\s+", " ", text).strip()


def _jobage_to_tpr(days: int) -> Optional[str]:
    if not days or days >= 9999:
        return None
    return f"r{days * 86400}"


def _work_type(mode: Optional[str]) -> Optional[str]:
    mapping = {"remote": "2", "hybrid": "3", "onsite": "1", "on-site": "1"}
    return mapping.get((mode or "").lower())


def _parse_job_cards(html: str) -> List[Dict]:
    """Parse LinkedIn search results HTML into job card dicts."""
    results = []
    chunks = html.split('data-entity-urn="urn:li:jobPosting:')[1:]

    for chunk in chunks:
        id_match = re.match(r'^(\d+)', chunk)
        if not id_match:
            continue
        job_id = id_match.group(1)

        # URL
        link_m = re.search(r'class="base-card__full-link[^"]*"[^>]*href="([^"]+)"', chunk, re.I)
        url = _clean(link_m.group(1)).split("?")[0] if link_m else f"https://www.linkedin.com/jobs/view/{job_id}"

        # Title
        title = None
        h3 = re.search(r'class="base-search-card__title"[^>]*>([\s\S]*?)</h3>', chunk, re.I)
        if h3:
            title = _clean(h3.group(1))
        if not title:
            sr = re.search(r'class="sr-only"[^>]*>([\s\S]*?)</span>', chunk, re.I)
            if sr:
                title = _clean(sr.group(1))
        if not title:
            continue

        # Company
        company = None
        company_url = None
        sub = re.search(r'class="base-search-card__subtitle"[^>]*>([\s\S]*?)</h4>', chunk, re.I)
        if sub:
            a = re.search(r'href="([^"]+)"', sub.group(1), re.I)
            if a:
                company_url = _clean(a.group(1)).split("?")[0]
            company = _clean(sub.group(1)) or None

        # Location + date
        loc = re.search(r'class="job-search-card__location"[^>]*>([\s\S]*?)</span>', chunk, re.I)
        location = _clean(loc.group(1)) if loc else None
        dt = re.search(r'class="job-search-card__listdate[^"]*"[^>]*datetime="([^"]+)"', chunk, re.I)
        date = dt.group(1) if dt else None

        results.append({
            "id": f"li_{job_id}",
            "title": title,
            "company": company,
            "company_url": company_url,
            "location": location,
            "date": date,
            "url": url,
        })

    return results


def _parse_job_detail(html: str, job_id: str) -> Dict:
    """Parse LinkedIn single-job detail page."""
    # Title
    title_m = re.search(r'class="(?:top-card-layout__title|topcard__title)[^"]*"[^>]*>([\s\S]*?)</h[12]>', html, re.I)
    title = _clean(title_m.group(1)) if title_m else "(untitled)"

    # Company
    org_m = re.search(r'class="topcard__org-name-link[^"]*"[^>]*href="([^"]+)"[^>]*>([\s\S]*?)</a>', html, re.I)
    company = _clean(org_m.group(2)) if org_m else None

    # Location
    loc_m = re.search(r'class="topcard__flavor topcard__flavor--bullet"[^>]*>([\s\S]*?)</span>', html, re.I)
    location = _clean(loc_m.group(1)) if loc_m else None

    # Description
    desc_m = re.search(
        r'class="(?:show-more-less-html__markup|description__text[^"]*)"[^>]*>([\s\S]*?)</div>',
        html, re.I
    )
    description = None
    if desc_m:
        raw = desc_m.group(1)
        raw = re.sub(r'<\s*br\s*/?>', '\n', raw, flags=re.I)
        raw = re.sub(r'</(p|li|ul|ol|div|h\d)>', '\n', raw, flags=re.I)
        description = _clean(raw).replace('\n ', '\n').strip() or None

    # Criteria
    criteria = {}
    crit_re = re.compile(
        r'class="description__job-criteria-subheader"[^>]*>([\s\S]*?)</h3>[\s\S]*?'
        r'class="description__job-criteria-text[^"]*"[^>]*>([\s\S]*?)</span>',
        re.I
    )
    for m in crit_re.finditer(html):
        criteria[_clean(m.group(1)).lower()] = _clean(m.group(2))

    apply_m = re.search(r'class="topcard__link[^"]*"[^>]*href="([^"]+)"', html, re.I)
    apply_url = _clean(apply_m.group(1)).split("?")[0] if apply_m else None

    return {
        "id": f"li_{job_id}",
        "title": title,
        "company": company,
        "location": location,
        "url": f"https://www.linkedin.com/jobs/view/{job_id}",
        "description": description,
        "seniority": criteria.get("seniority level"),
        "employment_type": criteria.get("employment type"),
        "job_function": criteria.get("job function"),
        "industries": criteria.get("industries"),
        "apply_url": apply_url,
    }


class LinkedInScraper(BaseScraper):
    portal_name = "linkedin"
    request_delay = 3.0  # LinkedIn rate-limits aggressively

    async def search(self, query: str, location: str, **kwargs) -> List[Dict[str, Any]]:
        """
        Search LinkedIn jobs-guest API.
        Returns list of normalized job dicts.
        """
        params = {
            "keywords": query,
            "location": location,
            "start": str(kwargs.get("page", 0) * 10),
            "pageNum": str(kwargs.get("page", 0)),
        }

        jobage = kwargs.get("jobage")
        if jobage:
            tpr = _jobage_to_tpr(int(jobage))
            if tpr:
                params["f_TPR"] = tpr

        work_mode = kwargs.get("remote")
        if work_mode:
            wt = _work_type(work_mode)
            if wt:
                params["f_WT"] = wt

        logger.info(f"[LinkedIn] Searching: '{query}' in '{location}'")
        resp = await self._get(SEARCH_URL, params=params)
        if resp is None:
            return []

        try:
            html = resp.text
        except Exception:
            return []

        raw_jobs = _parse_job_cards(html)
        logger.info(f"[LinkedIn] Found {len(raw_jobs)} jobs for '{query}' in '{location}'")

        normalized = []
        for rj in raw_jobs:
            nj = self.normalize_job(rj)
            normalized.append(nj)

        return normalized

    async def get_detail(self, job_id: str, url: str) -> Optional[Dict[str, Any]]:
        """Fetch full job details from LinkedIn."""
        # Extract numeric ID from our prefixed ID
        numeric_id = job_id.replace("li_", "")

        detail_url = f"{DETAIL_URL}/{numeric_id}"
        resp = await self._get(detail_url)
        if resp is None:
            return None

        detail = _parse_job_detail(resp.text, numeric_id)
        return self.normalize_job(detail)

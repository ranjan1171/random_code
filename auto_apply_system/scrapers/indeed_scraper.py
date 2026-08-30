"""
scrapers/indeed_scraper.py — Indeed India job scraper.
Scrapes in.indeed.com search results via HTML parsing.
No auth required for searching.
"""

import re
import json
import logging
from typing import List, Dict, Any, Optional
from urllib.parse import urlencode

from scrapers.base_scraper import BaseScraper, make_job_id

logger = logging.getLogger(__name__)

INDEED_BASE = "https://in.indeed.com"
INDEED_SEARCH = "https://in.indeed.com/jobs"


def _extract_json_ld(html: str) -> Optional[Dict]:
    """Try to extract JSON-LD job data from page."""
    m = re.search(r'<script type="application/json"[^>]*id="mosaic-data"[^>]*>([\s\S]*?)</script>', html, re.I)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    return None


def _parse_indeed_cards(html: str) -> List[Dict]:
    """Parse Indeed search result cards from HTML."""
    results = []

    # Indeed job cards have data-jk (job key) attribute
    card_pattern = re.compile(
        r'data-jk="([^"]+)".*?class="jobTitle[^"]*"[^>]*>.*?'
        r'<(?:a|span)[^>]*>([^<]+)<',
        re.I | re.S
    )

    # Try direct JSON from Indeed's internal state
    state_m = re.search(r'window\.mosaic\.providerData\["mosaic-provider-jobcards"\]\s*=\s*(\{[\s\S]*?\});', html)
    if state_m:
        try:
            state = json.loads(state_m.group(1))
            results_data = state.get("metaData", {}).get("mosaicProviderJobCardsModel", {}).get("results", [])

            for job in results_data:
                jk = job.get("jobkey", "")
                title = job.get("displayTitle") or job.get("normTitle") or job.get("title") or ""
                company = job.get("company", "")
                location = job.get("formattedLocation") or job.get("jobLocationCity") or ""
                url = f"{INDEED_BASE}/rc/clk?jk={jk}" if jk else ""

                if jk and title:
                    results.append({
                        "id": f"in_{jk}",
                        "title": title,
                        "company": company,
                        "location": location,
                        "url": f"{INDEED_BASE}/viewjob?jk={jk}",
                        "description": job.get("snippet", ""),
                    })

            if results:
                return results
        except (json.JSONDecodeError, AttributeError, KeyError) as e:
            logger.debug(f"[Indeed] JSON state parse failed: {e}")

    # Fallback: HTML pattern matching
    jk_pattern = re.compile(r'data-jk="([a-f0-9]+)"')
    title_pattern = re.compile(r'class="jobTitle[^"]*"[^>]*>[\s\S]*?<(?:a|span)[^>]*>\s*([^<]+)\s*</')
    company_pattern = re.compile(r'class="companyName"[^>]*>([\s\S]*?)</span>')
    location_pattern = re.compile(r'class="companyLocation"[^>]*>([\s\S]*?)</div>')

    # Split on job cards
    card_splits = re.split(r'data-jk="', html)[1:]
    for card in card_splits:
        jk_m = re.match(r'^([a-f0-9]+)"', card)
        if not jk_m:
            continue
        jk = jk_m.group(1)

        title_m = title_pattern.search(card)
        title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip() if title_m else ""

        company_m = company_pattern.search(card)
        company = re.sub(r"<[^>]+>", "", company_m.group(1)).strip() if company_m else ""

        location_m = location_pattern.search(card)
        location = re.sub(r"<[^>]+>", "", location_m.group(1)).strip() if location_m else ""

        if jk and title:
            results.append({
                "id": f"in_{jk}",
                "title": title,
                "company": company,
                "location": location,
                "url": f"{INDEED_BASE}/viewjob?jk={jk}",
                "description": "",
            })

    return results


class IndeedScraper(BaseScraper):
    portal_name = "indeed"
    request_delay = 3.0

    async def search(self, query: str, location: str, **kwargs) -> List[Dict[str, Any]]:
        """Search Indeed India for jobs."""
        start = kwargs.get("page", 0) * 15

        params = {
            "q": query,
            "l": location,
            "start": start,
            "fromage": kwargs.get("jobage", ""),  # days old
            "sort": "date",
        }
        # Remove empty params
        params = {k: v for k, v in params.items() if v != ""}

        url = f"{INDEED_SEARCH}?{urlencode(params)}"
        logger.info(f"[Indeed] Searching: '{query}' in '{location}'")

        resp = await self._get(url)
        if resp is None:
            return []

        raw_jobs = _parse_indeed_cards(resp.text)
        logger.info(f"[Indeed] Found {len(raw_jobs)} jobs for '{query}' in '{location}'")

        return [self.normalize_job(j) for j in raw_jobs]

    async def get_detail(self, job_id: str, url: str) -> Optional[Dict[str, Any]]:
        """Fetch full Indeed job description."""
        jk = job_id.replace("in_", "")
        detail_url = f"{INDEED_BASE}/viewjob?jk={jk}"

        resp = await self._get(detail_url)
        if resp is None:
            return None

        html = resp.text

        # Try JSON-LD structured data first
        jld_m = re.search(r'<script type="application/ld\+json">([\s\S]*?)</script>', html, re.I)
        if jld_m:
            try:
                jld = json.loads(jld_m.group(1))
                description = jld.get("description", "")
                description = re.sub(r"<[^>]+>", " ", description)
                description = re.sub(r"\s+", " ", description).strip()
                return self.normalize_job({
                    "id": job_id,
                    "title": jld.get("title", ""),
                    "company": (jld.get("hiringOrganization") or {}).get("name", ""),
                    "location": (jld.get("jobLocation") or {}).get("name") or
                                (jld.get("jobLocation") or [{}])[0].get("address", {}).get("addressLocality", ""),
                    "url": url,
                    "description": description,
                })
            except Exception:
                pass

        # HTML fallback
        desc_m = re.search(r'id="jobDescriptionText"[^>]*>([\s\S]*?)</div>', html, re.I)
        description = ""
        if desc_m:
            description = re.sub(r"<[^>]+>", " ", desc_m.group(1))
            description = re.sub(r"\s+", " ", description).strip()

        return self.normalize_job({
            "id": job_id,
            "url": url,
            "description": description,
        })

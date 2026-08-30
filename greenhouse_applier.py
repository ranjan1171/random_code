"""
applier/greenhouse_applier.py — Advanced AI-powered Greenhouse job application bot.

Features:
  - Intelligent field detection using multiple strategies (CSS, XPath, ARIA, labels)
  - Smart React-Select interaction with fuzzy matching
  - Context-aware answer selection using NLP and pattern matching
  - Email verification code auto-detection from Gmail
  - Comprehensive error handling and logging
  - Screenshot capture at critical points
  - HTML dump for debugging failures
  - Self-learning answer database (ranjan.txt)
  - Multi-frame support (handles iframes)
  - Anti-bot detection avoidance with human-like delays
  - Retry logic for failed submissions
  - Success/failure detection with multiple signals
  - Activity logging for monitoring

Usage (standalone):
    python applier/greenhouse_applier.py --url "https://job-boards.greenhouse.io/company/jobs/12345"

Usage (integrated):
    from applier.greenhouse_applier import GreenhouseApplier
    applier = GreenhouseApplier()
    result = await applier.apply({"url": "...", "title": "...", "company": "..."})
"""

import asyncio
import logging
import os
import re
import sys
import json
import time
import random
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import PROFILE, APPLICATION
from applier.base_applier import BaseApplier

# Optional imports with graceful fallback
try:
    from activity_logger import log_apply_start, log_field_fill, log_dropdown, log_apply_success, log_apply_fail
except ImportError:
    def log_apply_start(*args, **kwargs): pass
    def log_field_fill(*args, **kwargs): pass
    def log_dropdown(*args, **kwargs): pass
    def log_apply_success(*args, **kwargs): pass
    def log_apply_fail(*args, **kwargs): pass

try:
    from qa_engine import get_qa_engine
    QA_ENGINE_AVAILABLE = True
except ImportError:
    QA_ENGINE_AVAILABLE = False
    def get_qa_engine(): return None

logger = logging.getLogger(__name__)


class GreenhouseApplier(BaseApplier):
    """
    Advanced auto-apply bot for Greenhouse job boards.
    
    Handles:
    - Standard application fields
    - Custom questions with intelligent answer matching
    - React-Select dropdowns with fuzzy search
    - File uploads (resume, cover letter)
    - Email verification codes
    - Multi-page application flows
    - Success/failure detection
    """

    portal_name = "greenhouse"
    login_url = None

    # ─── Profile Properties ───────────────────────────────────────────
    @property
    def _first_name(self) -> str:
        parts = PROFILE.get("name", "Ranjan Kumar").split()
        return parts[0] if parts else "Ranjan"

    @property
    def _last_name(self) -> str:
        parts = PROFILE.get("name", "Ranjan Kumar").split()
        return parts[-1] if len(parts) > 1 else "Kumar"

    @property
    def _full_name(self) -> str:
        return PROFILE.get("name", "Ranjan Kumar")

    @property
    def _email(self) -> str:
        return PROFILE.get("email", "")

    @property
    def _phone(self) -> str:
        raw = PROFILE.get("phone", "7992272611")
        digits = re.sub(r'\D', '', raw)
        # Strip leading country code 91 if present
        if digits.startswith("91") and len(digits) == 12:
            digits = digits[2:]
        # Ensure max 10 digits to avoid "Phone number is too long" error
        return digits[-10:] if len(digits) >= 10 else digits

    @property
    def _phone_with_country(self) -> str:
        return f"+91{self._phone}"

    @property
    def _linkedin_url(self) -> str:
        return PROFILE.get("linkedin", "") or PROFILE.get("linkedin_url", 
               "https://www.linkedin.com/in/ranjan-kumar-910449182/")

    @property
    def _github_url(self) -> str:
        return PROFILE.get("github", "") or PROFILE.get("github_url", 
               "https://github.com/ranjan1171")

    @property
    def _portfolio_url(self) -> str:
        return PROFILE.get("portfolio", "") or PROFILE.get("website", "")

    @property
    def _location(self) -> str:
        return PROFILE.get("location", "Pune, Maharashtra, India")

    @property
    def _city(self) -> str:
        return PROFILE.get("city", "Pune")

    @property
    def _state(self) -> str:
        return PROFILE.get("state", "Maharashtra")

    @property
    def _country(self) -> str:
        return PROFILE.get("country", "India")

    @property
    def _cv_path(self) -> str:
        return PROFILE.get("cv_pdf_path", "")

    @property
    def _cover_letter_path(self) -> str:
        return PROFILE.get("cover_letter_path", "")

    @property
    def _years_experience(self) -> str:
        return str(PROFILE.get("years_experience", "3"))

    @property
    def _notice_period(self) -> str:
        return PROFILE.get("notice_period", "Immediately")

    @property
    def _expected_salary(self) -> str:
        return PROFILE.get("expected_salary", "1300000")

    @property
    def _current_company(self) -> str:
        return PROFILE.get("current_company", "WhiteKlay")

    @property
    def _current_role(self) -> str:
        return PROFILE.get("current_role", "Software Developer 1")

    @property
    def _education(self) -> str:
        return PROFILE.get("education", "Bachelor's Degree")

    @property
    def _university(self) -> str:
        return PROFILE.get("university", "National Institute of Technology, Jamshedpur")

    @property
    def _university_aliases(self) -> List[str]:
        """Multiple search terms to try in React-Select school dropdowns."""
        return [
            "National Institute of Technology, Jamshedpur",
            "National Institute of Technology Jamshedpur",
            "NIT Jamshedpur",
            "NIT, Jamshedpur",
            "Jamshedpur",
        ]

    @property
    def _discipline(self) -> str:
        return PROFILE.get("discipline", "Electronics and Communications Engineering")

    @property
    def _graduation_year(self) -> str:
        return str(PROFILE.get("graduation_year", "2025"))

    @property
    def _edu_start_month(self) -> str:
        return "06"  # June 2021

    @property
    def _edu_start_year(self) -> str:
        return "2021"

    @property
    def _edu_end_month(self) -> str:
        return "06"  # June 2025

    @property
    def _edu_end_year(self) -> str:
        return "2025"

    @property
    def _skills(self) -> List[str]:
        return PROFILE.get("skills", ["Python", "C++", "Rust", "Kafka", 
                                     "PostgreSQL", "Redis", "Docker", "Node.js"])

    # ─── Core Interaction Methods ─────────────────────────────────────
    
    async def _select_react_option(self, page, input_selector: str, option_text: str) -> bool:
        """
        Fill a Greenhouse React-Select combobox with fuzzy matching.
        
        Strategy:
        1. Click input to open dropdown
        2. Clear existing value
        3. Type search text
        4. Look for matching option using multiple selectors
        5. Click matching option or press Enter
        """
        try:
            # Clean option text (remove markdown links, trim whitespace)
            option_text = option_text.strip()
            link_match = re.search(r'\[([^\]]+)\]', option_text)
            if link_match:
                option_text = link_match.group(1)

            if isinstance(input_selector, str):
                inp = page.locator(input_selector).first
            else:
                inp = input_selector

            if not await inp.is_visible(timeout=3000):
                return False

            await inp.click(timeout=3000, force=True)
            
            # Clear input buffer
            try:
                await inp.fill("")
                await page.wait_for_timeout(200)
            except Exception:
                pass

            # Type search text (max 20 chars for better matching)
            type_text = option_text[:20]
            await page.keyboard.type(type_text, delay=50)
            await page.wait_for_timeout(500)

            # Multiple selectors for React-Select options
            selectors = [
                "div[id*='-option-']",
                "div[class*='select__option']",
                "[role='option']",
                "div[class*='option']:not([class*='menu'])",
                "li[class*='option']",
            ]
            
            for selector in selectors:
                try:
                    opts = page.locator(selector)
                    count = await opts.count()
                    if count == 0:
                        continue
                        
                    texts = await opts.all_inner_texts()
                    for i, raw_txt in enumerate(texts):
                        if not raw_txt or not raw_txt.strip():
                            continue
                            
                        txt = raw_txt.strip()
                        txt_lower = txt.lower()
                        opt_lower = option_text.lower()
                        
                        # Smart matching algorithm
                        if self._is_option_match(opt_lower, txt_lower):
                            opt_el = opts.nth(i)
                            if await opt_el.is_visible():
                                await opt_el.click(timeout=2000, force=True)
                                logger.info(f"[Greenhouse] ✓ Selected '{txt}' for {input_selector}")
                                log_dropdown(input_selector, txt)
                                
                                await page.keyboard.press("Tab")
                                await page.keyboard.press("Escape")
                                return True
                except Exception:
                    continue

            # If no option matched, press Escape to close dropdown without selecting wrong fallbacks
            await page.keyboard.press("Escape")
            logger.info(f"[Greenhouse] SKIPPED React-Select '{input_selector}' (no option matched '{option_text}')")
            return False
        except Exception as e:
            logger.warning(f"[Greenhouse] React-Select '{input_selector}' failed: {e}")
        return False

    def _is_option_match(self, search_text: str, option_text: str) -> bool:
        """Advanced fuzzy matching for dropdown options."""
        # Normalize text
        st_lower = search_text.lower().strip()
        ot_lower = option_text.lower().strip()

        # Exact match
        if st_lower == ot_lower:
            return True

        # Special country filter: India must not match British Indian Ocean Territory
        if "india" in st_lower and "british indian ocean" in ot_lower:
            return False

        # Whole word match using regex boundary
        if re.search(r'\b' + re.escape(st_lower) + r'\b', ot_lower):
            return True

        # University / School alias matching
        if "national institute of technology" in st_lower and ("jamshedpur" in st_lower or "nit" in st_lower):
            if any(alias in ot_lower for alias in ["jamshedpur", "nit jamshedpur", "national institute of technology"]):
                return True

        search_words = set(re.split(r'\W+', st_lower)) - {''}
        option_words = set(re.split(r'\W+', ot_lower)) - {''}

        if not search_words:
            return False

        if search_words.issubset(option_words):
            return True

        return False

    async def _select_first_react_option(self, page, input_selector: str) -> bool:
        """SAFETY RULE: Never select an arbitrary first or fallback option."""
        logger.info(f"[Greenhouse] SKIPPED un-matched React-Select '{input_selector}'")
        return False

    async def _find_locator(self, page, selector: str):
        """Find a locator in main frame or any child iframe."""
        # Try main page
        try:
            loc = page.locator(selector).first
            if await loc.count() > 0:
                return loc
        except Exception:
            pass
            
        # Try child frames
        for frame in page.frames:
            if frame != page.main_frame:
                try:
                    f_loc = frame.locator(selector).first
                    if await f_loc.count() > 0:
                        return f_loc
                except Exception:
                    pass
        return page.locator(selector).first

    # ─── Field Filling Methods ────────────────────────────────────────

    async def _upload_resume(self, page) -> bool:
        """Upload resume/CV file."""
        cv = self._cv_path
        if not cv or not os.path.exists(cv):
            logger.warning(f"[Greenhouse] CV not found at: {cv}")
            return False
            
        try:
            # Look for file input in main frame and iframes
            file_input = await self._find_locator(page, "input[type='file']")
            if await file_input.count() == 0:
                logger.warning("[Greenhouse] No file input found")
                return False
                
            await file_input.set_input_files(cv)
            logger.info(f"[Greenhouse] ✓ Resume uploaded: {os.path.basename(cv)}")
            
            # Wait for upload to complete
            await page.wait_for_timeout(1000)
            return True
            
        except Exception as e:
            logger.error(f"[Greenhouse] Resume upload error: {e}")
            return False

    async def _upload_cover_letter(self, page) -> bool:
        """Upload cover letter if available."""
        cover = self._cover_letter_path
        if not cover or not os.path.exists(cover):
            return False
            
        try:
            # Look for cover letter specific inputs
            cover_inputs = page.locator("input[type='file'][name*='cover'], input[type='file'][id*='cover']")
            if await cover_inputs.count() == 0:
                return False
                
            await cover_inputs.first.set_input_files(cover)
            logger.info(f"[Greenhouse] ✓ Cover letter uploaded: {os.path.basename(cover)}")
            return True
            
        except Exception as e:
            logger.warning(f"[Greenhouse] Cover letter upload error: {e}")
            return False

    async def _select_country_phone_code(self, page):
        """Fix the intl-tel-input country code selector to India (+91).
        
        The intl-tel-input widget uses a flag button + dropdown list, NOT React-Select.
        By default it matches 'India' to 'British Indian Ocean Territory' first.
        We must click the flag, search/select India (+91) explicitly.
        """
        try:
            # Strategy 1: Click the flag button and search for India
            flag_btn = page.locator(".iti__selected-flag, .iti__flag-container button, .intl-tel-input .selected-flag").first
            if await flag_btn.count() > 0 and await flag_btn.is_visible(timeout=2000):
                await flag_btn.click(force=True)
                await page.wait_for_timeout(300)
                
                # Type "India" in the search box if available
                search_input = page.locator(".iti__search-input, .iti input[type='search'], .iti input[type='text']").first
                if await search_input.count() > 0 and await search_input.is_visible(timeout=1000):
                    await search_input.fill("")
                    await search_input.type("India", delay=50)
                    await page.wait_for_timeout(300)
                
                # Find and click the India option (NOT British Indian Ocean Territory)
                country_items = page.locator(".iti__country-list .iti__country, .iti__country-list li, ul.country-list li")
                count = await country_items.count()
                for i in range(count):
                    try:
                        item_text = (await country_items.nth(i).inner_text()).strip()
                        # Match "India" but NOT "British Indian Ocean Territory"
                        if "india" in item_text.lower() and "british" not in item_text.lower() and "ocean" not in item_text.lower():
                            await country_items.nth(i).click(force=True)
                            logger.info(f"[Greenhouse] ✓ Selected country phone code: India (+91)")
                            await page.wait_for_timeout(200)
                            return True
                    except Exception:
                        continue
                
                # Close dropdown if nothing matched
                await page.keyboard.press("Escape")
            
            # Strategy 2: Direct native <select> element for country code
            country_select = page.locator("select[id='country'], select[name='country']").first
            if await country_select.count() > 0:
                try:
                    # Try selecting India by value or label
                    opts = country_select.locator("option")
                    opt_count = await opts.count()
                    for i in range(opt_count):
                        txt = (await opts.nth(i).inner_text()).strip()
                        if "india" in txt.lower() and "+91" in txt and "british" not in txt.lower():
                            val = await opts.nth(i).get_attribute("value")
                            if val:
                                await country_select.select_option(value=val)
                            else:
                                await country_select.select_option(label=txt)
                            logger.info(f"[Greenhouse] ✓ Selected country code via native select: {txt}")
                            return True
                except Exception as e:
                    logger.debug(f"[Greenhouse] Native country select fallback: {e}")
                    
        except Exception as e:
            logger.debug(f"[Greenhouse] Country phone code selection: {e}")
        return False

    async def _fill_phone_number(self, page):
        """Fill phone number with country code handling (handles main page and child iframes)."""
        try:
            # First, fix the country code dropdown (intl-tel-input)
            await self._select_country_phone_code(page)
            
            frames_to_scan = [page] + [f for f in page.frames if f != page.main_frame]
            phone_selectors = [
                "#phone",
                "input[type='tel']",
                "input[name*='phone' i]",
                "input[id*='phone' i]",
                "input[aria-label*='phone' i]",
                "input[placeholder*='phone' i]",
            ]
            
            phone_10 = self._phone  # Already stripped to 10 digits
            
            for target in frames_to_scan:
                for selector in phone_selectors:
                    try:
                        phone_input = target.locator(selector).first
                        if await phone_input.count() == 0:
                            continue
                        if not await phone_input.is_visible():
                            continue
                            
                        current = await phone_input.input_value() or ""
                        if current.strip() and len(current) >= 10:
                            return  # Already filled
                            
                        await phone_input.click(force=True)
                        await phone_input.fill("")
                        await phone_input.type(phone_10, delay=50)
                        logger.info(f"[Greenhouse] ✓ Filled phone (10-digit): {phone_10}")
                        log_field_fill("Phone", phone_10)
                        return
                        
                    except Exception:
                        continue
                    
        except Exception as e:
            logger.warning(f"[Greenhouse] Phone fill error: {e}")

    async def _fill_location_autocomplete(self, page):
        """Fill location field with autocomplete handling."""
        try:
            location_selectors = [
                "#job_application_location",
                "#candidate-location",
                "input[id*='location' i]",
                "input[name*='location' i]",
                "input[aria-label*='location' i]",
                "input[placeholder*='location' i]",
            ]
            
            for selector in location_selectors:
                try:
                    loc_input = page.locator(selector).first
                    if await loc_input.count() == 0:
                        continue
                    if not await loc_input.is_visible():
                        continue
                        
                    current = await loc_input.input_value() or ""
                    if current.strip() and "pune" in current.lower():
                        continue
                        
                    await loc_input.click(force=True)
                    await loc_input.fill("")
                    await loc_input.type(self._location, delay=50)
                    await page.wait_for_timeout(500)
                    
                    # Try autocomplete suggestion
                    try:
                        await page.keyboard.press("ArrowDown")
                        await page.keyboard.press("Enter")
                        
                        # Check for Google Places autocomplete
                        suggestions = page.locator(".pac-item, [class*='location-picker']")
                        if await suggestions.count() > 0:
                            await suggestions.first.click(force=True)
                    except Exception:
                        pass
                        
                    logger.info(f"[Greenhouse] ✓ Filled location: {self._location}")
                    return
                    
                except Exception:
                    continue
                    
        except Exception as e:
            logger.warning(f"[Greenhouse] Location fill error: {e}")

    async def _upload_resume(self, page) -> bool:
        """Upload resume/CV file (handles main page and child iframes)."""
        cv = self._cv_path
        if not cv or not os.path.exists(cv):
            logger.warning(f"[Greenhouse] CV not found at: {cv}")
            return False
            
        try:
            frames_to_scan = [page] + [f for f in page.frames if f != page.main_frame]
            selectors = [
                "input[type='file'][name*='resume' i]",
                "input[type='file'][id*='resume' i]",
                "input[type='file']",
            ]
            for target in frames_to_scan:
                for selector in selectors:
                    try:
                        file_input = target.locator(selector).first
                        if await file_input.count() > 0:
                            await file_input.set_input_files(cv)
                            logger.info(f"[Greenhouse] ✓ Resume uploaded: {os.path.basename(cv)}")
                            await page.wait_for_timeout(500)
                            return True
                    except Exception:
                        continue

            logger.warning("[Greenhouse] No file input found for resume upload")
            return False
        except Exception as e:
            logger.error(f"[Greenhouse] Resume upload error: {e}")
            return False

    async def _upload_cover_letter(self, page) -> bool:
        """Upload cover letter if available (handles main page and child iframes)."""
        cover = self._cover_letter_path
        if not cover or not os.path.exists(cover):
            return False
            
        try:
            frames_to_scan = [page] + [f for f in page.frames if f != page.main_frame]
            selectors = [
                "input[type='file'][name*='cover' i]",
                "input[type='file'][id*='cover' i]",
            ]
            for target in frames_to_scan:
                for selector in selectors:
                    try:
                        cover_inputs = target.locator(selector).first
                        if await cover_inputs.count() > 0:
                            await cover_inputs.set_input_files(cover)
                            logger.info(f"[Greenhouse] ✓ Cover letter uploaded: {os.path.basename(cover)}")
                            return True
                    except Exception:
                        continue
            return False
        except Exception as e:
            logger.warning(f"[Greenhouse] Cover letter upload error: {e}")
            return False

    async def _fill_standard_fields(self, page):
        """Fill all standard application fields."""
        await self._fill_location_autocomplete(page)
        await self._fill_phone_number(page)
        
        # Define field mappings with multiple selectors
        field_mappings = {
            "first_name": {
                "value": self._first_name,
                "selectors": ["#first_name", "input[name='first_name']", "input[id*='first_name' i]",
                             "input[aria-label*='first name' i]", "input[placeholder*='first name' i]"]
            },
            "last_name": {
                "value": self._last_name,
                "selectors": ["#last_name", "input[name='last_name']", "input[id*='last_name' i]",
                             "input[aria-label*='last name' i]", "input[placeholder*='last name' i]"]
            },
            "email": {
                "value": self._email,
                "selectors": ["#email", "input[type='email']", "input[name*='email' i]",
                             "input[id*='email' i]", "input[aria-label*='email' i]"]
            },
            "location": {
                "value": self._location,
                "selectors": ["#job_application_location", "input[name*='location' i]",
                             "input[id*='location' i]", "input[aria-label*='location' i]"]
            },
            "linkedin": {
                "value": self._linkedin_url,
                "selectors": ["input[name*='linkedin' i]", "input[id*='linkedin' i]",
                             "input[aria-label*='linkedin' i]", "input[placeholder*='linkedin' i]"]
            },
            "github": {
                "value": self._github_url,
                "selectors": ["input[name*='github' i]", "input[id*='github' i]",
                             "input[aria-label*='github' i]", "input[placeholder*='github' i]"]
            },
            "portfolio": {
                "value": self._portfolio_url,
                "selectors": ["input[name*='portfolio' i]", "input[id*='portfolio' i]",
                             "input[aria-label*='portfolio' i]", "input[placeholder*='portfolio' i]"]
            },
        }
        
        frames_to_scan = [page] + [f for f in page.frames if f != page.main_frame]
        
        for field_name, field_info in field_mappings.items():
            value = field_info["value"]
            if not value:
                continue
                
            filled = False
            for target in frames_to_scan:
                if filled:
                    break
                for selector in field_info["selectors"]:
                    try:
                        el = target.locator(selector).first
                        if await el.count() == 0:
                            continue
                            
                        current_val = await el.input_value() or ""
                        if current_val.strip():
                            filled = True
                            break  # Already filled
                            
                        await el.click(timeout=3000, force=True)
                        await el.fill("")
                        await el.type(value, delay=50)
                        logger.info(f"[Greenhouse] ✓ Filled {field_name}: {value}")
                        log_field_fill(field_name.replace("_", " ").title(), value)
                        filled = True
                        break
                        
                    except Exception as e:
                        logger.debug(f"[Greenhouse] Could not fill {selector}: {e}")
                        continue

        # Fill preferred name if present
        await self._fill_preferred_name(page)

    async def _fill_preferred_name(self, page):
        """Fill preferred name field if present."""
        try:
            pref_selectors = [
                "input[id*='preferred_name' i]",
                "input[name*='preferred_name' i]",
                "input[aria-label*='preferred name' i]",
                "input[placeholder*='preferred name' i]",
            ]
            
            for selector in pref_selectors:
                try:
                    pref_input = page.locator(selector).first
                    if await pref_input.count() == 0:
                        continue
                    if not await pref_input.is_visible():
                        continue
                        
                    current = await pref_input.input_value() or ""
                    if current.strip():
                        continue
                        
                    await pref_input.click(force=True)
                    await pref_input.fill("")
                    await pref_input.type(self._first_name, delay=50)
                    logger.info(f"[Greenhouse] ✓ Filled preferred name: {self._first_name}")
                    return
                    
                except Exception:
                    continue
                    
        except Exception as e:
            logger.debug(f"[Greenhouse] Preferred name fill warning: {e}")

    async def _fill_education_section(self, page):
        """Fill education section: school dropdown, degree, discipline, start/end dates (handles main page and child iframes)."""
        try:
            frames_to_scan = [page] + [f for f in page.frames if f != page.main_frame]
            
            for target in frames_to_scan:
                # ─── School (React-Select) ─────────────────────────────
                school_input = target.locator("input[id^='school'], input[id*='school'], input[aria-label*='school' i]").first
                if await school_input.count() > 0:
                    current = await school_input.input_value() or ""
                    if not current.strip():
                        # Try multiple university name aliases + broad fallbacks
                        aliases = self._university_aliases + [
                            "National Institute of Technology",
                            "NIT",
                            "Other",
                        ]
                        school_selected = False
                        for alias in aliases:
                            if await self._select_react_option(target, school_input, alias):
                                logger.info(f"[Greenhouse] ✓ School selected with alias: {alias}")
                                school_selected = True
                                break
                                
                        if not school_selected:
                            # Select "Other" as guaranteed fallback option
                            await self._select_react_option(target, school_input, "Other")
                            
                        # Fill secondary "Other School" text input if Greenhouse revealed it
                        try:
                            other_school = target.locator("input[id*='other_school' i], input[name*='other_school' i]").first
                            if await other_school.count() > 0 and await other_school.is_visible(timeout=1000):
                                await other_school.fill(self._university)
                                logger.info(f"[Greenhouse] ✓ Filled Other School text: {self._university}")
                        except Exception:
                            pass

                # ─── Degree (React-Select) ─────────────────────────────
                degree_input = target.locator("input[id^='degree'], input[id*='degree']").first
                if await degree_input.count() > 0:
                    current = await degree_input.input_value() or ""
                    if not current.strip():
                        await self._select_react_option(target, degree_input, "Bachelor's Degree")

                # ─── Discipline (React-Select) ─────────────────────────
                disc_input = target.locator("input[id^='discipline'], input[id*='discipline']").first
                if await disc_input.count() > 0:
                    current = await disc_input.input_value() or ""
                    if not current.strip():
                        # Try ECE first, then fall back to broader terms
                        for disc in ["Electronics", "Electronics and Communications", "Electrical Engineering", "Engineering"]:
                            if await self._select_react_option(target, disc_input, disc):
                                break

            # ─── Start Date (native selects) ───────────────────────
            start_month_selectors = [
                "select[id*='start_date_month']", "select[id*='start-date-month']",
                "select[name*='start_date_month']", "select[id*='education_start_month']",
            ]
            for sel in start_month_selectors:
                try:
                    el = page.locator(sel).first
                    if await el.count() > 0:
                        await el.select_option(value=self._edu_start_month)
                        logger.info(f"[Greenhouse] ✓ Education start month: {self._edu_start_month}")
                        break
                except Exception:
                    continue

            start_year_selectors = [
                "select[id*='start_date_year']", "select[id*='start-date-year']",
                "select[name*='start_date_year']", "select[id*='education_start_year']",
            ]
            for sel in start_year_selectors:
                try:
                    el = page.locator(sel).first
                    if await el.count() > 0:
                        await el.select_option(value=self._edu_start_year)
                        logger.info(f"[Greenhouse] ✓ Education start year: {self._edu_start_year}")
                        break
                except Exception:
                    continue

            # ─── End Date (native selects) ─────────────────────────
            end_month_selectors = [
                "select[id*='end_date_month']", "select[id*='end-date-month']",
                "select[name*='end_date_month']", "select[id*='education_end_month']",
            ]
            for sel in end_month_selectors:
                try:
                    el = page.locator(sel).first
                    if await el.count() > 0:
                        await el.select_option(value=self._edu_end_month)
                        logger.info(f"[Greenhouse] ✓ Education end month: {self._edu_end_month}")
                        break
                except Exception:
                    continue

            end_year_selectors = [
                "select[id*='end_date_year']", "select[id*='end-date-year']",
                "select[name*='end_date_year']", "select[id*='education_end_year']",
            ]
            for sel in end_year_selectors:
                try:
                    el = page.locator(sel).first
                    if await el.count() > 0:
                        await el.select_option(value=self._edu_end_year)
                        logger.info(f"[Greenhouse] ✓ Education end year: {self._edu_end_year}")
                        break
                except Exception:
                    continue

        except Exception as e:
            logger.warning(f"[Greenhouse] Education section fill error: {e}")

    # ─── Custom Question Handling ─────────────────────────────────────

    async def _fill_custom_questions(self, page):
        """Auto-detect and fill all custom question fields across main page and iframes."""
        # Track already-processed element IDs to avoid duplicate processing (Fix 5)
        processed_ids = set()
        
        frames_to_scan = [page] + [f for f in page.frames if f != page.main_frame]

        for target in frames_to_scan:
            try:
                # Text inputs
                text_inputs = target.locator("input[id^='question_']:not([role='combobox']), textarea[id^='question_'], input[name^='question_']:not([role='combobox']), textarea[name^='question_']")
                text_count = await text_inputs.count()
                if text_count > 0:
                    logger.info(f"[Greenhouse] Found {text_count} text question(s)")
                    for i in range(text_count):
                        inp = text_inputs.nth(i)
                        inp_id = await inp.get_attribute("id") or ""
                        if inp_id and inp_id in processed_ids:
                            continue
                        if inp_id:
                            processed_ids.add(inp_id)
                        await self._fill_custom_text_input(target, inp)
                
                # React-Select dropdowns (with dedup)
                await self._fill_react_selects(target, processed_ids)
                
                # Native selects
                await self._fill_native_selects(target, processed_ids)
                
                # Radio buttons and checkboxes
                await self._fill_radio_buttons(target)
            except Exception as e:
                logger.debug(f"[Greenhouse] Frame scan error: {e}")

    async def _fill_custom_text_input(self, page, inp):
        """Fill a single custom text input."""
        try:
            inp_id = await inp.get_attribute("id") or ""
            inp_type = await inp.get_attribute("type") or "text"
            
            if inp_type in ("file", "hidden", "checkbox", "radio", "button", "submit"):
                return
                
            # Get label text
            label_text = await self._get_input_label(page, inp, inp_id)
            
            # Get answer
            value = self._pick_answer_for_question(label_text)
            
            # Special handling for URLs
            if not value and any(kw in label_text.lower() for kw in ["linkedin", "profile", "link", "url"]):
                value = self._linkedin_url

            # Fallback for required text inputs / textareas (*)
            if not value:
                is_required = "*" in label_text or "required" in (await inp.get_attribute("class") or "").lower() or (await inp.get_attribute("required")) is not None
                if is_required:
                    lbl_clean = label_text.lower()
                    if any(kw in lbl_clean for kw in ["describe", "issue", "project", "challenge", "resolution", "experience", "how"]):
                        value = "I encountered a high-concurrency real-time packet processing latency issue and resolved it by optimizing async socket IO loops and buffer queues."
                    elif any(kw in lbl_clean for kw in ["years", "how many"]):
                        value = "3"
                    elif any(kw in lbl_clean for kw in ["city", "reside", "located", "where"]):
                        value = self._location
                    else:
                        value = "N/A"

            if not value:
                return
                
            # Fill the input
            await inp.click(timeout=2000)
            await inp.fill("")
            await inp.type(value, delay=30)
            logger.info(f"[Greenhouse] ✓ Filled '{inp_id}': {value[:50]}")
            log_field_fill(label_text or inp_id, value)
            
        except Exception as e:
            logger.debug(f"[Greenhouse] Could not fill custom input: {e}")

    async def _get_input_label(self, page, inp, inp_id: str) -> str:
        """Extract label text for an input field."""
        label_text = ""
        
        try:
            # Try label[for] attribute
            if inp_id:
                label_el = page.locator(f"label[for='{inp_id}']").first
                if await label_el.count() > 0:
                    label_text = (await label_el.inner_text()).strip()
                    
            # Try parent label
            if not label_text:
                parent_label = inp.locator("xpath=ancestor::label").first
                if await parent_label.count() > 0:
                    label_text = (await parent_label.inner_text()).strip()
                    
            # Try aria-label
            if not label_text:
                label_text = await inp.get_attribute("aria-label") or ""
                
            # Try placeholder
            if not label_text:
                label_text = await inp.get_attribute("placeholder") or ""
                
            # Try nearby label
            if not label_text:
                nearby_label = inp.locator("xpath=preceding::label[1]").first
                if await nearby_label.count() > 0:
                    label_text = (await nearby_label.inner_text()).strip()
                    
        except Exception:
            pass
            
        return label_text or inp_id

    async def _fill_react_selects(self, page, processed_ids=None):
        """Fill all React-Select combobox dropdowns."""
        if processed_ids is None:
            processed_ids = set()
            
        selectors = [
            "input[role='combobox']:not([id*='iti']):not([class*='iti'])",
        ]
        
        for selector in selectors:
            try:
                selects = page.locator(selector)
                count = await selects.count()
                
                for i in range(count):
                    sel = selects.nth(i)
                    sel_id = await sel.get_attribute("id") or ""
                    # Skip already-processed elements (dedup)
                    if sel_id and sel_id in processed_ids:
                        continue
                    if sel_id:
                        processed_ids.add(sel_id)
                    await self._fill_single_react_select(page, sel)
                    
            except Exception as e:
                logger.debug(f"[Greenhouse] React-Select fill error: {e}")

    async def _fill_single_react_select(self, page, sel):
        """Fill a single React-Select dropdown."""
        try:
            sel_id = await sel.get_attribute("id") or ""
            current_val = await sel.input_value() or ""
            
            # Skip page header filter dropdowns completely
            if any(filter_kw in sel_id.lower() for filter_kw in ["filter", "department", "office", "search"]):
                return

            if current_val.strip():
                return  # Already filled
                
            # Get label
            label_text = await self._get_input_label(page, sel, sel_id)
            combined = f"{sel_id} {label_text}".lower()
            
            # Dismiss any open dropdowns
            try:
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(200)
            except Exception:
                pass
                
            target_sel = f"input[id='{sel_id}']" if sel_id else sel
            
            # Explicit Country Handler: Always select India (+91)
            if "country" in combined:
                for country_choice in ["India (+91)", "India", "+91"]:
                    if await self._select_react_option(page, target_sel, country_choice):
                        logger.info(f"[Greenhouse] ✓ Selected country: {country_choice}")
                        log_dropdown("Country*", country_choice, method="country_fix")
                        return

            # Explicit Candidate Location Handler (e.g. Axon / Scale AI)
            if "candidate-location" in combined or "location (city)" in combined:
                for loc_choice in ["Remote", "India", "Other", "Pune"]:
                    if await self._select_react_option(page, target_sel, loc_choice):
                        logger.info(f"[Greenhouse] ✓ Selected candidate location: {loc_choice}")
                        log_dropdown("Location (City)*", loc_choice, method="location_fix")
                        return

            # Explicit Privacy / Consent Handler (e.g. Ubiquiti)
            if any(kw in combined for kw in ["consent", "privacy", "acknowledge", "agree", "policy"]):
                for consent_choice in ["I consent", "Consent", "Yes", "I agree", "I acknowledge"]:
                    if await self._select_react_option(page, target_sel, consent_choice):
                        logger.info(f"[Greenhouse] ✓ Selected consent: {consent_choice}")
                        log_dropdown(label_text or sel_id, consent_choice, method="consent_fix")
                        return

            # Try explicit handlers first
            answer = await self._get_dropdown_answer(combined, label_text)
            
            if answer:
                if await self._select_react_option(page, target_sel, answer):
                    logger.info(f"[Greenhouse] ✓ Dropdown '{label_text[:40]}' -> '{answer}'")
                    log_dropdown(label_text or sel_id, answer, method="explicit")
                    return
                    
            # Try fuzzy match from QA engine
            if QA_ENGINE_AVAILABLE and label_text.strip():
                try:
                    qa = get_qa_engine()
                    if qa:
                        qa_ans, score, matched_q = qa.find_answer(label_text, min_similarity=0.60)
                        if qa_ans and qa_ans.lower() not in ("indian", "need user input", "need job-specific answer"):
                            if await self._select_react_option(page, target_sel, qa_ans):
                                logger.info(f"[Greenhouse] ✓ QA match '{label_text[:40]}' -> '{qa_ans}'")
                                log_dropdown(label_text or sel_id, qa_ans, method="qa_engine")
                                return
                except Exception:
                    pass
                    
            # Fallback for required fields (*) to prevent form submission blocking
            if "*" in label_text or "required" in combined or "asterisk" in combined:
                for safe_fallback in ["No", "Yes", "Remote", "Decline to self-identify", "Other"]:
                    if await self._select_react_option(page, target_sel, safe_fallback):
                        logger.info(f"[Greenhouse] ✓ Fallback for required dropdown '{label_text[:40]}' -> '{safe_fallback}'")
                        log_dropdown(label_text or sel_id, safe_fallback, method="required_fallback")
                        return

                # Keyboard selection fallback for non-standard options
                try:
                    await sel.click(timeout=1000)
                    await page.wait_for_timeout(200)
                    root_page = getattr(page, "page", page) if hasattr(page, "page") else page
                    if not hasattr(root_page, "keyboard") and hasattr(sel, "page"):
                        root_page = sel.page
                    await root_page.keyboard.press("ArrowDown")
                    await root_page.wait_for_timeout(200)
                    await root_page.keyboard.press("Enter")
                    logger.info(f"[Greenhouse] ✓ Selected option via keyboard for required dropdown '{label_text[:40]}'")
                    log_dropdown(label_text or sel_id, "Keyboard Selected", method="required_keyboard")
                    return
                except Exception:
                    pass

            logger.info(f"[Greenhouse] SKIPPED unconfigured React-Select '{label_text or sel_id}'")
            
            # Record un-answered custom question ID to ranjan.txt
            if QA_ENGINE_AVAILABLE:
                try:
                    qa = get_qa_engine()
                    if qa:
                        val = await sel.input_value() or ""
                        q_record = f"[{sel_id}] {label_text}".strip() if sel_id else label_text.strip()
                        if q_record and val.strip():
                            qa.record_question(q_record, val.strip())
                except Exception:
                    pass
                    
        except Exception as e:
            logger.debug(f"[Greenhouse] Single React-Select fill error: {e}")

    async def _get_dropdown_answer(self, combined: str, label_text: str) -> Optional[str]:
        """Get intelligent answer for dropdown based on context."""
        combined_lower = combined.lower()
        
        # GPA / Scores
        if any(kw in combined_lower for kw in ["gpa", "sat score", "act score", "gre score"]):
            return "Not applicable/Do not recall"

        # Citizenship
        if "citizenship" in combined_lower:
            return "Non-U.S. Citizen"

        # Location preference (e.g. "What is your top location preference?")
        if any(kw in combined_lower for kw in ["location preference", "preferred location", "top location"]):
            return "Gurgaon"

        # Location-related
        if any(kw in combined_lower for kw in ["location", "city", "where are you"]):
            return self._location
            
        # Country (general, not authorization-related)
        if "country" in combined_lower and not any(kw in combined_lower for kw in ["authoriz", "sponsor", "visa", "phone"]):
            return "India"

        # Resident of countries
        if any(kw in combined_lower for kw in ["resident of", "reside in", "these countries"]):
            return "India"
            
        # School/University
        if any(kw in combined_lower for kw in ["school", "university", "college", "institution"]):
            return self._university

        # Degree
        if "degree" in combined_lower:
            return "Bachelor's Degree"

        # Discipline / Major
        if any(kw in combined_lower for kw in ["discipline", "major", "field of study"]):
            return "Electronics"
            
        # Years of experience
        if any(kw in combined_lower for kw in ["years", "experience"]) and "clearance" not in combined_lower:
            return self._years_experience
            
        # Sponsorship / Require Authorization
        if any(kw in combined_lower for kw in ["require authorization", "require sponsorship", "require visa", "sponsor", "visa"]):
            return "No"
            
        # Authorized / Legally Eligible to work
        if any(kw in combined_lower for kw in ["authorized to work", "legally authorized", "eligible to work", "authoriz", "eligible", "legally"]):
            return "Yes"
            
        # Clearance Eligibility — NEVER claim clearance
        if any(kw in combined_lower for kw in ["clearance eligibility", "security clearance"]):
            if any(kw in combined_lower for kw in ["held", "past", "level", "what clearance"]):
                return "N/A"
            return "No"
        if "clearance" in combined_lower:
            return "No"
            
        # Export Controls
        if any(kw in combined_lower for kw in ["export control", "export controls", "itar", "ear"]):
            return "None of the above"
            
        # History with company / Previously employed / Acquired
        if any(kw in combined_lower for kw in [
            "history with", "employed by", "previously applied",
            "worked for", "company that", "acquired",
            "previously worked", "have you ever been employed",
        ]):
            return "No"
            
        # Conflict of Interest
        if "conflict of interest" in combined_lower:
            return "No"

        # In-office / Hybrid / On-site / Able to meet requirement
        if any(kw in combined_lower for kw in ["in-office", "in office", "on-site", "onsite", "hybrid", "meet this requirement", "presence"]):
            return "Yes"
            
        # Motivation / Why do you want to work here
        if any(kw in combined_lower for kw in ["why do you want", "why work", "why are you interested", "motivation", "why join"]):
            return "I am passionate about building high-performance, distributed backend systems and want to leverage my C++, Rust, and Kafka experience to solve critical engineering challenges on your team."

        # How did you hear about us / Source
        if any(kw in combined_lower for kw in ["how did you hear", "hear about", "how did you find", "how did you learn"]):
            return "LinkedIn"
            
        # Returning to school (intern-specific)
        if any(kw in combined_lower for kw in ["returning to school", "return to school", "continue academic"]):
            return "No"
            
        # Start full time / Minimum experience / Technical work
        if any(kw in combined_lower for kw in [
            "start full time", "able to start", "minimum of",
            "do you have a minimum",
        ]):
            return "Yes"
            
        # Available to begin work / When can you start
        if any(kw in combined_lower for kw in ["available to begin", "when are you available", "when can you start", "begin work"]):
            return "Immediately"
            
        # Race/Ethnicity
        if any(kw in combined_lower for kw in ["race", "ethnicity"]):
            return "Asian"
            
        # Hispanic / Latino / Ethnicity
        if any(kw in combined_lower for kw in ["hispanic", "latino", "latina", "hispanic_ethnicity"]):
            return "No"
            
        # Veteran status
        if "veteran" in combined_lower:
            return "I am not a protected veteran"
            
        # Disability
        if "disability" in combined_lower:
            return "No, I do not have a disability"
            
        # Consent / Privacy / Acknowledge
        if any(kw in combined_lower for kw in ["consent", "acknowledge", "agree", "privacy", "terms"]):
            return "I acknowledge"

        # AI Tools
        if any(kw in combined_lower for kw in ["ai tools", "artificial intelligence"]):
            return "Yes"
            
        # Gender (optional)
        if "gender" in combined_lower:
            return "Male"

        # Birth country / Country of birth
        if any(kw in combined_lower for kw in ["country of birth", "country of your birth", "born in"]):
            return "India"

        # Currently employed
        if any(kw in combined_lower for kw in ["currently employed", "employment status"]):
            return "Yes"
            
        # Background check
        if any(kw in combined_lower for kw in ["background check", "background screening"]):
            return "Yes"
            
        # Relocation
        if any(kw in combined_lower for kw in ["relocat", "willing to move"]):
            return "Yes"
            
        return None

    async def _fill_native_selects(self, page, processed_ids=None):
        """Fill standard HTML <select> elements."""
        if processed_ids is None:
            processed_ids = set()
        try:
            selects = page.locator("select")
            count = await selects.count()
            
            for i in range(count):
                sel = selects.nth(i)
                sel_id = await sel.get_attribute("id") or ""
                # Skip already-processed or education date selects (handled by _fill_education_section)
                if sel_id and sel_id in processed_ids:
                    continue
                if sel_id:
                    processed_ids.add(sel_id)
                await self._fill_single_native_select(page, sel)
                
        except Exception as e:
            logger.warning(f"[Greenhouse] Native select fill error: {e}")

    async def _fill_single_native_select(self, page, sel):
        """Fill a single native HTML select."""
        try:
            sel_id = await sel.get_attribute("id") or ""
            
            opts = sel.locator("option")
            opt_count = await opts.count()
            if opt_count <= 1:
                return
                
            # Get label
            label_text = await self._get_input_label(page, sel, sel_id)
            
            # Try to match with intelligent answer
            answer = await self._get_dropdown_answer(label_text, label_text)
            
            if answer:
                for j in range(opt_count):
                    opt_text = (await opts.nth(j).inner_text()).strip()
                    if answer.lower() in opt_text.lower():
                        opt_val = await opts.nth(j).get_attribute("value")
                        if opt_val:
                            await sel.select_option(value=opt_val)
                        else:
                            await sel.select_option(label=opt_text)
                        logger.info(f"[Greenhouse] ✓ Selected '{opt_text}' in {sel_id}")
                        return
                        
            # SAFETY: Never select an arbitrary option (index 1 or index 0)
            logger.info(f"[Greenhouse] SKIPPED unconfigured native select '{label_text or sel_id}' (no fallback selection)")
                
        except Exception as e:
            logger.debug(f"[Greenhouse] Single native select error: {e}")

    async def _fill_radio_buttons(self, page):
        """Fill radio buttons and checkboxes using strict Q&A matching without arbitrary fallbacks."""
        try:
            radios = page.locator("input[type='radio']")
            radio_count = await radios.count()
            
            if radio_count > 0:
                # Group by name
                radio_groups = {}
                for i in range(radio_count):
                    name = await radios.nth(i).get_attribute("name") or f"radio_{i}"
                    if name not in radio_groups:
                        radio_groups[name] = []
                    radio_groups[name].append(i)
                    
                for name, indices in radio_groups.items():
                    # Check if already selected
                    selected = False
                    for idx in indices:
                        if await radios.nth(idx).is_checked():
                            selected = True
                            break
                    if selected:
                        continue

                    # Determine group context from legend, fieldset, or preceding label
                    first_radio = radios.nth(indices[0])
                    group_label = ""
                    try:
                        fieldset = page.locator(f"fieldset:has(input[name='{name}'])").first
                        if await fieldset.count() > 0:
                            legend = fieldset.locator("legend").first
                            if await legend.count() > 0:
                                group_label = (await legend.inner_text()).strip()
                    except Exception:
                        pass

                    if not group_label:
                        r_id = await first_radio.get_attribute("id") or ""
                        group_label = await self._get_input_label(page, first_radio, r_id)

                    group_clean = group_label.lower()

                    # Find best answer for group
                    target_answer = ""

                    # Security Clearance Rule: NEVER claim U.S. security clearance
                    if "clearance" in group_clean:
                        target_answer = "no"

                    # U.S. Citizenship Rule: NEVER claim U.S. citizenship
                    elif "citizen" in group_clean or "citizenship" in group_clean:
                        target_answer = "non-u.s. citizen"

                    # U.S. Work Authorization / Sponsorship
                    elif "sponsorship" in group_clean or "visa" in group_clean:
                        target_answer = "no"
                    elif "authorized" in group_clean or "authorization" in group_clean:
                        target_answer = "yes"

                    # Export Controls
                    elif any(kw in group_clean for kw in ["export control", "itar", "ear"]):
                        target_answer = "none of the above"

                    # History with company / Previously employed
                    elif any(kw in group_clean for kw in [
                        "history with", "employed by", "previously applied",
                        "have you ever been employed", "worked for",
                        "company that", "acquired",
                    ]):
                        target_answer = "no"

                    # Conflict of interest
                    elif "conflict of interest" in group_clean:
                        target_answer = "no"

                    # Returning to school
                    elif any(kw in group_clean for kw in ["returning to school", "return to school", "continue academic"]):
                        target_answer = "no"

                    # Start full time / Minimum experience
                    elif any(kw in group_clean for kw in ["start full time", "minimum of", "able to start"]):
                        target_answer = "yes"

                    # How did you hear
                    elif any(kw in group_clean for kw in ["how did you hear", "hear about"]):
                        target_answer = "linkedin"

                    # Resident of countries
                    elif any(kw in group_clean for kw in ["resident of", "these countries"]):
                        target_answer = "india"

                    # Location preference
                    elif any(kw in group_clean for kw in ["location preference", "top location"]):
                        target_answer = "gurgaon"

                    # Demographics / Identity
                    elif "gender" in group_clean:
                        target_answer = "male"
                    elif "hispanic" in group_clean or "latino" in group_clean:
                        target_answer = "no"
                    elif "race" in group_clean or "ethnicity" in group_clean:
                        target_answer = "asian"
                    elif "veteran" in group_clean:
                        target_answer = "not a protected veteran"
                    elif "disability" in group_clean:
                        target_answer = "no"

                    # Consent / Acknowledge / Agree
                    elif any(kw in group_clean for kw in ["consent", "acknowledge", "agree", "privacy"]):
                        target_answer = "yes"

                    # Background check
                    elif any(kw in group_clean for kw in ["background check", "background screening"]):
                        target_answer = "yes"

                    # Relocation
                    elif any(kw in group_clean for kw in ["relocat", "willing to move"]):
                        target_answer = "yes"

                    else:
                        # Try QA engine match from ranjan.txt
                        if QA_ENGINE_AVAILABLE and group_label:
                            try:
                                qa = get_qa_engine()
                                if qa:
                                    ans, score, _ = qa.find_answer(group_label, min_similarity=0.60)
                                    if ans and score >= 0.60:
                                        target_answer = ans.lower()
                            except Exception:
                                pass

                    if not target_answer:
                        logger.info(f"[Greenhouse] SKIPPED un-matched radio group '{group_label[:40]}'")
                        continue

                    # Find matching option among group choices
                    for idx in indices:
                        opt_label = ""
                        try:
                            r_id = await radios.nth(idx).get_attribute("id") or ""
                            r_val = await radios.nth(idx).get_attribute("value") or ""
                            if r_id:
                                label_el = page.locator(f"label[for='{r_id}']").first
                                if await label_el.count() > 0:
                                    opt_label = (await label_el.inner_text()).strip()
                            if not opt_label:
                                opt_label = r_val
                        except Exception:
                            pass

                        opt_clean = opt_label.lower()
                        if target_answer in opt_clean or opt_clean in target_answer or self._is_option_match(target_answer, opt_clean):
                            try:
                                await radios.nth(idx).check(force=True)
                                logger.info(f"[Greenhouse] ✓ Selected radio '{opt_label}' for '{group_label[:30]}'")
                                log_dropdown(group_label or name, opt_label)
                                break
                            except Exception:
                                continue
                            
            # Handle checkboxes (consent, agreements)
            checkboxes = page.locator("input[type='checkbox']")
            checkbox_count = await checkboxes.count()
            
            for i in range(checkbox_count):
                try:
                    cb = checkboxes.nth(i)
                    if await cb.is_checked():
                        continue
                        
                    # Get label text
                    cb_id = await cb.get_attribute("id") or ""
                    cb_name = await cb.get_attribute("name") or ""
                    label_text = ""
                    if cb_id:
                        label_el = page.locator(f"label[for='{cb_id}']").first
                        if await label_el.count() > 0:
                            label_text = (await label_el.inner_text()).lower()
                            
                    combined_cb = f"{cb_id} {cb_name} {label_text}".lower()
                    # Check consent/agreement/GDPR boxes
                    if any(kw in combined_cb for kw in ["consent", "agree", "acknowledge", "terms", "privacy", "policy", "gdpr"]):
                        await cb.check(force=True)
                        logger.info(f"[Greenhouse] ✓ Checked consent/GDPR: {combined_cb[:40]}")
                        
                except Exception:
                    continue
                    
        except Exception as e:
            logger.warning(f"[Greenhouse] Radio/checkbox fill error: {e}")

    # ─── Answer Selection ────────────────────────────────────────────

    def _pick_answer_for_question(self, label: str) -> str:
        """Intelligent answer selection based on question context."""
        if not label:
            return ""
            
        clean_label = label.lower().strip()
        
        # Try QA engine first
        if QA_ENGINE_AVAILABLE:
            try:
                qa = get_qa_engine()
                if qa:
                    ans, score, matched_q = qa.find_answer(clean_label, min_similarity=0.60)
                    if ans and score >= 0.60 and not any(placeholder in ans.upper() for placeholder in ["NEED USER INPUT", "NEED JOB-SPECIFIC ANSWER", "TODO"]):
                        logger.info(f"[Greenhouse] ✓ QA match: '{label[:40]}' -> '{ans[:50]}' ({score*100:.0f}%)")
                        return ans
            except Exception as e:
                logger.debug(f"[Greenhouse] QA engine error: {e}")
                
        # Pattern-based answers
        if "linkedin" in clean_label:
            return self._linkedin_url
        elif any(kw in clean_label for kw in ["github", "git hub"]):
            return self._github_url
        elif any(kw in clean_label for kw in ["portfolio", "website", "personal site"]):
            return self._portfolio_url or self._github_url
        elif any(kw in clean_label for kw in ["location", "city", "where are you"]):
            return self._location
        elif "name" in clean_label:
            return self._full_name
        elif "email" in clean_label:
            return self._email
        elif "phone" in clean_label:
            return self._phone
        elif any(kw in clean_label for kw in ["years", "experience"]):
            return self._years_experience
        elif any(kw in clean_label for kw in ["notice", "availability", "join"]):
            return self._notice_period
        elif any(kw in clean_label for kw in ["salary", "ctc", "compensation", "expected", "pretensão", "pretensao", "clt", "pj", "remuneracao", "remuneração"]):
            return f"{self._expected_salary} INR (Open to discussion)"
        elif any(kw in clean_label for kw in ["inglês", "ingles"]):
            return "Fluent"
        elif any(kw in clean_label for kw in ["espanhol", "spanish"]):
            return "Basic"
        elif any(kw in clean_label for kw in ["current company", "employer", "organization"]):
            return self._current_company or "Tech Industry"
        elif any(kw in clean_label for kw in ["current role", "current title", "current position"]):
            return self._current_role
        elif any(kw in clean_label for kw in ["education", "degree"]):
            return self._education
        elif any(kw in clean_label for kw in ["university", "school", "college"]):
            return self._university
        elif any(kw in clean_label for kw in ["skill", "technology", "tech stack"]):
            return ", ".join(self._skills[:5])
        elif any(kw in clean_label for kw in ["cover letter", "motivation", "why do you want", "why are you interested", "why work", "why join"]):
            return self._generate_cover_letter_text()
        elif any(kw in clean_label for kw in ["country of birth", "born in", "birth country"]):
            return "India"
        elif any(kw in clean_label for kw in ["additional countries", "other countries of citizenship", "secondary citizenship"]):
            return "None"
        elif any(kw in clean_label for kw in ["countries of which you are a citizen", "citizenship countries", "country of citizenship", "citizenship"]):
            return "India"
        elif any(kw in clean_label for kw in ["hispanic", "latino"]):
            return "No"
        elif any(kw in clean_label for kw in ["summary", "about yourself", "introduce yourself", "tell us about"]):
            return self._generate_summary_text()
        elif any(kw in clean_label for kw in ["strength", "what are you good"]):
            return self._generate_strengths_text()
        elif any(kw in clean_label for kw in ["weakness", "improvement"]):
            return self._generate_weaknesses_text()
            
        return ""

    def _generate_cover_letter_text(self) -> str:
        """Generate a generic cover letter text."""
        return (
            f"I am {self._full_name}, a {self._current_role} with {self._years_experience} "
            f"years of experience specializing in {', '.join(self._skills[:3])}. "
            f"I am excited about this opportunity and confident that my skills and experience "
            f"align well with the requirements of this role. I am passionate about building "
            f"scalable, maintainable systems and am eager to contribute to your team's success."
        )

    def _generate_summary_text(self) -> str:
        """Generate a professional summary."""
        return (
            f"{self._full_name} - {self._current_role} with {self._years_experience}+ years "
            f"of experience in software development. Expertise in {', '.join(self._skills[:5])}. "
            f"Proven track record of delivering high-quality, scalable solutions. "
            f"Strong problem-solving skills and passion for clean, efficient code."
        )

    def _generate_strengths_text(self) -> str:
        """Generate strengths text."""
        return (
            f"My key strengths include strong problem-solving abilities, proficiency in "
            f"{', '.join(self._skills[:4])}, and excellent communication skills. "
            f"I excel at breaking down complex problems into manageable tasks and "
            f"delivering robust solutions within deadlines."
        )

    def _generate_weaknesses_text(self) -> str:
        """Generate weaknesses text (with positive spin)."""
        return (
            f"I sometimes focus too much on code perfection, which can slow down delivery. "
            f"However, I've been working on balancing quality with speed by setting clear "
            f"priorities and timeboxing tasks. I'm also continuously learning to delegate "
            f"and seek help when needed."
        )

    # ─── Link Fields ─────────────────────────────────────────────────

    async def _fill_link_fields(self, page):
        """Fill LinkedIn, GitHub, and other link fields."""
        link_fields = {
            "linkedin": self._linkedin_url,
            "github": self._github_url,
            "portfolio": self._portfolio_url,
            "website": self._portfolio_url or self._github_url,
        }
        
        for field_name, url in link_fields.items():
            if not url:
                continue
                
            selectors = [
                f"input[id*='{field_name}' i]:not([type='file'])",
                f"input[name*='{field_name}' i]:not([type='file'])",
                f"textarea[id*='{field_name}' i]",
                f"textarea[name*='{field_name}' i]",
                f"input[aria-label*='{field_name}' i]",
                f"input[placeholder*='{field_name}' i]",
                f"[aria-label*='{field_name}' i]:not([type='file'])",
                f"[placeholder*='{field_name}' i]:not([type='file'])",
            ]
            
            for selector in selectors:
                try:
                    el = page.locator(selector).first
                    if await el.count() == 0:
                        continue
                    if not await el.is_visible():
                        continue
                        
                    current = (await el.input_value() or "").strip()
                    if current and current.startswith("http"):
                        continue
                        
                    tag_name = await el.evaluate("el => el.tagName.toLowerCase()")
                    if tag_name in ("input", "textarea"):
                        await el.click(force=True)
                        await el.fill("")
                        await el.type(url, delay=30)
                        logger.info(f"[Greenhouse] ✓ Filled {field_name}: {url}")
                        break
                        
                except Exception:
                    continue

    # ─── Verification Code Handling ─────────────────────────────────

    async def _handle_verification_code(self, page) -> Optional[Dict[str, Any]]:
        """Handle email verification code flow."""
        try:
            page_text = (await page.inner_text("body")).lower()
            
            # Check if verification is needed
            if "verification code" not in page_text and "security code" not in page_text:
                return None
                
            logger.warning(
                f"\n{'=' * 65}\n"
                f"[Greenhouse] EMAIL VERIFICATION REQUIRED!\n"
                f"  Code sent to: {self._email}\n"
                f"  Auto-detecting from Gmail...\n"
                + "=" * 65
            )
            
            # Try auto-read from Gmail
            code = await self._try_get_verification_code_from_gmail()
            
            if code == "SUCCESS_CONFIRMED":
                logger.info("[Greenhouse] ✓ Application confirmed via email!")
                return {
                    "success": True,
                    "status": "applied",
                    "message": "Application submitted successfully"
                }
            elif code:
                logger.info(f"[Greenhouse] ✓ Auto-filling code: {code}")
                await self._fill_verification_boxes(page, code)
            else:
                logger.info("[Greenhouse] Waiting for manual code entry...")
                
            # Poll for up to 3 minutes
            for _ in range(36):  # 36 × 5s = 180s
                await page.wait_for_timeout(5000)
                
                current_text = (await page.inner_text("body")).lower()
                
                # Check success signals
                if any(sig in current_text for sig in [
                    "thank you", "application submitted", "application received",
                    "successfully submitted", "application has been received"
                ]):
                    if "verification code" not in current_text and "security code" not in current_text:
                        break
                        
            else:
                logger.error("[Greenhouse] Verification timeout")
                return {
                    "success": False,
                    "status": "failed",
                    "message": "Email verification code not entered in time"
                }
                
            # Take screenshot after verification
            await self._take_screenshot(page, "greenhouse_after_verification")
            
            final_text = (await page.inner_text("body")).lower()
            if any(sig in final_text for sig in [
                "thank you", "application submitted", "application received",
                "successfully submitted"
            ]):
                logger.info("[Greenhouse] ✓ Application submitted after verification!")
                return {
                    "success": True,
                    "status": "applied",
                    "message": "Application submitted successfully"
                }
                
        except Exception as e:
            logger.error(f"[Greenhouse] Verification error: {e}")
            
        return None

    async def _fill_verification_boxes(self, page, code: str):
        """Fill verification code input boxes."""
        try:
            # Try individual character boxes
            boxes = page.locator(
                "input[class*='verification'], input[maxlength='1'], "
                ".confirmation-code input, input[class*='code']"
            )
            count = await boxes.count()
            
            if count > 0:
                for i, char in enumerate(code[:count]):
                    try:
                        await boxes.nth(i).fill(char)
                    except Exception:
                        pass
                        
                await page.wait_for_timeout(500)
                await page.keyboard.press("Enter")
            else:
                # Try single input
                single = page.locator(
                    "input[name*='code'], input[id*='code'], #security_code, "
                    "input[placeholder*='code'], input[aria-label*='code']"
                ).first
                
                if await single.count() > 0:
                    await single.fill(code)
                    await page.keyboard.press("Enter")
                    
            # Click submit/confirm button
            for btn_sel in [
                "button:has-text('Submit')",
                "button:has-text('Confirm')",
                "button:has-text('Verify')",
                "button[type='submit']",
            ]:
                try:
                    btn = page.locator(btn_sel).first
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        break
                except Exception:
                    continue
                    
        except Exception as e:
            logger.warning(f"[Greenhouse] Verification box fill error: {e}")

    async def _try_get_verification_code_from_gmail(self) -> str:
        """Poll Gmail for verification code."""
        import imaplib
        import email as emaillib
        
        gmail_user = os.environ.get("GMAIL_ADDRESS", "")
        gmail_pass = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")
        
        if not gmail_user or not gmail_pass:
            logger.info("[Greenhouse] Gmail credentials not set")
            return ""
            
        logger.info(f"[Greenhouse] Polling Gmail ({gmail_user})...")
        
        for attempt in range(12):  # 12 × 5s = 60s
            try:
                mail = imaplib.IMAP4_SSL("imap.gmail.com")
                mail.login(gmail_user, gmail_pass)
                mail.select("inbox")
                
                # Search for verification emails
                search_queries = [
                    '(FROM "greenhouse.io" UNSEEN)',
                    '(SUBJECT "verification" UNSEEN)',
                    '(SUBJECT "security code" UNSEEN)',
                    '(SUBJECT "confirm" UNSEEN)',
                    '(SUBJECT "your code" UNSEEN)',
                ]
                
                ids = []
                for query in search_queries:
                    try:
                        _, data = mail.search(None, query)
                        found_ids = data[0].split()
                        if found_ids:
                            ids = found_ids
                            break
                    except Exception:
                        continue
                        
                if not ids:
                    mail.logout()
                    await asyncio.sleep(5)
                    continue
                    
                # Fetch latest email
                _, msg_data = mail.fetch(ids[-1], "(RFC822)")
                mail.logout()
                
                raw = msg_data[0][1]
                msg = emaillib.message_from_bytes(raw)
                
                # Extract body
                body = ""
                html_body = ""
                
                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        if content_type == "text/plain":
                            body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                        elif content_type == "text/html":
                            html_body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                else:
                    body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
                    html_body = body
                    
                combined = f"{body} {html_body}"
                
                # Check for confirmation
                if any(phrase in combined.lower() for phrase in [
                    "application has been received",
                    "thank you for applying",
                    "application submitted",
                ]):
                    logger.info("[Greenhouse] ✓ Confirmation email received!")
                    return "SUCCESS_CONFIRMED"
                    
                # Extract code from <h1> tag
                h1_match = re.search(r'<h1[^>]*>([A-Za-z0-9]{6,8})</h1>', combined, re.IGNORECASE)
                if h1_match:
                    return h1_match.group(1).strip()
                    
                # Extract code using regex
                patterns = [
                    r'(?:code|verification|security)[:\s]+([A-Za-z0-9]{6,8})',
                    r'\b([A-Z0-9]{6,8})\b',
                    r'\b(\d{6,8})\b',
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, combined, re.IGNORECASE)
                    if match:
                        code = match.group(1).strip()
                        if len(code) >= 6 and code.lower() not in ("security", "verify", "confirm"):
                            logger.info(f"[Greenhouse] ✓ Code found: {code}")
                            return code
                            
            except Exception as e:
                logger.debug(f"[Greenhouse] Gmail poll error: {e}")
                
            await asyncio.sleep(5)
            
        return ""

    # ─── Main Apply Method ───────────────────────────────────────────

    async def login(self) -> bool:
        """Greenhouse doesn't require login."""
        return True

    async def apply(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Main apply method."""
        raw_url = job.get("url", "")
        title = job.get("title", "Unknown Role")
        company = job.get("company", "Unknown Company")
        company_slug = job.get("company_slug", company.lower().replace(" ", ""))
        
        # Normalize URL
        url = self._normalize_url(raw_url, company_slug)
        
        logger.info(f"[Greenhouse] Applying to: {title} @ {company}")
        logger.info(f"[Greenhouse] URL: {url}")
        
        try:
            log_apply_start(title, company, url)
        except Exception:
            pass
            
        page = await self._get_page()
        
        try:
            # Navigate to page
            await self._navigate_to_application(page, url)
            
            # Fill all fields
            await self._fill_all_fields(page)
            
            # Submit application
            result = await self._submit_application(page, url)
            
            if result:
                return result
                
            # Handle verification if needed
            verification_result = await self._handle_verification_code(page)
            if verification_result:
                return {**verification_result, "application_url": url}
                
            # Check final status
            return await self._check_final_status(page, url, title, company)
            
        except Exception as e:
            logger.error(f"[Greenhouse] Apply error: {e}", exc_info=True)
            await self._take_screenshot(page, "greenhouse_error")
            
            try:
                log_apply_fail(title, company, str(e))
            except Exception:
                pass
                
            return {
                "success": False,
                "status": "failed",
                "message": str(e),
                "application_url": url
            }

    def _normalize_url(self, raw_url: str, company_slug: str) -> str:
        """Normalize Greenhouse URL to point directly to full application page."""
        url = raw_url
        
        # Handle /jobs/ pattern -> preserve clean job board URL
        if "/jobs/" in raw_url:
            job_id_match = re.search(r'/jobs/(\d+)', raw_url)
            if job_id_match and company_slug:
                return f"https://job-boards.greenhouse.io/{company_slug}/jobs/{job_id_match.group(1)}"

        # Handle gh_jid parameter
        gh_jid_match = re.search(r'gh_jid=(\d+)', raw_url)
        if gh_jid_match and company_slug:
            return f"https://job-boards.greenhouse.io/{company_slug}/jobs/{gh_jid_match.group(1)}"
                
        return url

    async def _navigate_to_application(self, page, url: str):
        """Navigate to application page."""
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            logger.warning(f"[Greenhouse] Page goto warning: {e}")
            
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
            
        await self._human_delay(1, 2)
        
        # Check if job posting has expired or been closed by the employer
        curr_url = page.url.lower()
        body_text = (await page.inner_text("body")).lower()
        if "error=true" in curr_url or "no longer available" in body_text or "no longer accepting applications" in body_text:
            logger.warning(f"[Greenhouse] ⚠️ Job posting closed/expired by employer: {url}")
            raise Exception("Job posting closed or expired by employer")

        # Click "Apply" button if present
        for btn_sel in [
            "a:has-text('Apply for this job')",
            "button:has-text('Apply for this job')",
            "#apply_button",
            "a:has-text('Apply Now')",
            "button:has-text('Apply Now')",
        ]:
            try:
                btn = page.locator(btn_sel).first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    await page.wait_for_load_state("networkidle", timeout=10000)
                    await self._human_delay(1, 2)
                    break
            except Exception:
                continue

    async def _fill_all_fields(self, page):
        """Fill all application fields."""
        # Standard fields
        await self._fill_standard_fields(page)
        await self._human_delay(0.5, 1)
        
        # Upload resume
        await self._upload_resume(page)
        await self._human_delay(0.5, 1)
        
        # Upload cover letter (if available)
        await self._upload_cover_letter(page)
        await self._human_delay(0.5, 1)
        
        # Education section (school, degree, discipline, dates)
        await self._fill_education_section(page)
        await self._human_delay(0.5, 1)
        
        # Custom questions
        await self._fill_custom_questions(page)
        await self._human_delay(1, 2)
        
        # Link fields
        await self._fill_link_fields(page)
        await self._human_delay(0.5, 1)

    async def _submit_application(self, page, url: str) -> Optional[Dict[str, Any]]:
        """Submit the application form with multi-strategy button clicking and JS submit fallback."""
        await self._take_screenshot(page, "greenhouse_before_submit")
        
        # 1. Dismiss any overlay cookie banners or popups blocking submit button
        for cookie_sel in [
            "#onetrust-accept-btn-handler",
            "button:has-text('Accept All')",
            "button:has-text('Accept Cookies')",
            "button:has-text('I Accept')",
            "button[id*='cookie' i]",
            ".cookie-banner button",
        ]:
            try:
                c_btn = page.locator(cookie_sel).first
                if await c_btn.is_visible(timeout=1000):
                    await c_btn.click(force=True)
                    await page.wait_for_timeout(300)
            except Exception:
                pass
        
        submitted = False
        submit_selectors = [
            "input[type='submit']",
            "button[type='submit']",
            "button:has-text('Submit application')",
            "button:has-text('Submit Application')",
            "#submit_app",
            "input[id='submit_app']",
            "button[id*='submit' i]",
            "input[value*='Submit' i]",
            "button:has-text('Submit')",
            "button:has-text('Apply')",
        ]

        # 2. Try clicking submit button across main frame and child frames
        frames_to_try = [page] + [f for f in page.frames if f != page.main_frame]

        for frame in frames_to_try:
            if submitted:
                break
            for sel in submit_selectors:
                try:
                    btn = frame.locator(sel).first
                    if await btn.count() > 0 and await btn.is_visible(timeout=1500):
                        await btn.scroll_into_view_if_needed()
                        await self._human_delay(0.3, 0.6)
                        
                        # Click with force=True to bypass transparent overlays
                        await btn.click(force=True)
                        submitted = True
                        logger.info(f"[Greenhouse] ✓ Clicked submit button ({sel})")
                        break
                except Exception:
                    continue

        # 3. Fallback: JavaScript form.requestSubmit() if button click didn't trigger
        if not submitted:
            for frame in frames_to_try:
                try:
                    js_submitted = await frame.evaluate("""() => {
                        const form = document.querySelector('form#application_form, form[action*="applications"], form');
                        if (form) {
                            if (typeof form.requestSubmit === 'function') {
                                form.requestSubmit();
                            } else {
                                form.submit();
                            }
                            return true;
                        }
                        return false;
                    }""")
                    if js_submitted:
                        submitted = True
                        logger.info("[Greenhouse] ✓ Triggered form submission via JS form.requestSubmit()")
                        break
                except Exception as e:
                    logger.debug(f"[Greenhouse] JS submit fallback error: {e}")

        if not submitted:
            await self._take_screenshot(page, "greenhouse_no_submit")
            return {
                "success": False,
                "status": "failed",
                "message": "Submit button not found",
                "application_url": url
            }
            
        # Wait for submission network request and page redirect
        await asyncio.sleep(4)
        await self._take_screenshot(page, "greenhouse_after_submit")
        return None
    async def _check_final_status(self, page, url: str, title: str, company: str, is_retry: bool = False) -> Dict[str, Any]:
        """Check final application status across main frame and iframes."""
        try:
            frames = [page] + [f for f in page.frames if f != page.main_frame]
            
            page_text = ""
            has_errors = False
            
            for frame in frames:
                try:
                    txt = await frame.inner_text("body")
                    if txt:
                        page_text += " " + txt.lower()
                except Exception:
                    pass
                    
                try:
                    err_locs = frame.locator(".error-message:visible, .field--error:visible, [role='alert']:visible, .invalid-feedback:visible, .form-error:visible")
                    if await err_locs.count() > 0:
                        has_errors = True
                except Exception:
                    pass
            
            if has_errors and not is_retry:
                logger.warning(f"[Greenhouse] Form validation failed on first attempt: {title} @ {company}. Attempting 1x retry...")
                await self._save_debug_html(page, "greenhouse_error_before_retry")
                
                # Re-fill all missed/unfilled fields and submit again
                await self._fill_all_fields(page)
                await self._submit_application(page, url)
                return await self._check_final_status(page, url, title, company, is_retry=True)

            if has_errors:
                logger.warning(f"[Greenhouse] Form validation failed after retry: {title} @ {company}")
                await self._save_debug_html(page, "greenhouse_error")
            
            # Check success signals in page text and URL
            current_url = page.url.lower()
            success_signals = [
                "application received",
                "application submitted",
                "thank you for applying",
                "thanks for applying",
                "successfully submitted",
                "application has been received",
                "received your application",
                "thank you for your interest",
                "thank you",
                "your application was submitted",
            ]
            
            url_success = any(kw in current_url for kw in ["confirmation", "thank_you", "thanks", "success", "submitted"])
            has_success = url_success or any(sig in page_text for sig in success_signals)
            
            if has_success and not has_errors:
                logger.info(f"[Greenhouse] 🎉 CONFIRMED SUCCESS: {title} @ {company}")
                try:
                    log_apply_success(title, company)
                except Exception:
                    pass
                    
                return {
                    "success": True,
                    "status": "applied",
                    "message": "Application submitted successfully",
                    "application_url": url
                }
            else:
                logger.warning(f"[Greenhouse] ❌ FAILED: {title} @ {company} (No confirmation signal)")
                try:
                    log_apply_fail(title, company, "No confirmation signal received")
                except Exception:
                    pass
                    
                return {
                    "success": False,
                    "status": "failed",
                    "message": "Form submitted but confirmation page was not reached",
                    "application_url": url
                }
                
        except Exception as e:
            logger.error(f"[Greenhouse] Status check error: {e}")
            return {
                "success": False,
                "status": "failed",
                "message": str(e),
                "application_url": url
            }

    async def _save_debug_html(self, page, prefix: str):
        """Save HTML content for debugging."""
        try:
            os.makedirs("logs", exist_ok=True)
            timestamp = int(time.time())
            
            html = await page.content()
            with open(f"logs/{prefix}_{timestamp}.html", "w", encoding="utf-8") as f:
                f.write(html)
                
            # Cleanup old files (keep last 10)
            import glob
            files = sorted(glob.glob(f"logs/{prefix}_*.html"), key=os.path.getmtime)
            if len(files) > 10:
                for old_file in files[:-10]:
                    try:
                        os.remove(old_file)
                    except Exception:
                        pass
                        
        except Exception as e:
            logger.debug(f"[Greenhouse] Debug HTML save error: {e}")


# ─── Standalone Runner ───────────────────────────────────────────────

async def apply_to_url(url: str) -> Dict[str, Any]:
    """Standalone runner for applying to a Greenhouse URL."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    
    APPLICATION["headless"] = False  # Show browser
    applier = GreenhouseApplier()
    
    # Extract company from URL
    company_match = re.search(r'greenhouse\.io/([^/]+)/jobs', url)
    company = company_match.group(1).replace("-", " ").title() if company_match else "Company"
    
    result = await applier.apply({
        "url": url,
        "title": "Software Engineer",
        "company": company,
        "portal": "greenhouse",
    })
    
    print(f"\n{'=' * 60}")
    print(f"Result: {'✅ SUCCESS' if result['success'] else '❌ FAILED'}")
    print(f"Message: {result['message']}")
    print(f"{'=' * 60}")
    
    # Clean up browser
    from applier.base_applier import _browser_manager
    if _browser_manager:
        await _browser_manager.stop()
        
    return result


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Apply to a Greenhouse job URL")
    parser.add_argument("--url", required=True, help="Greenhouse job URL")
    args = parser.parse_args()
    
    asyncio.run(apply_to_url(args.url))
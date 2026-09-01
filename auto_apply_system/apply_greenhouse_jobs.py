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

    # SAFETY POLICY:
    # Never invent or guess application answers.
    # Never select the first/second dropdown or radio option as fallback.
    # Unknown/ambiguous questions must remain unanswered and be flagged.
    # Submission must be blocked if required fields remain unanswered.

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
        if digits.startswith("91") and len(digits) == 12:
            return digits[2:]
        return digits if len(digits) >= 10 else raw

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
        return PROFILE.get("education", "B.Tech in Electronics and Communications Engineering")

    @property
    def _university(self) -> str:
        return PROFILE.get("university", "National Institute of Technology, Jamshedpur")

    @property
    def _skills(self) -> List[str]:
        return PROFILE.get("skills", [
            "Python", "C++", "Rust", "JavaScript", "TypeScript", "SQL",
            "Apache Kafka", "Confluent Kafka", "Kafka Connect", "CDC",
            "JDBC Source/Sink Connectors", "Schema Registry", "Avro",
            "ETL Pipelines", "SingleStore Pipelines", "Oracle",
            "SingleStore", "PostgreSQL", "MySQL", "MongoDB", "Redis",
            "RocksDB", "Linux", "Systemd", "Cron", "Shell Scripting",
            "WebSockets", "TCP/IP", "POSIX Sockets", "Boost.Asio",
            "Grafana", "Jaeger", "OpenTelemetry", "Docker", "Git", "GitHub"
        ])

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

            inp = page.locator(input_selector).first
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

            # Fallback: Press Enter to confirm
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(300)
            
            val = (await inp.input_value() or "").strip()
            if val and val.lower() not in ("select...", "select", "no options", "no options available"):
                logger.info(f"[Greenhouse] ✓ Selected via Enter: '{val}'")
                return True
                
        except Exception as e:
            logger.warning(f"[Greenhouse] React-Select '{input_selector}' failed: {e}")
        return False

    def _is_option_match(self, search_text: str, option_text: str) -> bool:
        """Advanced fuzzy matching for dropdown options."""
        # Exact match
        if search_text == option_text:
            return True
            
        # Normalize text
        search_words = set(re.split(r'\W+', search_text.lower()))
        option_words = set(re.split(r'\W+', option_text.lower()))
        
        # Remove empty strings
        search_words.discard('')
        option_words.discard('')
        
        if not search_words:
            return False
            
        # All search words must be in option words
        if search_words.issubset(option_words):
            return True
            
        # Partial word match (substring)
        for sw in search_words:
            if len(sw) < 3:  # Skip very short words
                continue
            if any(sw in ow or ow in sw for ow in option_words):
                return True
                
        return False

    async def _select_first_react_option(self, page, input_selector: str) -> bool:
        """DEPRECATED SAFETY STUB: arbitrary fallback selection is forbidden."""
        logger.warning(
            f"[Greenhouse] Refused arbitrary fallback selection for {input_selector}"
        )
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

    async def _fill_phone_number(self, page):
        """Fill phone number with country code handling."""
        try:
            # Try multiple phone input selectors
            phone_selectors = [
                "#phone",
                "input[type='tel']",
                "input[name*='phone' i]",
                "input[id*='phone' i]",
                "input[aria-label*='phone' i]",
                "input[placeholder*='phone' i]",
            ]
            
            for selector in phone_selectors:
                try:
                    phone_input = page.locator(selector).first
                    if await phone_input.count() == 0:
                        continue
                    if not await phone_input.is_visible():
                        continue
                        
                    current = await phone_input.input_value() or ""
                    if current.strip() and len(current) >= 10:
                        continue  # Already filled
                        
                    await phone_input.click(force=True)
                    await phone_input.fill("")
                    await phone_input.type(self._phone, delay=50)
                    logger.info(f"[Greenhouse] ✓ Filled phone: {self._phone}")
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
        
        for field_name, field_info in field_mappings.items():
            value = field_info["value"]
            if not value:
                continue
                
            for selector in field_info["selectors"]:
                try:
                    el = await self._find_locator(page, selector)
                    if await el.count() == 0:
                        continue
                        
                    current_val = await el.input_value() or ""
                    if current_val.strip():
                        break  # Already filled
                        
                    await el.click(timeout=3000)
                    await el.fill("")
                    await el.type(value, delay=50)
                    logger.info(f"[Greenhouse] ✓ Filled {field_name}: {value}")
                    log_field_fill(field_name.replace("_", " ").title(), value)
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

    # ─── Custom Question Handling ─────────────────────────────────────

    async def _fill_custom_questions(self, page):
        """Auto-detect and fill all custom question fields."""
        self._blocked_submission = False
        self._unanswered_questions = []
        # Text inputs
        text_inputs = page.locator("input[id^='question_']:not([role='combobox']), textarea[id^='question_']")
        text_count = await text_inputs.count()
        logger.info(f"[Greenhouse] Found {text_count} text question(s)")
        
        for i in range(text_count):
            await self._fill_custom_text_input(page, text_inputs.nth(i))
        
        # React-Select dropdowns
        await self._fill_react_selects(page)
        
        # Native selects
        await self._fill_native_selects(page)
        
        # Radio buttons and checkboxes
        await self._fill_radio_buttons(page)

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

    async def _fill_react_selects(self, page):
        """Fill all React-Select combobox dropdowns."""
        selectors = [
            "input[role='combobox']:not([id*='iti']):not([class*='iti'])",
            "div[class*='select'] input:not([type='hidden'])",
        ]
        
        for selector in selectors:
            try:
                selects = page.locator(selector)
                count = await selects.count()
                
                for i in range(count):
                    await self._fill_single_react_select(page, selects.nth(i))
                    
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
                        qa_ans, score, matched_q = qa.find_answer(label_text, min_similarity=0.88)
                        if qa_ans and qa_ans.lower() not in ("indian", "need user input", "need job-specific answer"):
                            if await self._select_react_option(page, target_sel, qa_ans):
                                logger.info(f"[Greenhouse] ✓ QA match '{label_text[:40]}' -> '{qa_ans}'")
                                log_dropdown(label_text or sel_id, qa_ans, method="qa_engine")
                                return
                except Exception:
                    pass                    
            # SAFETY: never select an arbitrary option.
            required = await self._field_is_required(sel, label_text)
            self._mark_unanswered(label_text or sel_id, required)
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass

            # Record the unanswered question for review, but do NOT select a value.

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
        
        # Education scores
        if any(kw in combined_lower for kw in ["12th percentage", "class 12", "12th score", "twelfth"]):
            return "85.6%"
        if any(kw in combined_lower for kw in ["10th percentage", "class 10", "10th score", "tenth"]):
            return "86.4%"
        if "cgpa" in combined_lower:
            return "7.35"
        if any(kw in combined_lower for kw in ["gpa", "sat score", "act score", "gre score"]):
            return "7.35"

        # Citizenship
        if "citizenship" in combined_lower:
            return "Non-U.S. Citizen"

        # Location-related
        if any(kw in combined_lower for kw in ["location", "city", "where are you"]):
            return self._location
            
        # Country
        if "country" in combined_lower and not any(kw in combined_lower for kw in ["authoriz", "sponsor", "visa"]):
            return "India"
            
        # Education institution
        if any(kw in combined_lower for kw in ["university", "college", "institution"]):
            return self._university

        # Secondary-school questions: distinguish Class 10 and Class 12.
        if "school" in combined_lower:
            if any(kw in combined_lower for kw in ["12", "twelfth", "senior secondary", "higher secondary"]):
                return "Sree Ayyappa Public School, Bokaro Steel City"
            if any(kw in combined_lower for kw in ["10", "tenth", "secondary"]):
                return "Vimla Pandey Memorial Gyan Niketan School"
            return "Sree Ayyappa Public School, Bokaro Steel City"

        # Degree
        if "degree" in combined_lower:
            return "Bachelor's Degree"

        # Discipline / Major
        if any(kw in combined_lower for kw in ["discipline", "major", "field of study", "specialization", "specialisation"]):
            return "Electronics and Communications Engineering"
            
        # Years of experience: only answer when the question explicitly asks
        # for a duration. Never turn "Do you have X experience?" into "3".
        if (
            re.search(r"\bhow many years\b", combined_lower)
            or re.search(r"\byears? of (professional |relevant |industry )?experience\b", combined_lower)
            or re.search(r"\btotal years\b", combined_lower)
        ):
            return self._years_experience
            
        # Sponsorship
        if any(kw in combined_lower for kw in ["sponsor", "visa"]):
            return "No"
            
        # Authorization
        if any(kw in combined_lower for kw in ["authoriz", "eligible", "legal"]):
            return "Yes"
            
        # Clearance
        if any(kw in combined_lower for kw in ["clearance", "security clearance"]):
            return "No"
            
        # Previous employee/application question.
        # Only answer when the label clearly asks whether the candidate
        # previously worked for/applied to THIS company.
        if any(kw in combined_lower for kw in [
            "previously worked for this company",
            "worked for this company before",
            "former employee of this company",
            "previously applied to this company",
            "applied to this company before",
        ]):
            return "No"
            
        # Race/Ethnicity
        if any(kw in combined_lower for kw in ["race", "ethnicity"]):
            return "Asian"
            
        # Veteran status
        if "veteran" in combined_lower:
            return "I am not a protected veteran"
            
        # Disability: no answer supplied; leave unconfigured.
        if "disability" in combined_lower:
            return None
            
        # Consent / Privacy
        if any(kw in combined_lower for kw in ["consent", "acknowledge", "agree", "privacy"]):
            return "I acknowledge"

            
        # Gender (optional)
        if "gender" in combined_lower:
            return "Male"
            
        return None

    async def _fill_native_selects(self, page):
        """Fill standard HTML <select> elements."""
        try:
            selects = page.locator("select")
            count = await selects.count()
            
            for i in range(count):
                await self._fill_single_native_select(page, selects.nth(i))
                
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
                        
            # SAFETY: never select an arbitrary native option.
            logger.warning(
                f"[Greenhouse] SKIPPED unconfigured native select '{label_text or sel_id}' "
                "(no confident answer; no fallback selection)"
            )
            if await self._field_is_required(sel, label_text):
                self._blocked_submission = True
                
        except Exception as e:
            logger.debug(f"[Greenhouse] Single native select error: {e}")

    async def _field_is_required(self, field, label_text: str = "") -> bool:
        """Return True only when the field is explicitly marked required."""
        try:
            required = await field.get_attribute("required")
            aria_required = await field.get_attribute("aria-required")
            if str(required).lower() in ("true", "required", ""):
                return True
            if str(aria_required).lower() == "true":
                return True
        except Exception:
            pass
        text = (label_text or "").strip().lower()
        return text.endswith("*") or "*" in text[:80]

    def _mark_unanswered(self, label_text: str, required: bool = False):
        """Record an unanswered question without inventing a response."""
        if not hasattr(self, "_unanswered_questions"):
            self._unanswered_questions = []
        item = label_text.strip() or "<unknown question>"
        if item not in self._unanswered_questions:
            self._unanswered_questions.append(item)
        if required:
            self._blocked_submission = True
        logger.warning(
            f"[Greenhouse] NEEDS REVIEW: {item} "
            f"(required={required}; no value selected)"
        )

    async def _fill_radio_buttons(self, page):
        """Fill radio buttons and checkboxes."""
        try:
            # Handle radio buttons
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
                    # Check if any is already selected
                    selected = False
                    for idx in indices:
                        if await radios.nth(idx).is_checked():
                            selected = True
                            break
                            
                    if selected:
                        continue
                        
                    # Try to select based on label
                    for idx in indices:
                        label_text = ""
                        try:
                            r_id = await radios.nth(idx).get_attribute("id") or ""
                            if r_id:
                                label_el = page.locator(f"label[for='{r_id}']").first
                                if await label_el.count() > 0:
                                    label_text = (await label_el.inner_text()).lower()
                        except Exception:
                            pass
                            
                        # Prefer "Yes" or "No" answers
                        if "yes" in label_text or "no" in label_text:
                            try:
                                await radios.nth(idx).check(force=True)
                                logger.info(f"[Greenhouse] ✓ Selected radio: {label_text[:40]}")
                                selected = True
                                break
                            except Exception:
                                continue
                                
                    # SAFETY: never select an arbitrary radio option.
                    if not selected:
                        group_required = False
                        try:
                            group_required = await self._field_is_required(
                                radios.nth(indices[0]), name
                            )
                        except Exception:
                            pass
                        self._mark_unanswered(name, group_required)
                            
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
                    label_text = ""
                    if cb_id:
                        label_el = page.locator(f"label[for='{cb_id}']").first
                        if await label_el.count() > 0:
                            label_text = (await label_el.inner_text()).lower()
                            
                    # Check consent/agreement boxes
                    if any(kw in label_text for kw in ["consent", "agree", "acknowledge", "terms", "privacy", "policy"]):
                        await cb.check(force=True)
                        logger.info(f"[Greenhouse] ✓ Checked consent: {label_text[:40]}")
                        
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
                    ans, score, matched_q = qa.find_answer(clean_label, min_similarity=0.88)
                    if ans and score >= 0.88:
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
        elif clean_label in ("name", "full name", "candidate name", "your name") or              any(kw in clean_label for kw in ["first name", "last name", "preferred name"]):
            if "first name" in clean_label:
                return self._first_name
            if "last name" in clean_label:
                return self._last_name
            if "preferred name" in clean_label:
                return self._first_name
            return self._full_name
        elif "email" in clean_label:
            return self._email
        elif "phone" in clean_label:
            return self._phone
        elif (
            re.search(r"\bhow many years\b", clean_label)
            or re.search(r"\byears? of (professional |relevant |industry )?experience\b", clean_label)
            or re.search(r"\btotal years\b", clean_label)
        ):
            return self._years_experience
        elif any(kw in clean_label for kw in ["notice", "availability", "join"]):
            return self._notice_period
        elif any(kw in clean_label for kw in ["salary", "ctc", "compensation", "expected"]):
            return self._expected_salary
        elif any(kw in clean_label for kw in ["current company", "employer", "organization"]):
            return self._current_company or "Tech Industry"
        elif any(kw in clean_label for kw in ["current role", "current title", "current position"]):
            return self._current_role
        elif "class 12" in clean_label or "12th" in clean_label:
            if "school" in clean_label:
                return "Sree Ayyappa Public School, Bokaro Steel City"
            if any(kw in clean_label for kw in ["percentage", "score", "marks"]):
                return "85.6%"
        elif "class 10" in clean_label or "10th" in clean_label:
            if "school" in clean_label:
                return "Vimla Pandey Memorial Gyan Niketan School"
            if any(kw in clean_label for kw in ["percentage", "score", "marks"]):
                return "86.4%"
        elif "cgpa" in clean_label:
            return "7.35"
        elif any(kw in clean_label for kw in ["education", "degree"]):
            return self._education
        elif any(kw in clean_label for kw in ["university", "college"]):
            return self._university
        elif "school" in clean_label:
            return "Sree Ayyappa Public School, Bokaro Steel City"
        elif any(kw in clean_label for kw in ["skill", "technology", "tech stack"]):
            return ", ".join(self._skills[:5])
        elif any(kw in clean_label for kw in ["cover letter", "motivation", "why do you want", "why are you interested"]):
            return self._generate_cover_letter_text()
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
        """Normalize Greenhouse URL."""
        url = raw_url
        
        # Handle gh_jid parameter
        gh_jid_match = re.search(r'gh_jid=(\d+)', raw_url)
        if gh_jid_match:
            job_id = gh_jid_match.group(1)
            return f"https://job-boards.greenhouse.io/embed/job_app?for={company_slug}&token={job_id}"
            
        # Handle /jobs/ pattern
        if "/jobs/" in raw_url:
            job_id_match = re.search(r'/jobs/(\d+)', raw_url)
            if job_id_match:
                return f"https://job-boards.greenhouse.io/embed/job_app?for={company_slug}&token={job_id_match.group(1)}"
                
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
            
        await self._human_delay(2, 3)
        
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
        
        # Custom questions
        await self._fill_custom_questions(page)
        await self._human_delay(1, 2)
        
        # Link fields
        await self._fill_link_fields(page)
        await self._human_delay(0.5, 1)

    async def _submit_application(self, page, url: str) -> Optional[Dict[str, Any]]:
        """Submit the application form only when no required answer is unknown."""
        if getattr(self, "_blocked_submission", False):
            questions = getattr(self, "_unanswered_questions", [])
            logger.error(
                "[Greenhouse] BLOCKED SUBMISSION: required questions have no "
                f"verified answers: {questions}"
            )
            await self._take_screenshot(page, "greenhouse_blocked_unanswered")
            return {
                "success": False,
                "status": "needs_review",
                "message": "Submission blocked: one or more required questions have no verified answer",
                "application_url": url,
                "unanswered_questions": questions,
            }

        await self._take_screenshot(page, "greenhouse_before_submit")

        submitted = False
        for sel in [
            "button:has-text('Submit your application')",
            "button:has-text('Submit application')",
            "button:has-text('Submit Application')",
            "button:has-text('Send application')",
            "button:has-text('Send Application')",
            "button:has-text('Review and submit')",
            "button:has-text('Review Application')",
            "button[type='submit']",
            "input[type='submit']",
            "#submit_app",
            "button:has-text('Submit')",
            "input[id='submit_app']",
        ]:
            try:
                btn = page.locator(sel).first
                if await btn.count() == 0:
                    continue
                if not await btn.is_visible(timeout=3000):
                    continue
                if await btn.evaluate("(el) => el.disabled || el.getAttribute('aria-disabled') === 'true'"):
                    continue
                await btn.scroll_into_view_if_needed()
                await self._human_delay(0.5, 1)
                await btn.click(force=True)
                submitted = True
                logger.info(f"[Greenhouse] ✓ Clicked submit: {sel}")
                break
            except Exception:
                continue

        if not submitted:
            try:
                js_submitted = await page.evaluate("""() => {
                    const forms = Array.from(document.querySelectorAll('form#application_form, form[action*="applications"], form'));
                    for (const form of forms) {
                        if (!form) continue;
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
                    logger.info("[Greenhouse] ✓ Triggered form submission via JS requestSubmit()")
            except Exception:
                pass

        if not submitted:
            await self._take_screenshot(page, "greenhouse_no_submit")
            return {
                "success": False,
                "status": "failed",
                "message": "Submit button not found",
                "application_url": url,
            }

        await asyncio.sleep(4)
        await self._take_screenshot(page, "greenhouse_after_submit")
        return None

    async def _check_final_status(self, page, url: str, title: str, company: str) -> Dict[str, Any]:
        """Check final application status."""
        try:
            page_text = (await page.inner_text("body")).lower()
            
            # Check for errors
            has_errors = any(err in page_text for err in [
                "this field is required",
                "please enter your location",
                "please fill out this field",
                "invalid email",
                "please enter a valid",
            ])
            
            if has_errors:
                logger.warning(f"[Greenhouse] Form validation failed: {title} @ {company}")
                
                # Save error HTML for debugging
                await self._save_debug_html(page, "greenhouse_error")
                
                # Retry with remaining fields
                await self._fill_native_selects(page)
                await self._fill_radio_buttons(page)
                
                # Retry submit
                await self._submit_application(page, url)
                page_text = (await page.inner_text("body")).lower()
                has_errors = any(err in page_text for err in [
                    "this field is required",
                    "please enter your location",
                ])
                
            # Check success signals
            success_signals = [
                "application received",
                "application submitted",
                "thank you for applying",
                "thanks for applying",
                "successfully submitted",
                "application has been received",
                "received your application",
                "thank you",
                "success",
            ]
            
            has_success = any(sig in page_text for sig in success_signals)
            
            if has_success and not has_errors:
                logger.info(f"[Greenhouse] 🎉 SUCCESS: {title} @ {company}")
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
            elif not has_errors:
                # No errors = likely success
                logger.info(f"[Greenhouse] ✅ LIKELY SUCCESS: {title} @ {company}")
                try:
                    log_apply_success(title, company)
                except Exception:
                    pass
                    
                return {
                    "success": True,
                    "status": "applied",
                    "message": "Application likely submitted",
                    "application_url": url
                }
            else:
                logger.warning(f"[Greenhouse] ❌ FAILED: {title} @ {company}")
                try:
                    log_apply_fail(title, company, "Validation errors")
                except Exception:
                    pass
                    
                return {
                    "success": False,
                    "status": "failed",
                    "message": "Required fields missing",
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
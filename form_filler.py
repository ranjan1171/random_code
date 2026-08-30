"""
applier/form_filler.py — Generic intelligent form filler.
Detects and fills common job application form fields using
field label detection and smart matching to Ranjan's profile.
"""

import logging
import os
from typing import Any, Dict, Optional

from config import PROFILE, APPLICATION

logger = logging.getLogger(__name__)


class FormFiller:
    """
    Intelligent form filler for generic job application forms.
    Detects fields by label text, placeholder, name, and id attributes.
    """

    # Mapping of field patterns → profile data
    FIELD_MAPPINGS = {
        # Name fields
        "full.?name|your.?name|applicant.?name": PROFILE["name"],
        "first.?name|given.?name": PROFILE["name"].split()[0],
        "last.?name|family.?name|surname": " ".join(PROFILE["name"].split()[1:]),

        # Contact fields
        "email|e.mail|email.?address": PROFILE["email"],
        "phone|mobile|contact.?number|cell": PROFILE["phone"].replace("+91 ", ""),
        "phone.?with.?country|country.?code.?phone": PROFILE["phone"],

        # Location
        "city|location|current.?city|current.?location": "Pune",
        "state|province": "Maharashtra",
        "country|nationality": "India",
        "pin.?code|zip|postal": "411001",

        # Experience
        "years.?of.?exp|total.?exp|experience": "1",
        "current.?salary|ctc|current.?ctc": "700000",  # 7 LPA (approx)
        "expected.?salary|expected.?ctc": "1000000",   # 10 LPA expected

        # Notice period
        "notice.?period|joining.?time": "30",

        # LinkedIn
        "linkedin|linkedin.?profile|linkedin.?url": PROFILE["linkedin"],

        # GitHub
        "github|github.?profile|github.?url": PROFILE["github"],

        # Portfolio
        "portfolio|website|personal.?site": PROFILE["github"],

        # Highest qualification
        "qualification|degree|education": "B.Tech",
        "college|university|institution": "NIT Jamshedpur",
        "graduation.?year|passing.?year": "2025",
        "cgpa|gpa|percentage": "7.35",

        # Current company
        "current.?company|current.?employer|working.?at": "WhiteKlay",
        "current.?designation|current.?role|current.?position": "Software Developer 1",

        # Skills
        "skills|technical.?skills|key.?skills": "Python, Kafka, Rust, C++, Node.js, Distributed Systems, REST API",
    }

    def __init__(self):
        self.cv_path = PROFILE.get("cv_pdf_path", "")

    async def fill_form(self, page: Any, job: Dict[str, Any] = None) -> int:
        """
        Auto-fill all detectable fields on the current page.
        Returns count of fields filled.
        """
        filled = 0

        try:
            # Get all input elements
            inputs = page.locator("input:not([type='hidden']):not([type='submit']):not([type='button']):not([type='checkbox']):not([type='radio'])")
            count = await inputs.count()

            for i in range(count):
                element = inputs.nth(i)
                try:
                    if not await element.is_visible():
                        continue

                    # Get field context
                    field_name = (await element.get_attribute("name") or "").lower()
                    field_id = (await element.get_attribute("id") or "").lower()
                    placeholder = (await element.get_attribute("placeholder") or "").lower()
                    field_type = (await element.get_attribute("type") or "text").lower()

                    # Find label text
                    label_text = await self._find_label(page, element) or ""
                    label_text = label_text.lower()

                    context = f"{field_name} {field_id} {placeholder} {label_text}"

                    if field_type == "file":
                        # File upload — try to upload CV
                        if any(kw in context for kw in ["resume", "cv", "upload", "attach"]):
                            if self.cv_path and os.path.exists(self.cv_path):
                                await element.set_input_files(self.cv_path)
                                logger.info(f"[FormFiller] Uploaded CV to field '{field_id or field_name}'")
                                filled += 1
                        continue

                    # Match field to profile data
                    value = self._match_field(context)
                    if value is not None:
                        current_val = await element.input_value()
                        if not current_val:  # Don't overwrite already-filled fields
                            await element.fill(str(value))
                            filled += 1
                            logger.debug(f"[FormFiller] Filled '{context[:40]}' = '{str(value)[:30]}'")

                except Exception as e:
                    logger.debug(f"[FormFiller] Field {i} error: {e}")
                    continue

            # Handle textareas (cover letter, about, etc.)
            textareas = page.locator("textarea")
            ta_count = await textareas.count()
            for i in range(ta_count):
                ta = textareas.nth(i)
                try:
                    if not await ta.is_visible():
                        continue
                    ta_name = (await ta.get_attribute("name") or "").lower()
                    ta_id = (await ta.get_attribute("id") or "").lower()
                    ta_placeholder = (await ta.get_attribute("placeholder") or "").lower()
                    label = await self._find_label(page, ta) or ""
                    context = f"{ta_name} {ta_id} {ta_placeholder} {label}".lower()

                    current_val = await ta.input_value()
                    if current_val:
                        continue

                    if any(kw in context for kw in ["cover", "motivation", "why", "letter"]):
                        cover = job.get("cover_letter") if job else None
                        text = cover or PROFILE.get("default_cover_letter", "")
                        if text:
                            await ta.fill(text)
                            filled += 1
                            logger.info(f"[FormFiller] Filled cover letter textarea")
                    elif any(kw in context for kw in ["about", "summary", "objective", "profile"]):
                        await ta.fill(PROFILE.get("default_cover_letter", "")[:500])
                        filled += 1

                except Exception as e:
                    logger.debug(f"[FormFiller] Textarea {i} error: {e}")

        except Exception as e:
            logger.error(f"[FormFiller] Form fill error: {e}")

        logger.info(f"[FormFiller] Filled {filled} fields")
        return filled

    async def _find_label(self, page: Any, element: Any) -> Optional[str]:
        """Find label text associated with an input element."""
        try:
            # Try 'for' attribute matching
            el_id = await element.get_attribute("id")
            if el_id:
                label = page.locator(f"label[for='{el_id}']")
                if await label.count() > 0:
                    return await label.first.inner_text()

            # Try aria-label
            aria = await element.get_attribute("aria-label")
            if aria:
                return aria

            # Try parent label
            parent = element.locator("xpath=..")
            parent_tag = await parent.evaluate("el => el.tagName")
            if parent_tag.lower() == "label":
                return await parent.inner_text()

            # Try preceding sibling label
            prev_label = element.locator("xpath=preceding-sibling::label[1]")
            if await prev_label.count() > 0:
                return await prev_label.first.inner_text()

        except Exception:
            pass
        return None

    def _match_field(self, context: str) -> Optional[str]:
        """Match field context to profile data using pattern matching."""
        import re
        for pattern, value in self.FIELD_MAPPINGS.items():
            if re.search(pattern, context, re.I):
                return value
        return None

    async def handle_selects(self, page: Any):
        """Handle dropdown select elements."""
        try:
            selects = page.locator("select")
            count = await selects.count()
            for i in range(count):
                sel = selects.nth(i)
                try:
                    if not await sel.is_visible():
                        continue

                    sel_name = (await sel.get_attribute("name") or "").lower()
                    sel_id = (await sel.get_attribute("id") or "").lower()
                    context = f"{sel_name} {sel_id}"

                    if any(kw in context for kw in ["experience", "exp.level", "years"]):
                        # Try to select "0-1 years" or "1-2 years"
                        for val in ["0-1", "1-2", "fresher", "0", "1", "entry"]:
                            try:
                                await sel.select_option(label=val, timeout=1000)
                                break
                            except Exception:
                                pass

                    elif any(kw in context for kw in ["notice", "joining"]):
                        for val in ["30", "1 month", "30 days", "immediate"]:
                            try:
                                await sel.select_option(label=val, timeout=1000)
                                break
                            except Exception:
                                pass

                    elif any(kw in context for kw in ["qualification", "degree"]):
                        for val in ["B.Tech", "BTech", "Bachelor", "Graduation"]:
                            try:
                                await sel.select_option(label=val, timeout=1000)
                                break
                            except Exception:
                                pass

                except Exception as e:
                    logger.debug(f"[FormFiller] Select {i} error: {e}")
        except Exception as e:
            logger.debug(f"[FormFiller] handle_selects error: {e}")

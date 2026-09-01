"""Inspect the HTML structure of the 'referred' question field."""
import asyncio
import json
import sys
import logging
from playwright.async_api import async_playwright

sys.path.insert(0, '.')

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("diagnose")

async def diagnose():
    with open('greenhouse_matched_jobs.json') as f:
        jobs = json.load(f)['matched_jobs']
    
    job = jobs[2]  # Job #3 with the 'referred' blocker
    logger.info(f"Diagnosing: {job['title']} @ {job['company']}")
    
    # Use the normalized embed URL directly
    embed_url = f"https://job-boards.greenhouse.io/embed/job_app?for=coinbase&token=8054153"
    logger.info(f"URL: {embed_url}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # headless=False to see the browser
        page = await browser.new_page()
        
        await page.goto(embed_url, wait_until='domcontentloaded')
        await asyncio.sleep(3)
        
        # Click apply button if it exists
        apply_btn = page.locator("button:has-text('Apply')")
        if await apply_btn.count() > 0:
            logger.info("Found apply button, clicking...")
            await apply_btn.click()
            await asyncio.sleep(3)
        else:
            logger.info("No apply button found, likely already in form")
        
        # Look for the referred field in the HTML
        # Try to find any element containing the "referred" text
        logger.info("Searching for 'referred' field in page HTML...")
        
        # Get all text content
        body_text = await page.inner_text("body")
        if "referred to this position" in body_text.lower():
            logger.info("✓ Found 'referred to this position' text on page")
        
        # Check for radio buttons with this question
        radios = page.locator("input[type='radio']")
        radio_count = await radios.count()
        logger.info(f"Found {radio_count} radio button(s) on page")
        
        # Find fieldsets with legends
        fieldsets = page.locator("fieldset")
        fs_count = await fieldsets.count()
        logger.info(f"Found {fs_count} fieldset(s) on page")
        
        for i in range(fs_count):
            fs = fieldsets.nth(i)
            legend = fs.locator("legend")
            if await legend.count() > 0:
                legend_text = await legend.inner_text()
                if "referred" in legend_text.lower():
                    logger.info(f"✓ Fieldset {i} has legend: '{legend_text}'")
                    
                    # Get the inner HTML
                    inner_html = await fs.inner_html()
                    logger.info(f"Fieldset HTML:\n{inner_html[:1000]}")
        
        # Also search for any label containing "referred"
        labels = page.locator("label")
        label_count = await labels.count()
        logger.info(f"Searching {label_count} labels for 'referred'...")
        for i in range(label_count):
            lbl = labels.nth(i)
            text = await lbl.inner_text()
            if "referred" in text.lower():
                logger.info(f"✓ Label {i}: '{text[:80]}'")
                # Get the input element it's linked to
                for_attr = await lbl.get_attribute("for")
                logger.info(f"Label for: {for_attr}")
                
                if for_attr:
                    # Find the element with this ID
                    elem = page.locator(f"#{for_attr}").first
                    if await elem.count() > 0:
                        tag = await elem.evaluate("el => el.tagName")
                        type_attr = await elem.get_attribute("type")
                        class_attr = await elem.get_attribute("class")
                        role = await elem.get_attribute("role")
                        logger.info(f"  Input tag: {tag}")
                        logger.info(f"  Type: {type_attr}")
                        logger.info(f"  Class: {class_attr}")
                        logger.info(f"  Role: {role}")
                        
                        # Try to find React-Select wrapper
                        parent = elem.evaluate("el => el.parentElement?.className || ''")
                        logger.info(f"  Parent class: {parent}")
        
        # Try to find by aria-label or other attributes
        elements = page.locator("[aria-label*='referred' i]")
        elem_count = await elements.count()
        logger.info(f"Found {elem_count} element(s) with aria-label containing 'referred'")
        for i in range(elem_count):
            elem = elements.nth(i)
            aria_label = await elem.get_attribute("aria-label")
            logger.info(f"✓ Element {i}: aria-label='{aria_label}'")
            tag_name = await elem.evaluate("el => el.tagName")
            logger.info(f"  Tag: {tag_name}")
        
        # Scroll to find the referred field
        logger.info("Scrolling to find 'referred' field...")
        await page.locator("body").evaluate("el => el.scrollTop = el.scrollHeight")
        await asyncio.sleep(1)
        
        # Take screenshot
        screenshot_path = "logs/diagnose_field_screenshot.png"
        await page.screenshot(path=screenshot_path)
        logger.info(f"Screenshot saved to: {screenshot_path}")
        
        await browser.close()

asyncio.run(diagnose())

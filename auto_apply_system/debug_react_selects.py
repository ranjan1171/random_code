"""Check which React-Select fields are found on the form."""
import asyncio
import json
import sys
import logging
from playwright.async_api import async_playwright

sys.path.insert(0, '.')

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("debug_react")

async def debug():
    with open('greenhouse_matched_jobs.json') as f:
        jobs = json.load(f)['matched_jobs']
    
    job = jobs[2]  # Job #3
    embed_url = f"https://job-boards.greenhouse.io/embed/job_app?for=coinbase&token=8054153"
    logger.info(f"Loading: {embed_url}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        await page.goto(embed_url, wait_until='domcontentloaded')
        await asyncio.sleep(2)
        
        # Click apply
        apply_btn = page.locator("button:has-text('Apply')")
        if await apply_btn.count() > 0:
            await apply_btn.click()
            await asyncio.sleep(3)
        
        # Find all React-Select inputs (combobox inputs)
        selector = "input[role='combobox']:not([id*='iti']):not([class*='iti'])"
        combobox_inputs = page.locator(selector)
        count = await combobox_inputs.count()
        logger.info(f"Found {count} combobox inputs matching selector")
        
        for i in range(count):
            inp = combobox_inputs.nth(i)
            inp_id = await inp.get_attribute("id") or ""
            inp_class = await inp.get_attribute("class") or ""
            inp_value = await inp.input_value() or ""
            
            # Get associated label
            label_text = ""
            if inp_id:
                lbl = page.locator(f"label[for='{inp_id}']").first
                if await lbl.count() > 0:
                    label_text = await lbl.inner_text()
            
            logger.info(f"  [{i}] ID: {inp_id}, Value: '{inp_value[:20]}', Label: '{label_text[:40]}'")
            
            # Check if this is the "referred" field
            if "referred" in label_text.lower():
                logger.info(f"    ✓ THIS IS THE REFERRED FIELD!")
        
        # Also check if the selector is looking for the right things
        logger.info("\nChecking for input[role='combobox'] without negative conditions:")
        all_combobox = page.locator("input[role='combobox']")
        all_count = await all_combobox.count()
        logger.info(f"Found {all_count} total combobox inputs (including ITI)")
        
        for i in range(min(3, all_count)):
            inp = all_combobox.nth(i)
            inp_id = await inp.get_attribute("id") or ""
            inp_class = await inp.get_attribute("class") or ""
            has_iti = "iti" in inp_id.lower() or "iti" in inp_class.lower()
            logger.info(f"  [{i}] ID: {inp_id}, Has ITI: {has_iti}")
        
        await browser.close()

asyncio.run(debug())

"""Check what options are available in the 'referred' React-Select dropdown."""
import asyncio
import json
import sys
import logging
from playwright.async_api import async_playwright

sys.path.insert(0, '.')

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("check_options")

async def check_options():
    with open('greenhouse_matched_jobs.json') as f:
        jobs = json.load(f)['matched_jobs']
    
    embed_url = "https://job-boards.greenhouse.io/embed/job_app?for=coinbase&token=8054153"
    logger.info(f"Loading: {embed_url}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        await page.goto(embed_url, wait_until='domcontentloaded')
        await asyncio.sleep(2)
        
        # Click apply
        apply_btn = page.locator("button:has-text('Apply')")
        if await apply_btn.count() > 0:
            await apply_btn.click()
            await asyncio.sleep(3)
        
        # Find the referred field
        referred_input = page.locator("#question_68017438").first
        if await referred_input.count() > 0:
            logger.info("✓ Found referred field (question_68017438)")
            
            # Scroll into view
            await referred_input.scroll_into_view_if_needed()
            await asyncio.sleep(1)
            
            # Click to open dropdown
            await referred_input.click()
            await asyncio.sleep(1)
            
            # Get all options that appear
            logger.info("Looking for dropdown options...")
            
            # Try multiple selectors for React-Select options
            selectors = [
                "div[id*='-option-']",
                "div[class*='select__option']",
                "[role='option']",
                "div[class*='option']:not([class*='menu'])",
                "li[class*='option']",
            ]
            
            options_found = False
            for selector in selectors:
                opts = page.locator(selector)
                count = await opts.count()
                if count > 0:
                    logger.info(f"\n  Selector '{selector}' found {count} option(s):")
                    for i in range(count):
                        opt = opts.nth(i)
                        if await opt.is_visible():
                            text = await opt.inner_text()
                            logger.info(f"    [{i}] {text}")
                            options_found = True
            
            if not options_found:
                logger.info("  No options found with any selector!")
                # Try typing to search
                await referred_input.type("No")
                await asyncio.sleep(1)
                
                logger.info("Trying again after typing 'No'...")
                for selector in selectors:
                    opts = page.locator(selector)
                    count = await opts.count()
                    if count > 0:
                        logger.info(f"  Selector '{selector}' found {count} option(s):")
                        for i in range(count):
                            opt = opts.nth(i)
                            text = await opt.inner_text()
                            logger.info(f"    [{i}] {text}")
            
            # Take screenshot
            await page.screenshot(path="logs/referred_field_screenshot.png")
            logger.info("Screenshot saved to logs/referred_field_screenshot.png")
        
        else:
            logger.info("✗ Could not find referred field!")
        
        await browser.close()

asyncio.run(check_options())

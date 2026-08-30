import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        print('--- SpaceX ---')
        await page.goto('https://job-boards.greenhouse.io/embed/job_app?for=spacex&token=8563110002')
        await page.wait_for_timeout(3000)
        # Find the legally authorized input
        el = page.locator('label', has_text='legally authorized').first
        if await el.count() > 0:
            parent = el.locator('xpath=following-sibling::div[contains(@class, "select-shell")]').first
            control = parent.locator('.select__control').first
            await control.click(force=True)
            await page.wait_for_timeout(1000)
            options = await page.locator('[id*="option"]').all_inner_texts()
            for opt in options:
                print(' -', opt)
        else:
            print('Could not find SpaceX element')
                
        print('\n--- Datadog ---')
        await page.goto('https://job-boards.greenhouse.io/embed/job_app?for=datadog&token=3851927')
        await page.wait_for_timeout(3000)
        el = page.locator('label', has_text='cities are you available').first
        if await el.count() > 0:
            parent = el.locator('xpath=following-sibling::div[contains(@class, "select-shell")]').first
            control = parent.locator('.select__control').first
            await control.click(force=True)
            await page.wait_for_timeout(1000)
            options = await page.locator('[id*="option"]').all_inner_texts()
            for opt in options:
                print(' -', opt)
        else:
            print('Could not find Datadog element')
                
        await browser.close()

asyncio.run(run())

"""
Quick test to inspect LinkedIn login page DOM and find correct selectors.
"""
import asyncio, sys
sys.path.insert(0, r'C:\Users\HP\OneDrive\Desktop\auto_job_apply\auto_apply_system')
import os
os.chdir(r'C:\Users\HP\OneDrive\Desktop\auto_job_apply\auto_apply_system')

async def inspect_linkedin_login():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # visible so we can see
        page = await browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
        await page.goto("https://www.linkedin.com/login", timeout=30000)
        await page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(3)

        # Get all input elements with their attributes
        inputs = await page.evaluate("""
            () => {
                return Array.from(document.querySelectorAll('input')).map(el => ({
                    id: el.id,
                    name: el.name,
                    type: el.type,
                    placeholder: el.placeholder,
                    autocomplete: el.autocomplete,
                    class: el.className.substring(0, 80)
                }));
            }
        """)
        print("=== All INPUT elements on LinkedIn login page ===")
        for inp in inputs:
            print(f"  id={repr(inp['id'])} name={repr(inp['name'])} type={repr(inp['type'])} placeholder={repr(inp['placeholder'])} autocomplete={repr(inp['autocomplete'])}")

        # Test each selector
        test_selectors = [
            "input[name='session_key']",
            "input[autocomplete='username']",
            "#username",
            "input[type='email']",
            "input[type='text']",
            "#organic-div input",
            "form input:first-of-type",
            ".login__form input:first-child",
        ]
        print("\n=== Selector visibility test ===")
        for sel in test_selectors:
            try:
                el = page.locator(sel).first
                visible = await el.is_visible(timeout=2000)
                print(f"  {repr(sel):55s} -> visible={visible}")
            except Exception as e:
                print(f"  {repr(sel):55s} -> ERROR: {e}")

        await browser.close()

asyncio.run(inspect_linkedin_login())

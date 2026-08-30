"""
test_login.py — Test LinkedIn login in isolation.
Run: python test_login.py
"""
import asyncio, sys, os
sys.path.insert(0, r'C:\Users\HP\OneDrive\Desktop\auto_job_apply\auto_apply_system')
os.chdir(r'C:\Users\HP\OneDrive\Desktop\auto_job_apply\auto_apply_system')

async def main():
    from applier.linkedin_applier import LinkedInApplier
    print("Testing LinkedIn login...")
    applier = LinkedInApplier()
    result = await applier.login()
    print(f"\nLogin result: {result}")
    if result:
        page = await applier._get_page()
        print(f"Current URL: {page.url}")
        print(f"Title: {await page.title()}")
    else:
        print("Login FAILED")
    # Keep browser open for 5s to inspect
    await asyncio.sleep(5)
    from applier.base_applier import _browser_manager
    if _browser_manager:
        await _browser_manager.stop()

asyncio.run(main())

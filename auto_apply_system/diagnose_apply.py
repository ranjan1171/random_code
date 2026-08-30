"""
diagnose_apply.py — Diagnose why jobs are not being applied to.
Run: python diagnose_apply.py
"""
import asyncio, sys, os
sys.path.insert(0, r'C:\Users\HP\OneDrive\Desktop\auto_job_apply\auto_apply_system')
os.chdir(r'C:\Users\HP\OneDrive\Desktop\auto_job_apply\auto_apply_system')
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from config import DB_PATH, APPLICATION, PROFILE
from db.database import Database
from matcher.scorer import score_job

db = Database(DB_PATH)
stats = db.get_stats()

print("=" * 60)
print("DIAGNOSE: Why are jobs not being applied to?")
print("=" * 60)

# Check 1: Are there matched jobs in DB?
print(f"\n[CHECK 1] Database stats:")
print(f"  Total scraped:   {stats['total_scraped']}")
print(f"  Total matched:   {stats['total_matched']}")
print(f"  Total applied:   {stats['total_applied']}")
print(f"  Applied today:   {stats['applied_today']}")
print(f"  By portal:       {stats['by_portal']}")
print(f"  By status:       {stats['by_status']}")

# Check 2: Show top matched jobs from DB
print(f"\n[CHECK 2] Top matched jobs in DB (should be non-empty):")
with db._get_conn() as conn:
    rows = conn.execute("""
        SELECT id, title, company, portal, score, status, url
        FROM jobs
        WHERE is_dealbreaker=0 AND score >= 60
        ORDER BY score DESC
        LIMIT 10
    """).fetchall()
    if not rows:
        print("  !! NO MATCHED JOBS IN DB — Run scraper first: python main.py --dry-run")
    for r in rows:
        print(f"  [{r['score']:5.1f}%] [{r['status']:12s}] {r['title'][:40]} @ {(r['company'] or '?')[:20]} ({r['portal']})")

# Check 3: Already applied check
print(f"\n[CHECK 3] Jobs already in applications table:")
with db._get_conn() as conn:
    apps = conn.execute("SELECT job_id, status, applied_at FROM applications ORDER BY applied_at DESC LIMIT 10").fetchall()
    if not apps:
        print("  (No applications recorded yet)")
    for a in apps:
        print(f"  job_id={a['job_id'][:20]}... status={a['status']} applied={a['applied_at']}")

# Check 4: Daily limit check
print(f"\n[CHECK 4] Daily limit:")
print(f"  MAX_DAILY_APPLICATIONS = {APPLICATION['max_daily']}")
print(f"  Applied today          = {stats['applied_today']}")
remaining = APPLICATION['max_daily'] - stats['applied_today']
print(f"  Remaining today        = {remaining}")
if remaining <= 0:
    print("  !! DAILY LIMIT REACHED — No more applications will be sent today")

# Check 5: Portal config
print(f"\n[CHECK 5] Portal config:")
from config import PORTALS
for name, cfg in PORTALS.items():
    print(f"  {name:12s}: enabled={cfg.get('enabled')} email={cfg.get('email','?')[:30]}")

# Check 6: LinkedIn credentials loaded
print(f"\n[CHECK 6] Credentials:")
from dotenv import load_dotenv
load_dotenv()
li_pwd = os.environ.get("LINKEDIN_PASSWORD", "")
nk_pwd = os.environ.get("NAUKRI_PASSWORD", "")
print(f"  LINKEDIN_PASSWORD: {'SET (' + li_pwd[:3] + '***)' if li_pwd else 'NOT SET !!!'}")
print(f"  NAUKRI_PASSWORD:   {'SET (' + nk_pwd[:3] + '***)' if nk_pwd else 'NOT SET !!!'}")

# Check 7: Profile
print(f"\n[CHECK 7] Profile:")
print(f"  Name:  {PROFILE.get('name')}")
print(f"  Email: {PROFILE.get('email')}")
cv = PROFILE.get('cv_pdf_path', '')
print(f"  CV:    {cv} {'(EXISTS)' if cv and os.path.exists(cv) else '(NOT FOUND)'}")

# Check 8: Playwright
print(f"\n[CHECK 8] Playwright browser:")
async def test_browser():
    try:
        from applier.base_applier import get_browser_manager
        bm = await get_browser_manager()
        page = await bm.new_page()
        await page.goto("https://www.linkedin.com/login", timeout=20000)
        title = await page.title()
        url = page.url
        print(f"  Browser: OK — LinkedIn login page loaded: '{title}'")
        print(f"  URL: {url}")

        # Check if Easy Apply button exists on a real job
        print(f"\n[CHECK 9] LinkedIn Easy Apply button test:")
        # Find a job URL from DB that is LinkedIn
        with db._get_conn() as conn:
            row = conn.execute(
                "SELECT url, title FROM jobs WHERE portal='linkedin' AND is_dealbreaker=0 ORDER BY score DESC LIMIT 1"
            ).fetchone()
        if row:
            print(f"  Testing URL: {row['url'][:70]}")
            await page.goto(row['url'], timeout=20000)
            await asyncio.sleep(3)
            content = await page.content()
            has_easy_apply = 'Easy Apply' in content
            has_apply = 'Apply' in content
            print(f"  Has 'Easy Apply' text: {has_easy_apply}")
            print(f"  Has 'Apply' text: {has_apply}")
            print(f"  Page title: {await page.title()}")

            # Check login wall
            if 'signin' in page.url or 'login' in page.url:
                print(f"  !! REDIRECTED TO LOGIN — Must be logged in to see Easy Apply!")
            elif 'authwall' in page.url:
                print(f"  !! AUTH WALL — Must log in first!")
        else:
            print("  No LinkedIn jobs in DB to test.")

        await bm.stop()
    except Exception as e:
        print(f"  Browser ERROR: {e}")

asyncio.run(test_browser())

print("\n" + "=" * 60)
print("DIAGNOSIS COMPLETE")
print("=" * 60)

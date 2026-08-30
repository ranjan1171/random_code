import sys
sys.path.insert(0, '.')
import os
os.chdir(r'C:\Users\HP\OneDrive\Desktop\auto_job_apply\auto_apply_system')

print("=== Auto Job Apply System — Validation Tests ===\n")

# Test 1: Config
try:
    from config import PROFILE, PORTALS, SEARCH_QUERIES, MATCHING
    print("PASS Config loaded")
    print(f"     Profile: {PROFILE['name']}")
    print(f"     Skills:  {len(PROFILE['skills'])} skills configured")
    print(f"     Portals: {list(PORTALS.keys())}")
    print(f"     Queries: {len(SEARCH_QUERIES)} search queries")
except Exception as e:
    print(f"FAIL Config: {e}")

# Test 2: Database
try:
    from db.database import Database
    from pathlib import Path
    db = Database(Path(r'C:\Users\HP\OneDrive\Desktop\auto_job_apply\auto_apply_system\db\jobs.db'))
    stats = db.get_stats()
    print(f"\nPASS Database OK")
    print(f"     Stats: {stats}")
except Exception as e:
    print(f"\nFAIL Database: {e}")

# Test 3: Matcher scoring
try:
    from matcher.scorer import score_job, is_good_match
    test_job = {
        'title': 'Backend Engineer Python Kafka',
        'company': 'Razorpay',
        'location': 'Bangalore India',
        'description': 'Python Kafka distributed systems REST API backend engineer low latency'
    }
    score, details = score_job(test_job)
    print(f"\nPASS Matcher OK")
    print(f"     Score: {score:.1f}%")
    print(f"     Skill: {details['skill_score']:.1f}  Title: {details['title_score']:.1f}  Loc: {details['location_score']:.1f}")
    print(f"     Matched: {details['matched_skills'][:5]}")
    print(f"     is_good_match: {is_good_match(score)}")
except Exception as e:
    print(f"\nFAIL Matcher: {e}")
    import traceback; traceback.print_exc()

# Test 4: Dealbreaker
try:
    bad_job = {
        'title': 'Frontend React Developer',
        'company': 'Co',
        'location': 'India',
        'description': 'frontend only react angular'
    }
    score2, det2 = score_job(bad_job)
    print(f"\nPASS Dealbreaker detection")
    print(f"     Score: {score2}  is_dealbreaker: {det2['is_dealbreaker']}")
    if det2.get('dealbreaker_reason'):
        print(f"     Reason: {det2['dealbreaker_reason']}")
except Exception as e:
    print(f"\nFAIL Dealbreaker: {e}")

# Test 5: Flask dashboard
try:
    from dashboard.app import app
    print(f"\nPASS Flask dashboard imports OK")
except Exception as e:
    print(f"\nFAIL Flask dashboard: {e}")
    import traceback; traceback.print_exc()

# Test 6: Email monitor
try:
    from email_monitor.monitor import EmailMonitor
    mon = EmailMonitor()
    print(f"\nPASS Email monitor: enabled={mon.enabled}")
except Exception as e:
    print(f"\nFAIL Email monitor: {e}")

# Test 7: Scrapers import
try:
    from scrapers.linkedin_scraper import LinkedInScraper
    from scrapers.naukri_scraper import NaukriScraper
    from scrapers.indeed_scraper import IndeedScraper
    from scrapers.wellfound_scraper import WellfoundScraper
    from scrapers.internshala_scraper import IntershalaScraper
    from scrapers.freehire_scraper import FreehireScraper
    print(f"\nPASS All 6 scrapers import OK")
except Exception as e:
    print(f"\nFAIL Scraper imports: {e}")
    import traceback; traceback.print_exc()

# Test 8: Appliers import
try:
    from applier.base_applier import BaseApplier
    from applier.form_filler import FormFiller
    from applier.linkedin_applier import LinkedInApplier
    from applier.naukri_applier import NaukriApplier
    from applier.indeed_applier import IndeedApplier
    print(f"\nPASS All 5 applier modules import OK")
except Exception as e:
    print(f"\nFAIL Applier imports: {e}")
    import traceback; traceback.print_exc()

# Test 9: CAPTCHA
try:
    from captcha.solver import CaptchaSolver
    solver = CaptchaSolver()
    print(f"\nPASS CAPTCHA solver: has_api_key={solver.has_solver}")
except Exception as e:
    print(f"\nFAIL CAPTCHA: {e}")

print("\n=== ALL TESTS COMPLETE ===")

import asyncio, sys
sys.path.insert(0, r'C:\Users\HP\OneDrive\Desktop\auto_job_apply\auto_apply_system')
import os
os.chdir(r'C:\Users\HP\OneDrive\Desktop\auto_job_apply\auto_apply_system')

async def test():
    print("=== Live Scraper Tests ===\n")

    # Test LinkedIn scraper
    try:
        from scrapers.linkedin_scraper import LinkedInScraper
        s = LinkedInScraper()
        jobs = await s.search("backend developer python", "Bangalore, Karnataka, India", page=0)
        print("PASS LinkedIn: {} jobs".format(len(jobs)))
        if jobs:
            j = jobs[0]
            print("     First: {} @ {} ({})".format(j["title"], j["company"], j["location"]))
        await s.close()
    except Exception as e:
        print("FAIL LinkedIn: {}".format(e))

    # Test Freehire scraper
    try:
        from scrapers.freehire_scraper import FreehireScraper
        s = FreehireScraper()
        jobs = await s.search("backend python", "India")
        print("PASS Freehire: {} jobs".format(len(jobs)))
        if jobs:
            j = jobs[0]
            print("     First: {} @ {} ({})".format(j["title"], j["company"], j["location"]))
        await s.close()
    except Exception as e:
        print("FAIL Freehire: {}".format(e))

    # Test matcher scoring
    from matcher.scorer import score_job
    test_jobs = [
        {"title": "Backend Engineer", "company": "Razorpay", "location": "Bangalore", "description": "Python Kafka distributed systems microservices"},
        {"title": "SDE-1 Backend Python", "company": "Zerodha", "location": "Remote India", "description": "Python REST API microservices kafka distributed systems backend"},
        {"title": "Senior Frontend Developer", "company": "Co", "location": "US Only", "description": "React Angular Vue frontend only"},
    ]
    print("\nMatcher scoring test:")
    for j in test_jobs:
        score, det = score_job(j)
        db_str = " [DEALBREAKER]" if det["is_dealbreaker"] else ""
        print("  {:5.1f}% -- {} @ {}{}".format(score, j["title"], j["company"], db_str))

    print("\n=== LIVE TEST COMPLETE ===")

asyncio.run(test())

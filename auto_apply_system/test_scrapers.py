import asyncio, sys
sys.path.insert(0, r'C:\Users\HP\OneDrive\Desktop\auto_job_apply\auto_apply_system')
import os
os.chdir(r'C:\Users\HP\OneDrive\Desktop\auto_job_apply\auto_apply_system')

async def test_all_scrapers():
    from scrapers.linkedin_scraper import LinkedInScraper
    from scrapers.freehire_scraper import FreehireScraper
    from scrapers.internshala_scraper import IntershalaScraper
    from scrapers.naukri_scraper import NaukriScraper
    from scrapers.indeed_scraper import IndeedScraper
    from scrapers.wellfound_scraper import WellfoundScraper

    scrapers = [
        ("LinkedIn", LinkedInScraper()),
        ("Freehire", FreehireScraper()),
        ("Internshala", IntershalaScraper()),
        ("Naukri", NaukriScraper()),
        ("Indeed", IndeedScraper()),
        ("Wellfound", WellfoundScraper()),
    ]

    for name, s in scrapers:
        try:
            jobs = await s.search("backend engineer python", "Bangalore")
            print("[{:10s}] -> {} jobs scraped".format(name, len(jobs)))
            if jobs:
                print("   Sample: {} @ {}".format(jobs[0]["title"], jobs[0]["company"]))
            await s.close()
        except Exception as e:
            print("[{:10s}] -> ERROR: {}".format(name, e))

asyncio.run(test_all_scrapers())

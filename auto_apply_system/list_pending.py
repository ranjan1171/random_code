import json

with open("greenhouse_matched_jobs.json", "r", encoding="utf-8") as f:
    data = json.load(f)

pending = [j for j in data.get("matched_jobs", []) if not j.get("applied")]

print(f"\n======================================================================")
print(f"PENDING MATCHED ACTIVE ENGINEERING JOBS ({len(pending)} Total)")
print(f"======================================================================")
for idx, j in enumerate(pending, 1):
    score = j.get("score", 0)
    title = j.get("title", "")
    company = j.get("company", "")
    location = j.get("location", "")
    url = j.get("url", "")
    print(f"{idx:2d}. [{score:5.1f}%] {title:<45} @ {company:<20} ({location})")
    print(f"    URL: {url}")
    print("-" * 70)

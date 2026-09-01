import json
import sqlite3
from collections import Counter

with open("greenhouse_matched_jobs.json", "r", encoding="utf-8") as f:
    data = json.load(f)

jobs = data.get("matched_jobs", data) if isinstance(data, dict) else data

# Connect to DB to check applied jobs
conn = sqlite3.connect("db/jobs.db")
c = conn.cursor()
applied_ids = {row[0] for row in c.execute("SELECT job_id FROM applications WHERE status='applied'").fetchall()}
conn.close()

print(f"Total jobs in JSON: {len(jobs)}")
print(f"Total applied jobs in DB: {len(applied_ids)}")

companies = Counter(j.get("company", "Unknown") for j in jobs)
print("\nTop 15 Companies in JSON:")
for comp, cnt in companies.most_common(15):
    print(f"  {comp}: {cnt} jobs")

unapplied = [j for j in jobs if str(j.get("id")) not in applied_ids and not j.get("applied")]
print(f"\nTotal unapplied jobs: {len(unapplied)}")

unapplied_companies = Counter(j.get("company", "Unknown") for j in unapplied)
print("\nUnapplied Jobs by Company:")
for comp, cnt in unapplied_companies.most_common(15):
    print(f"  {comp}: {cnt} jobs")

# Pick 5 diverse unapplied jobs from different companies
diverse_5 = []
seen_comps = set()
for j in unapplied:
    comp = j.get("company", "Unknown")
    if comp not in seen_comps and comp.lower() != "coinbase":
        diverse_5.append(j)
        seen_comps.add(comp)
        if len(diverse_5) == 5:
            break

# If less than 5 non-Coinbase, fill with any diverse unapplied
if len(diverse_5) < 5:
    for j in unapplied:
        if j not in diverse_5:
            diverse_5.append(j)
            if len(diverse_5) == 5:
                break

print("\nSelected 5 Diverse Unapplied Jobs:")
for i, j in enumerate(diverse_5, 1):
    print(f"  {i}. [{j.get('company')}] {j.get('title')} (Score: {j.get('match_score', 0)}%)")
    print(f"     ID: {j.get('id')}")
    print(f"     URL: {j.get('url')}")

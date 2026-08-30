import json
from config import DB_PATH
from db.database import Database
from matcher.scorer import score_job

with open('c:/Users/HP/OneDrive/Desktop/auto_job_apply/auto_apply_system/greenhouse_matched_jobs.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

matched = data.get('matched_jobs', [])
clean_jobs = []
for j in matched:
    score, details = score_job(j)
    if not details.get('is_dealbreaker', False) and score >= 50:
        j['score'] = score
        clean_jobs.append(j)

data['matched_jobs'] = clean_jobs
with open('c:/Users/HP/OneDrive/Desktop/auto_job_apply/auto_apply_system/greenhouse_matched_jobs.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)

print(f"=== 🎯 PURE SOFTWARE ENGINEERING QUEUE ({len(clean_jobs)} JOBS) ===")
for i, j in enumerate(clean_jobs, 1):
    status = "APPLIED" if j.get("applied") else "PENDING"
    print(f"{i:2d}. [{status}] [{j.get('score', 0):.1f}%] {j.get('title')} @ {j.get('company')} ({j.get('location')})")

db = Database(DB_PATH)
stats = db.get_stats()
print("\n=== DATABASE STATS ===")
print(json.dumps(stats, indent=2))

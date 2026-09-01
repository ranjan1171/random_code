import json
with open('greenhouse_matched_jobs.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
jobs = data.get('matched_jobs', [])
applied = [j for j in jobs if j.get('applied') and j.get('success')]
unapplied = [j for j in jobs if not (j.get('applied') and j.get('success'))]
print(f"Total jobs: {len(jobs)} | Successfully applied: {len(applied)} | Pending: {len(unapplied)}")
print("\n--- NEXT 5 JOBS TO PROCESS ---")
for i, j in enumerate(unapplied[:5], 1):
    print(f"[{i}] {j.get('title')} @ {j.get('company')}")
    print(f"    URL: {j.get('url')}")
    print(f"    gh_jid: {j.get('gh_jid')}")

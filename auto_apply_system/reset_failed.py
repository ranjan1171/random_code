import sys, os, json
sys.path.insert(0, r'C:\Users\HP\OneDrive\Desktop\auto_job_apply\auto_apply_system')
os.chdir(r'C:\Users\HP\OneDrive\Desktop\auto_job_apply\auto_apply_system')
from config import DB_PATH
from db.database import Database

# 1. Reset in SQLite DB
db = Database(DB_PATH)
with db._get_conn() as conn:
    count = conn.execute("DELETE FROM applications WHERE status='failed'").rowcount
    conn.commit()
    print("Deleted {} failed records from applications table".format(count))

# 2. Reset in greenhouse_matched_jobs.json
json_path = 'greenhouse_matched_jobs.json'
if os.path.exists(json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    reset_count = 0
    for j in data.get('matched_jobs', []):
        if j.get('applied') and j.get('failure_reason') and not j.get('success'):
            j['applied'] = False
            j.pop('processed', None)
            j.pop('failed_at', None)
            j.pop('failure_reason', None)
            reset_count += 1
            
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    print(f"Reset {reset_count} failed jobs in {json_path} back to unapplied (ready to retry)")

print("Done.")


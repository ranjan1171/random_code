import sys, os
sys.path.insert(0, r'C:\Users\HP\OneDrive\Desktop\auto_job_apply\auto_apply_system')
os.chdir(r'C:\Users\HP\OneDrive\Desktop\auto_job_apply\auto_apply_system')
from config import DB_PATH
from db.database import Database

db = Database(DB_PATH)
with db._get_conn() as conn:
    count = conn.execute("UPDATE jobs SET status='scraped' WHERE status='failed'").rowcount
    conn.commit()
    print("Reset {} failed jobs back to 'scraped' (ready to retry)".format(count))
    rows = conn.execute("SELECT status, COUNT(*) as n FROM jobs GROUP BY status").fetchall()
    for r in rows:
        print("  status={} count={}".format(r[0], r[1]))
print("Done.")

import sqlite3
from pathlib import Path

db_path = Path("db/jobs.db")
if db_path.exists():
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    
    cur.execute("DELETE FROM jobs WHERE lower(company) LIKE '%ubiquiti%' OR lower(company) LIKE '%anduril%' OR lower(url) LIKE '%ubiquiti%' OR lower(url) LIKE '%anduril%'")
    deleted_jobs = cur.rowcount
    
    cur.execute("DELETE FROM applications WHERE lower(application_url) LIKE '%ubiquiti%' OR lower(application_url) LIKE '%anduril%'")
    deleted_apps = cur.rowcount
    
    conn.commit()
    
    total_jobs = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    total_apps = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    
    print(f"SUCCESS: Deleted {deleted_jobs} jobs and {deleted_apps} applications from DB.")
    print(f"Remaining DB State: {total_jobs} total jobs, {total_apps} total applications.")
    conn.close()

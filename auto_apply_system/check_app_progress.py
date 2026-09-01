#!/usr/bin/env python
"""Quick check of application progress."""

from db.database import Database
from config import DB_PATH

db = Database(DB_PATH)
stats = db.get_stats()

print("\n" + "="*60)
print("  APPLICATION PROGRESS")
print("="*60)
print(f"Total Jobs Scraped:    {stats['total_scraped']}")
print(f"Total Applications:    {stats['total_applied']}")
print(f"Applied Today:         {stats['applied_today']}")
print("="*60 + "\n")

print("RECENT APPLICATIONS (Last 15):")
with db._get_conn() as conn:
    apps = conn.execute("""
        SELECT a.id, a.status, a.applied_at, j.title 
        FROM applications a
        JOIN jobs j ON a.job_id = j.id
        ORDER BY a.applied_at DESC
        LIMIT 15
    """).fetchall()
    for app in apps:
        title = app["title"][:45]
        status = app["status"][:10]
        when = app["applied_at"][-8:] if app["applied_at"] else "N/A"
        print(f"  [{status:10}] {title:45} @ {when}")

print("\n")

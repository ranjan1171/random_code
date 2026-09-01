#!/usr/bin/env python
"""Check filter and success stats."""

from db.database import Database
from config import DB_PATH

db = Database(DB_PATH)
with db._get_conn() as conn:
    # Check dealbreaker filtering
    total = conn.execute('SELECT COUNT(*) as c FROM jobs').fetchone()['c']
    dealbreak = conn.execute('SELECT COUNT(*) as c FROM jobs WHERE is_dealbreaker=1').fetchone()['c']
    
    # Check failed applications
    failed = conn.execute('''
        SELECT COUNT(*) as c FROM applications WHERE status="failed"
    ''').fetchone()['c']
    success = conn.execute('''
        SELECT COUNT(*) as c FROM applications WHERE status="applied"
    ''').fetchone()['c']
    
    print("\n" + "="*60)
    print("  FILTER & SUCCESS ANALYSIS")
    print("="*60)
    print(f"Total Jobs Scraped:       {total}")
    print(f"Dealbreakers Filtered:    {dealbreak}")
    print(f"Good Jobs in DB:          {total - dealbreak}")
    
    print(f"\nApplications:")
    print(f"  Successfully Applied:   {success}")
    print(f"  Failed/Blocked:         {failed}")
    if (success + failed) > 0:
        rate = success / (success + failed) * 100
        print(f"  Success Rate:           {rate:.1f}%")
    print("="*60 + "\n")

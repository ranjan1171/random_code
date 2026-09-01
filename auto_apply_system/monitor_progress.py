#!/usr/bin/env python
"""Monitor application progress in real-time."""

import time
import sqlite3
from config import DB_PATH

print("\n" + "="*60)
print("  MONITORING APPLICATION PROGRESS")
print("="*60)

for attempt in range(12):  # 120 seconds total
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        
        success = conn.execute("SELECT COUNT(*) as c FROM applications WHERE status='applied'").fetchone()['c']
        failed = conn.execute("SELECT COUNT(*) as c FROM applications WHERE status='failed'").fetchone()['c']
        total = success + failed
        
        if total > 0:
            rate = success / total * 100
            print(f"[{time.strftime('%H:%M:%S')}] Applied: {success:3d}  |  Failed: {failed:3d}  |  Rate: {rate:5.1f}%")
        else:
            print(f"[{time.strftime('%H:%M:%S')}] No applications yet")
        
        conn.close()
        
        if attempt < 11:
            time.sleep(10)
    except Exception as e:
        print(f"Error: {e}")
        break

print("="*60 + "\n")

import json
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).parent
json_path = BASE_DIR / "greenhouse_matched_jobs.json"
db_path = BASE_DIR / "db" / "jobs.db"

if json_path.exists():
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    jobs = data.get("matched_jobs", [])
    
    # Check DB for processed jobs
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    processed_job_ids = set()
    try:
        rows = cursor.execute("SELECT job_id FROM applications").fetchall()
        processed_job_ids = {r[0] for r in rows}
    except Exception as e:
        print("DB check warning:", e)
    finally:
        conn.close()

    updated = 0
    clean_jobs = []
    for j in jobs:
        if j.get("id") in processed_job_ids or j.get("applied") or j.get("processed"):
            j["applied"] = True
            updated += 1
        clean_jobs.append(j)

    data["matched_jobs"] = clean_jobs
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"✅ Marked {updated} already-processed/expired jobs as applied in JSON file.")

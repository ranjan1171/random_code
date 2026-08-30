import json
from pathlib import Path
from matcher.scorer import score_job

json_path = Path("greenhouse_matched_jobs.json")
if json_path.exists():
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    clean_jobs = []
    removed = 0

    for job in data.get("matched_jobs", []):
        company = job.get("company", "").lower()
        title = job.get("title", "").lower()
        url = job.get("url", "").lower()

        # Exclude Ubiquiti and Anduril
        if "ubiquiti" in company or "anduril" in company or "ubiquiti" in url or "anduril" in url:
            removed += 1
            continue

        # Exclude non-engineering titles explicitly
        if any(bad_title in title.lower() for bad_title in [
            "customer success", "account associate", "sales representative", "operations associate",
            "investment analyst", "av production", "quality inspector", "market research",
            "product operations", "designer advocate", "product designer", "short-form video"
        ]):
            removed += 1
            continue

        # Exclude non-ASCII / foreign language titles
        try:
            title.encode('ascii')
        except UnicodeEncodeError:
            removed += 1
            continue

        # Score check for non-engineering dealbreakers
        score, details = score_job(job)
        if details.get("is_dealbreaker"):
            removed += 1
            continue

        clean_jobs.append(job)

    data["matched_jobs"] = clean_jobs
    data["total_matched_pending"] = len([j for j in clean_jobs if not j.get("applied")])

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"Cleaned JSON: Removed {removed} jobs (Ubiquiti, Anduril & non-engineering dealbreakers).")
    print(f"Remaining pending active jobs: {data['total_matched_pending']}")

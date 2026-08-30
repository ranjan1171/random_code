"""
activity_logger.py — Writes live activity data (current job, Q&A answers)
to logs/live_activity.json for the dashboard to read and display.
"""

import json
import os
import time
from pathlib import Path

_ACTIVITY_FILE = Path("logs/live_activity.json")
_MAX_ENTRIES = 100


def _read():
    try:
        if _ACTIVITY_FILE.exists():
            return json.loads(_ACTIVITY_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"current_job": None, "entries": []}


def _write(data):
    try:
        os.makedirs("logs", exist_ok=True)
        # Keep only last N entries
        if len(data.get("entries", [])) > _MAX_ENTRIES:
            data["entries"] = data["entries"][-_MAX_ENTRIES:]
        _ACTIVITY_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


_TXT_SUMMARY_FILE = Path("logs/application_qa_summary.txt")


def _append_txt(text: str):
    try:
        os.makedirs("logs", exist_ok=True)
        with open(_TXT_SUMMARY_FILE, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception:
        pass


def log_apply_start(title: str, company: str, url: str = ""):
    """Called when the bot starts applying to a new job."""
    data = _read()
    data["current_job"] = {
        "title": title,
        "company": company,
        "url": url,
        "status": "Filling form...",
    }
    data["entries"].append({
        "type": "apply_start",
        "message": f"Applying to: {title} @ {company}",
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    _write(data)

    # Append to TXT summary log file
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    header = (
        f"\n======================================================================\n"
        f"🎯 JOB APPLICATION STARTED: {title} @ {company}\n"
        f"   Time: {timestamp}\n"
        f"   URL:  {url}\n"
        f"----------------------------------------------------------------------"
    )
    _append_txt(header)


def log_field_fill(question: str, answer: str, method: str = ""):
    """Called when a form field is filled."""
    data = _read()
    if data.get("current_job"):
        data["current_job"]["status"] = f"Answering: {question[:40]}..."
    data["entries"].append({
        "type": "field_fill",
        "question": question,
        "answer": answer,
        "method": method,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    _write(data)

    # Append to TXT summary log file
    entry = f"  • [Text Input] Q: '{question}' -> A: '{answer}'"
    _append_txt(entry)


def log_dropdown(question: str, selected: str, method: str = ""):
    """Called when a dropdown option is selected."""
    data = _read()
    if data.get("current_job"):
        data["current_job"]["status"] = f"Selected: {selected[:30]}"
    data["entries"].append({
        "type": "dropdown",
        "question": question,
        "answer": selected,
        "method": method,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    _write(data)

    # Append to TXT summary log file
    entry = f"  • [Dropdown  ] Q: '{question}' -> Selected: '{selected}'"
    _append_txt(entry)


def log_apply_success(title: str, company: str):
    """Called when application is submitted successfully."""
    data = _read()
    data["current_job"] = None
    data["entries"].append({
        "type": "apply_success",
        "message": f"✅ Applied successfully: {title} @ {company}",
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    _write(data)

    footer = f"RESULT: ✅ APPLIED SUCCESSFULLY: {title} @ {company}\n======================================================================\n"
    _append_txt(footer)


def log_apply_fail(title: str, company: str, reason: str = ""):
    """Called when application fails."""
    data = _read()
    data["current_job"] = None
    data["entries"].append({
        "type": "apply_fail",
        "message": f"❌ Failed: {title} @ {company}" + (f" — {reason}" if reason else ""),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    _write(data)

    footer = f"RESULT: ❌ FAILED: {title} @ {company} ({reason})\n======================================================================\n"
    _append_txt(footer)

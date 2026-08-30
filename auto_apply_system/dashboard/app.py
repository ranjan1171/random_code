"""
dashboard/app.py — Flask web dashboard for the Auto Job Apply System.
Provides real-time stats, application tracking, and system control.
"""

import json
import logging
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, jsonify, request
from flask_cors import CORS

from config import DB_PATH, DASHBOARD_PORT, PROFILE
from db.database import Database

logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)
app.secret_key = "auto-job-apply-secret-2024"

# Global references (set by main.py)
_db: Database = None
_orchestrator = None


def init_dashboard(db: Database, orchestrator=None):
    """Initialize dashboard with db and orchestrator references."""
    global _db, _orchestrator
    _db = db
    _orchestrator = orchestrator


def _get_db() -> Database:
    global _db
    if _db is None:
        _db = Database(DB_PATH)
    return _db


# ────────────────────────────────────────────────────────────
# Main dashboard page
# ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", profile=PROFILE)


# ────────────────────────────────────────────────────────────
# API: Stats
# ────────────────────────────────────────────────────────────

@app.route("/api/stats")
def get_stats():
    db = _get_db()
    stats = db.get_stats()
    return jsonify(stats)


# ────────────────────────────────────────────────────────────
# API: Jobs
# ────────────────────────────────────────────────────────────

@app.route("/api/jobs")
def get_jobs():
    db = _get_db()
    status = request.args.get("status")
    portal = request.args.get("portal")
    min_score = float(request.args.get("min_score", 0))
    limit = int(request.args.get("limit", 100))

    jobs = db.get_jobs(status=status, portal=portal, min_score=min_score, limit=limit)
    return jsonify(jobs)


@app.route("/api/jobs/<job_id>")
def get_job(job_id):
    db = _get_db()
    job = db.get_job(job_id)
    if job is None:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


# ────────────────────────────────────────────────────────────
# API: Applications
# ────────────────────────────────────────────────────────────

@app.route("/api/applications")
def get_applications():
    db = _get_db()
    limit = int(request.args.get("limit", 100))
    apps = db.get_applications(limit=limit)
    return jsonify(apps)


@app.route("/api/applications/<int:app_id>/status", methods=["PATCH"])
def update_application_status(app_id):
    db = _get_db()
    data = request.json or {}
    status = data.get("status", "")
    notes = data.get("notes", "")
    if not status:
        return jsonify({"error": "status required"}), 400
    db.update_application_status(app_id, status, notes)
    return jsonify({"ok": True})


# ────────────────────────────────────────────────────────────
# API: Emails
# ────────────────────────────────────────────────────────────

@app.route("/api/emails")
def get_emails():
    db = _get_db()
    limit = int(request.args.get("limit", 100))
    email_type = request.args.get("type", "").strip()
    search = request.args.get("search", "").strip()

    emails = db.get_emails(limit=limit)
    if email_type:
        emails = [e for e in emails if e.get("email_type") == email_type]
    if search:
        s = search.lower()
        emails = [
            e for e in emails
            if s in (e.get("subject") or "").lower() or s in (e.get("from_addr") or "").lower() or s in (e.get("body") or "").lower()
        ]
    return jsonify(emails)


@app.route("/api/emails/sync", methods=["POST"])
def sync_emails():
    try:
        from email_monitor.monitor import EmailMonitor
        db = _get_db()
        monitor = EmailMonitor(db)
        synced = monitor.sync_inbox(max_emails=100)
        return jsonify({"ok": True, "count": len(synced), "message": f"Synced {len(synced)} emails from Gmail"})
    except Exception as e:
        logger.error(f"[Dashboard] Email sync error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/emails/stats")
def email_stats():
    db = _get_db()
    with db._get_conn() as conn:
        rows = conn.execute("SELECT email_type, COUNT(*) as count FROM emails GROUP BY email_type").fetchall()
        by_type = {r["email_type"]: r["count"] for r in rows}
        total = conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    return jsonify({"total": total, "by_type": by_type})


# ────────────────────────────────────────────────────────────
# API: System Control
# ────────────────────────────────────────────────────────────

@app.route("/api/system/status")
def system_status():
    status = {
        "running": _orchestrator.is_running if _orchestrator else False,
        "db_path": str(DB_PATH),
        "timestamp": datetime.utcnow().isoformat(),
        "profile": PROFILE["name"],
    }
    return jsonify(status)


@app.route("/api/system/start", methods=["POST"])
def start_system():
    if _orchestrator:
        _orchestrator.start()
        return jsonify({"ok": True, "message": "System started"})
    return jsonify({"error": "No orchestrator connected"}), 500


@app.route("/api/system/stop", methods=["POST"])
def stop_system():
    if _orchestrator:
        _orchestrator.stop()
        return jsonify({"ok": True, "message": "System stopped"})
    return jsonify({"error": "No orchestrator connected"}), 500


@app.route("/api/system/dry-run", methods=["POST"])
def trigger_dry_run():
    if _orchestrator:
        threading.Thread(target=lambda: _orchestrator.run_once(dry_run=True), daemon=True).start()
        return jsonify({"ok": True, "message": "Dry run started"})
    return jsonify({"error": "No orchestrator connected"}), 500


@app.route("/api/system/run-now", methods=["POST"])
def trigger_run():
    if _orchestrator:
        threading.Thread(target=lambda: _orchestrator.run_once(dry_run=False), daemon=True).start()
        return jsonify({"ok": True, "message": "Run started"})
    return jsonify({"error": "No orchestrator connected"}), 500


# ────────────────────────────────────────────────────────────
# API: Logs (tail)
# ────────────────────────────────────────────────────────────

@app.route("/api/logs")
def get_logs():
    log_file = Path("logs/app.log")
    if not log_file.exists():
        return jsonify({"lines": []})
    lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    last_n = int(request.args.get("n", 200))
    return jsonify({"lines": lines[-last_n:]})


# ────────────────────────────────────────────────────────────
# API: Live Activity Feed
# ────────────────────────────────────────────────────────────

@app.route("/api/activity")
def get_activity():
    """Return live activity data: current job being applied + recent Q&A entries."""
    activity_file = Path("logs/live_activity.json")
    if not activity_file.exists():
        return jsonify({"current_job": None, "entries": []})
    try:
        data = json.loads(activity_file.read_text(encoding="utf-8", errors="replace"))
        return jsonify(data)
    except Exception:
        return jsonify({"current_job": None, "entries": []})


def run_dashboard(db: Database, orchestrator=None, port: int = None):
    """Start the Flask dashboard server."""
    init_dashboard(db, orchestrator)
    port = port or DASHBOARD_PORT
    logger.info(f"[Dashboard] Starting at http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)

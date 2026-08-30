"""
db/database.py — SQLite database layer for the Auto Job Apply System
Handles all storage: jobs scraped, applications sent, emails received.
"""

import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class Database:
    """Thread-safe SQLite wrapper for job application tracking."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self):
        """Create tables if they don't exist."""
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id          TEXT PRIMARY KEY,
                    portal      TEXT NOT NULL,
                    title       TEXT NOT NULL,
                    company     TEXT,
                    location    TEXT,
                    url         TEXT NOT NULL,
                    description TEXT,
                    score       REAL DEFAULT 0,
                    match_details TEXT,
                    is_dealbreaker INTEGER DEFAULT 0,
                    status      TEXT DEFAULT 'scraped',
                    scraped_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS applications (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id          TEXT NOT NULL REFERENCES jobs(id),
                    applied_at      TEXT NOT NULL,
                    status          TEXT DEFAULT 'applied',
                    portal          TEXT,
                    application_url TEXT,
                    cover_letter    TEXT,
                    cv_version      TEXT,
                    notes           TEXT,
                    updated_at      TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS emails (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    uid         TEXT UNIQUE,
                    from_addr   TEXT,
                    subject     TEXT,
                    body        TEXT,
                    email_type  TEXT,
                    job_id      TEXT REFERENCES jobs(id),
                    received_at TEXT NOT NULL,
                    processed   INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS run_stats (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_date    TEXT NOT NULL,
                    portal      TEXT,
                    jobs_scraped    INTEGER DEFAULT 0,
                    jobs_matched    INTEGER DEFAULT 0,
                    jobs_applied    INTEGER DEFAULT 0,
                    jobs_failed     INTEGER DEFAULT 0,
                    run_duration_s  REAL DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
                CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(score DESC);
                CREATE INDEX IF NOT EXISTS idx_jobs_portal ON jobs(portal);
                CREATE INDEX IF NOT EXISTS idx_apps_job ON applications(job_id);
            """)
        logger.info(f"Database initialized at {self.db_path}")

    # ─────────────────────── JOBS ────────────────────────────

    def upsert_job(self, job: Dict[str, Any]) -> bool:
        """Insert or update a job. Returns True if it's a new job."""
        now = datetime.utcnow().isoformat()
        existing = self.get_job(job["id"])

        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO jobs (id, portal, title, company, location, url,
                    description, score, match_details, is_dealbreaker, status,
                    scraped_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    score = excluded.score,
                    match_details = excluded.match_details,
                    is_dealbreaker = excluded.is_dealbreaker,
                    updated_at = excluded.updated_at
            """, (
                job["id"], job.get("portal", "unknown"),
                job.get("title", ""), job.get("company"),
                job.get("location"), job.get("url", ""),
                job.get("description"), job.get("score", 0),
                json.dumps(job.get("match_details", {})),
                1 if job.get("is_dealbreaker") else 0,
                job.get("status", "scraped"),
                job.get("scraped_at", now), now
            ))
        return existing is None

    def get_job(self, job_id: str) -> Optional[Dict]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            return dict(row) if row else None

    def get_jobs(self, status: Optional[str] = None, min_score: float = 0,
                 portal: Optional[str] = None, limit: int = 500) -> List[Dict]:
        query = "SELECT * FROM jobs WHERE score >= ?"
        params: list = [min_score]
        if status:
            query += " AND status=?"
            params.append(status)
        if portal:
            query += " AND portal=?"
            params.append(portal)
        query += " ORDER BY score DESC LIMIT ?"
        params.append(limit)
        with self._get_conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def update_job_status(self, job_id: str, status: str, notes: str = ""):
        now = datetime.utcnow().isoformat()
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE jobs SET status=?, updated_at=? WHERE id=?",
                (status, now, job_id)
            )

    def already_applied(self, job_id: str) -> bool:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT id FROM applications WHERE job_id=?", (job_id,)
            ).fetchone()
            return row is not None

    # ──────────────────── APPLICATIONS ───────────────────────

    def record_application(self, job_id: str, portal: str,
                           application_url: str = "",
                           cover_letter: str = "",
                           cv_version: str = "default",
                           notes: str = "",
                           status: str = "applied") -> int:
        now = datetime.utcnow().isoformat()
        with self._get_conn() as conn:
            cursor = conn.execute("""
                INSERT INTO applications
                    (job_id, applied_at, status, portal, application_url,
                     cover_letter, cv_version, notes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (job_id, now, status, portal, application_url, cover_letter, cv_version, notes, now))
            app_id = cursor.lastrowid
        # Also update job status
        self.update_job_status(job_id, status)
        return app_id

    def get_applications(self, limit: int = 200) -> List[Dict]:
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT a.*, j.title, j.company, j.score, j.url as job_url
                FROM applications a
                JOIN jobs j ON a.job_id = j.id
                ORDER BY a.applied_at DESC
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def update_application_status(self, app_id: int, status: str, notes: str = ""):
        now = datetime.utcnow().isoformat()
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE applications SET status=?, notes=?, updated_at=? WHERE id=?",
                (status, notes, now, app_id)
            )

    # ──────────────────── EMAILS ─────────────────────────────

    def record_email(self, uid: str, from_addr: str, subject: str,
                     body: str, email_type: str, job_id: Optional[str] = None):
        received_at = datetime.utcnow().isoformat()
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO emails
                    (uid, from_addr, subject, body, email_type, job_id, received_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (uid, from_addr, subject, body, email_type, job_id, received_at))

    def get_emails(self, limit: int = 100) -> List[Dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM emails ORDER BY received_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ──────────────────── STATS ──────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        with self._get_conn() as conn:
            total_scraped = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            total_matched = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE score >= 60 AND is_dealbreaker=0"
            ).fetchone()[0]
            total_applied = conn.execute(
                "SELECT COUNT(*) FROM applications"
            ).fetchone()[0]
            applied_today = conn.execute(
                "SELECT COUNT(*) FROM applications WHERE applied_at >= date('now')"
            ).fetchone()[0]
            responses = conn.execute(
                "SELECT COUNT(*) FROM emails WHERE email_type IN ('interview', 'rejection')"
            ).fetchone()[0]
            interviews = conn.execute(
                "SELECT COUNT(*) FROM applications WHERE status='interview'"
            ).fetchone()[0]

            by_portal = conn.execute("""
                SELECT portal, COUNT(*) as count FROM jobs GROUP BY portal
            """).fetchall()

            by_status = conn.execute("""
                SELECT status, COUNT(*) as count FROM applications GROUP BY status
            """).fetchall()

        return {
            "total_scraped": total_scraped,
            "total_matched": total_matched,
            "total_applied": total_applied,
            "applied_today": applied_today,
            "responses": responses,
            "interviews": interviews,
            "by_portal": {r["portal"]: r["count"] for r in by_portal},
            "by_status": {r["status"]: r["count"] for r in by_status},
        }

    def record_run_stats(self, portal: str, scraped: int, matched: int,
                         applied: int, failed: int, duration_s: float):
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO run_stats
                    (run_date, portal, jobs_scraped, jobs_matched,
                     jobs_applied, jobs_failed, run_duration_s)
                VALUES (date('now'), ?, ?, ?, ?, ?, ?)
            """, (portal, scraped, matched, applied, failed, duration_s))

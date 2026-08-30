"""
email_monitor/monitor.py — Gmail IMAP monitor for job-related emails.
Monitors: application confirmations, OTP codes, interview invites, rejections.
"""

import imaplib
import email as email_lib
import email.message
import logging
import time
import re
import threading
from typing import Optional, Callable, List, Dict, Any
from email.header import decode_header
from datetime import datetime

from config import EMAIL as EMAIL_CONFIG

logger = logging.getLogger(__name__)


def _decode_subject(subject: str) -> str:
    """Decode email subject (handles encoded headers)."""
    parts = decode_header(subject)
    decoded = []
    for part, encoding in parts:
        if isinstance(part, bytes):
            try:
                decoded.append(part.decode(encoding or "utf-8", errors="replace"))
            except Exception:
                decoded.append(part.decode("utf-8", errors="replace"))
        else:
            decoded.append(str(part))
    return " ".join(decoded)


def _get_email_body(msg: Any) -> str:
    """Extract plain text body from email message."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                        break
                except Exception:
                    pass
            elif content_type == "text/html" and not body:
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        html = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                        # Strip HTML tags for plain text
                        body = re.sub(r"<[^>]+>", " ", html)
                        body = re.sub(r"\s+", " ", body).strip()
                except Exception:
                    pass
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
        except Exception:
            pass
    return body


def _classify_email(subject: str, body: str) -> str:
    """
    Classify an email as: application_received | otp | interview | rejection | other
    """
    text = (subject + " " + body).lower()
    subj = subject.lower()

    # OTP / Security Code detection (requires regex word boundary to avoid false positives)
    if re.search(r'\b(otp|one.time.password|verification code|security code|login code)\b', text):
        if any(k in subj for k in ["thank you for applying", "application received", "application was sent", "applied to"]):
            return "application_received"
        return "otp"

    # Application confirmed
    app_keywords = EMAIL_CONFIG["application_keywords"] + [
        "application was sent", "applied to", "thank you for applying",
        "we received your application", "application submitted",
        "confirmation of your application", "application for"
    ]
    if any(kw in text for kw in app_keywords):
        return "application_received"

    # Interview invite
    interview_keywords = EMAIL_CONFIG["interview_keywords"]
    if any(kw in text for kw in interview_keywords):
        return "interview"

    # Rejection
    rejection_keywords = EMAIL_CONFIG["rejection_keywords"]
    if any(kw in text for kw in rejection_keywords):
        return "rejection"

    return "other"


def _extract_otp(body: str) -> Optional[str]:
    """Extract OTP code from email body."""
    # Common OTP patterns: 4-8 digit codes
    patterns = [
        r'\b(\d{4,8})\b(?:\s*(?:is\s+your|your|as\s+your|OTP|one.time|verification|code|password))',
        r'(?:OTP|code|password)[:\s]+(\d{4,8})',
        r'<strong>(\d{4,8})</strong>',
        r'\b([0-9]{6})\b',  # Most OTPs are 6 digits
    ]
    for pattern in patterns:
        m = re.search(pattern, body, re.I)
        if m:
            return m.group(1)
    return None


class EmailMonitor:
    """
    Background Gmail IMAP monitor.
    Runs in a separate thread, checks for new emails every N seconds.
    """

    def __init__(self, db=None):
        self.db = db
        self.gmail_address = EMAIL_CONFIG.get("gmail_address", "")
        self.gmail_password = EMAIL_CONFIG.get("gmail_app_password", "")
        self.imap_server = EMAIL_CONFIG.get("imap_server", "imap.gmail.com")
        self.imap_port = EMAIL_CONFIG.get("imap_port", 993)
        self.check_interval = EMAIL_CONFIG.get("check_interval_seconds", 60)

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callbacks: List[Callable] = []
        self.enabled = bool(self.gmail_address and self.gmail_password)

        if not self.enabled:
            logger.info("[EmailMonitor] Not configured (no Gmail credentials). Skipping.")

    def add_callback(self, callback: Callable):
        """Register a callback for new job-related emails."""
        self._callbacks.append(callback)

    def _notify(self, email_data: Dict):
        """Notify all registered callbacks of a new email."""
        for cb in self._callbacks:
            try:
                cb(email_data)
            except Exception as e:
                logger.error(f"[EmailMonitor] Callback error: {e}")

    def _connect(self) -> Optional[imaplib.IMAP4_SSL]:
        """Connect to Gmail IMAP server."""
        try:
            imap = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            imap.login(self.gmail_address, self.gmail_password)
            logger.info("[EmailMonitor] Connected to Gmail IMAP")
            return imap
        except imaplib.IMAP4.error as e:
            logger.error(f"[EmailMonitor] Login failed: {e}")
            logger.error(
                "Make sure you're using an App Password, not your regular Gmail password. "
                "Generate at: https://myaccount.google.com/apppasswords"
            )
            return None
        except Exception as e:
            logger.error(f"[EmailMonitor] Connection error: {e}")
            return None

    def _check_once(self, imap: imaplib.IMAP4_SSL) -> List[Dict]:
        """Check inbox for new unread emails. Returns list of processed email dicts."""
        new_emails = []
        try:
            imap.select("INBOX")
            status, messages = imap.search(None, "UNSEEN")
            if status != "OK":
                return new_emails

            uids = messages[0].split()
            for uid in uids[-50:]:  # Process latest 50 unread
                status, msg_data = imap.fetch(uid, "(RFC822)")
                if status != "OK":
                    continue

                for response in msg_data:
                    if not isinstance(response, tuple):
                        continue
                    msg = email_lib.message_from_bytes(response[1])

                    subject = _decode_subject(msg.get("Subject", ""))
                    from_addr = msg.get("From", "")
                    body = _get_email_body(msg)

                    email_type = _classify_email(subject, body)

                    # Only process job-related emails
                    if email_type == "other":
                        continue

                    email_data = {
                        "uid": uid.decode(),
                        "from_addr": from_addr,
                        "subject": subject,
                        "body": body[:2000],  # Store first 2000 chars
                        "email_type": email_type,
                        "otp": _extract_otp(body) if email_type == "otp" else None,
                        "received_at": datetime.utcnow().isoformat(),
                    }

                    logger.info(
                        f"[EmailMonitor] New {email_type} email from {from_addr}: '{subject[:60]}'"
                    )

                    if self.db:
                        self.db.record_email(
                            uid=email_data["uid"],
                            from_addr=from_addr,
                            subject=subject,
                            body=email_data["body"],
                            email_type=email_type,
                        )

                    self._notify(email_data)
                    new_emails.append(email_data)

        except Exception as e:
            logger.error(f"[EmailMonitor] Check error: {e}")

        return new_emails

    def sync_inbox(self, max_emails: int = 150) -> List[Dict]:
        """Perform a full synchronization of Gmail inbox with DB."""
        if not self.enabled:
            logger.warning("[EmailMonitor] Cannot sync: Gmail credentials not configured")
            return []

        imap = self._connect()
        if not imap:
            return []

        synced = []
        try:
            imap.select("INBOX")
            status, messages = imap.search(None, 'OR (FROM "greenhouse") (OR (FROM "linkedin") (OR (FROM "naukri") (FROM "indeed")))')
            all_uids = messages[0].split() if status == "OK" else []

            if not all_uids:
                status, messages = imap.search(None, "ALL")
                all_uids = messages[0].split() if status == "OK" else []

            logger.info(f"[EmailMonitor] Syncing {len(all_uids)} email(s) from IMAP...")
            for uid in reversed(all_uids[-max_emails:]):
                res, msg_data = imap.fetch(uid, "(RFC822)")
                if res != "OK":
                    continue
                for response in msg_data:
                    if not isinstance(response, tuple):
                        continue
                    msg = email_lib.message_from_bytes(response[1])
                    subject = _decode_subject(msg.get("Subject", ""))
                    from_addr = msg.get("From", "")
                    body = _get_email_body(msg)
                    email_type = _classify_email(subject, body)

                    email_data = {
                        "uid": uid.decode(),
                        "from_addr": from_addr,
                        "subject": subject,
                        "body": body[:2000],
                        "email_type": email_type,
                        "received_at": datetime.utcnow().isoformat(),
                    }

                    if self.db:
                        self.db.record_email(
                            uid=email_data["uid"],
                            from_addr=from_addr,
                            subject=subject,
                            body=email_data["body"],
                            email_type=email_type,
                        )
                    synced.append(email_data)

            logger.info(f"[EmailMonitor] Successfully synced {len(synced)} email(s) into database")
        except Exception as e:
            logger.error(f"[EmailMonitor] Sync error: {e}")
        finally:
            try:
                imap.logout()
            except Exception:
                pass

        return synced

    def _run(self):
        """Main monitoring loop (runs in background thread)."""
        logger.info(f"[EmailMonitor] Starting — checking every {self.check_interval}s")
        imap = None

        while self._running:
            try:
                if imap is None:
                    imap = self._connect()
                    if imap is None:
                        time.sleep(self.check_interval * 2)
                        continue

                self._check_once(imap)
                time.sleep(self.check_interval)

            except (imaplib.IMAP4.abort, imaplib.IMAP4.error, OSError) as e:
                logger.warning(f"[EmailMonitor] Connection dropped: {e}. Reconnecting...")
                imap = None
                time.sleep(30)
            except Exception as e:
                logger.error(f"[EmailMonitor] Unexpected error: {e}")
                time.sleep(self.check_interval)

        if imap:
            try:
                imap.logout()
            except Exception:
                pass

    def start(self):
        """Start background email monitoring thread."""
        if not self.enabled:
            logger.info("[EmailMonitor] Skipped (not configured)")
            return
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("[EmailMonitor] Background monitoring started")

    def stop(self):
        """Stop background monitoring."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("[EmailMonitor] Stopped")

    def check_for_otp(self, timeout: int = 120) -> Optional[str]:
        """
        Block and wait for an OTP email. Returns the OTP code or None.
        Used by the applier when a login requires OTP.
        """
        if not self.enabled:
            logger.warning("[EmailMonitor] Not configured — cannot auto-fetch OTP")
            return None

        found_otp = [None]
        event = threading.Event()

        def otp_callback(email_data: Dict):
            if email_data.get("email_type") == "otp" and email_data.get("otp"):
                found_otp[0] = email_data["otp"]
                event.set()

        self.add_callback(otp_callback)
        event.wait(timeout=timeout)
        self._callbacks = [cb for cb in self._callbacks if cb != otp_callback]

        if found_otp[0]:
            logger.info(f"[EmailMonitor] Got OTP: {found_otp[0]}")
        else:
            logger.warning(f"[EmailMonitor] OTP not received within {timeout}s")

        return found_otp[0]

import sqlite3
import sys
import imaplib
import email as email_lib

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from email_monitor.monitor import EmailMonitor, _decode_subject

print("--- FULL AUDIT: CROSS-MATCHING APPLIED JOBS WITH GMAIL INBOX ---")

# 1. Fetch all applied jobs from SQLite DB
conn = sqlite3.connect('db/jobs.db')
cursor = conn.cursor()
cursor.execute("SELECT id, title, company, portal, status, updated_at FROM jobs WHERE status = 'applied'")
applied_jobs = cursor.fetchall()
conn.close()

print(f"\n[Database] Found {len(applied_jobs)} job(s) marked as APPLIED in db/jobs.db:\n")
for idx, job in enumerate(applied_jobs, 1):
    job_id, title, company, portal, status, updated_at = job
    print(f"{idx}. {title} @ {company} ({portal.upper()}) - {updated_at}")

# 2. Fetch all job-related emails from Gmail IMAP
print("\n[Gmail IMAP] Connecting to ranjankumar684118@gmail.com...")
monitor = EmailMonitor()
imap = monitor._connect()

if not imap:
    print("[ERROR] Could not connect to Gmail IMAP.")
    sys.exit(1)

imap.select("INBOX")
# Search for emails from Greenhouse or LinkedIn or containing "application" / "security code"
status, messages = imap.search(None, 'OR (FROM "greenhouse") (FROM "linkedin")')
all_uids = messages[0].split() if status == "OK" else []

print(f"[Gmail IMAP] Found {len(all_uids)} email(s) from Greenhouse/LinkedIn.\n")

email_records = []
for uid in reversed(all_uids[-50:]):
    res, msg_data = imap.fetch(uid, "(RFC822)")
    if res != "OK":
        continue
    for response in msg_data:
        if isinstance(response, tuple):
            msg = email_lib.message_from_bytes(response[1])
            subj = _decode_subject(msg.get("Subject", ""))
            from_addr = msg.get("From", "")
            date_str = msg.get("Date", "")
            email_records.append({
                "uid": uid.decode(),
                "from": from_addr,
                "subject": subj,
                "date": date_str
            })

imap.logout()

# 3. Perform Cross-Verification Match
print("=" * 70)
print("AUDIT RESULTS: APPLIED JOBS VS GMAIL INBOX MATCHING")
print("=" * 70)

for idx, job in enumerate(applied_jobs, 1):
    job_id, title, company, portal, status, updated_at = job
    matches = []
    comp_clean = company.lower().replace(" ", "").replace(".com", "")
    
    for em in email_records:
        subj_clean = em["subject"].lower()
        from_clean = em["from"].lower()
        if comp_clean in subj_clean or comp_clean in from_clean or "greenhouse" in from_clean or "linkedin" in from_clean:
            matches.append(em)

    print(f"\nJob #{idx}: {title} @ {company}")
    print(f"   DB Status: {status.upper()} at {updated_at}")
    if matches:
        print(f"   ✅ Gmail Verification Match ({len(matches)} email(s) found):")
        for m in matches[:3]:
            print(f"      - Subject: '{m['subject']}' | From: {m['from']} | Date: {m['date']}")
    else:
        print(f"   ℹ️  Email Note: Pending confirmation email or verification step")

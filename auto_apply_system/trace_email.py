import imaplib
import email as email_lib
from email_monitor.monitor import EmailMonitor, _decode_subject, _classify_email

print("--- LIVE GMAIL INBOX TRACE ---")
monitor = EmailMonitor()
print(f"[Email Monitor] Configured Address: {monitor.gmail_address}")

imap = monitor._connect()
if not imap:
    print("[Email Monitor] Unable to connect to Gmail IMAP. Please check App Password.")
else:
    print("[Email Monitor] IMAP Connection SUCCESSFUL!")
    imap.select("INBOX")
    status, messages = imap.search(None, "ALL")
    if status == "OK":
        uids = messages[0].split()
        print(f"[Email Monitor] Total Emails in INBOX: {len(uids)}")
        latest_uids = uids[-15:]  # Get last 15 emails
        print(f"[Email Monitor] Fetching latest {len(latest_uids)} email(s)...\n")
        
        for uid in reversed(latest_uids):
            res, msg_data = imap.fetch(uid, "(RFC822)")
            if res != "OK":
                continue
            for response in msg_data:
                if isinstance(response, tuple):
                    msg = email_lib.message_from_bytes(response[1])
                    subject = _decode_subject(msg.get("Subject", ""))
                    from_addr = msg.get("From", "")
                    date_str = msg.get("Date", "")
                    print(f"UID: {uid.decode()}")
                    print(f"From: {from_addr}")
                    print(f"Subject: {subject}")
                    print(f"Date: {date_str}")
                    print("=" * 60)
    imap.logout()

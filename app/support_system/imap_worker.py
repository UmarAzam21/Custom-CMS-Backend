"""
Standalone worker that polls the support mailbox via IMAP, finds replies
addressed to ticket+<id>@yourdomain.com, and files them as inbound messages
on the matching ticket.

Run with:  python -m app.imap_worker
"""

import email
import imaplib
import re
import time
from email.header import decode_header
from email.utils import parseaddr

from app import models
from app.db import SessionLocal
from app.support_system import crud
from app.support_system.config import settings


try:
    _LOCAL_PART = settings.IMAP_USER.split("@", 1)[0]
except Exception:
    _LOCAL_PART = "support"

TICKET_ADDRESS_RE = re.compile(
    re.escape(_LOCAL_PART) + r"\+(\d+)@" + re.escape(settings.SUPPORT_DOMAIN),
    re.IGNORECASE,
)

# Fallback: extract ticket id from subject like "[Ticket #123] ..."
SUBJECT_TICKET_RE = re.compile(r"\[Ticket #(\d+)\]")

def _decode(value: str | None) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    decoded = ""
    for text, encoding in parts:
        if isinstance(text, bytes):
            decoded += text.decode(encoding or "utf-8", errors="replace")
        else:
            decoded += text
    return decoded


def _extract_ticket_id(msg: email.message.Message) -> int | None:
    # Check the headers most likely to contain the ticket+<id>@domain alias.
    for header_name in ("To", "Delivered-To", "X-Original-To", "Cc", "Envelope-To"):
        header_value = _decode(msg.get(header_name))
        match = TICKET_ADDRESS_RE.search(header_value)
        if match:
            return int(match.group(1))

    # Fallback 1: try to find ticket id in subject like "[Ticket #123]"
    subject = _decode(msg.get("Subject"))
    if subject:
        sm = SUBJECT_TICKET_RE.search(subject)
        if sm:
            return int(sm.group(1))

    # Fallback 2: try to find pattern in the plain-text body (if available)
    try:
        body = _extract_body(msg)
        bm = SUBJECT_TICKET_RE.search(body)
        if bm:
            return int(bm.group(1))
    except Exception:
        pass

    return None


def _extract_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition") or "")
            if content_type == "text/plain" and "attachment" not in disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace").strip()
        # Fallback: no plain-text part found
        return "(no plain-text content found)"
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace").strip()
        return str(msg.get_payload())


def process_mailbox() -> int:
    """Connects, processes all unseen messages, returns count processed."""
    imap = imaplib.IMAP4_SSL(settings.IMAP_HOST, settings.IMAP_PORT)
    imap.login(settings.IMAP_USER, settings.IMAP_PASSWORD)
    imap.select(settings.IMAP_MAILBOX)

    status_, data = imap.search(None, "UNSEEN")
    if status_ != "OK":
        imap.logout()
        return 0

    message_ids = data[0].split()
    processed = 0
    db = SessionLocal()
    try:
        for msg_id in message_ids:
            status_, msg_data = imap.fetch(msg_id, "(RFC822)")
            if status_ != "OK" or not msg_data or not msg_data[0]:
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            ticket_id = _extract_ticket_id(msg)
            if ticket_id is None:
                # Not a reply to a known ticket alias — leave it unread/skip.
                print(f"[imap_worker] Skipping message {msg_id}: no ticket address found")
                continue

            ticket = crud.get_ticket(db, ticket_id)
            if ticket is None:
                print(f"[imap_worker] Skipping message {msg_id}: ticket #{ticket_id} not found")
                continue

            _, sender_email = parseaddr(_decode(msg.get("From")))
            body = _extract_body(msg)

            crud.add_message(
                db,
                ticket=ticket,
                direction=models.MessageDirection.INBOUND,
                sender_email=sender_email or "unknown",
                body=body,
            )
            print(f"[imap_worker] Filed reply into ticket #{ticket_id} from {sender_email}")
            processed += 1

            # Mark as seen so we don't reprocess it.
            imap.store(msg_id, "+FLAGS", "\\Seen")
    finally:
        db.close()
        imap.close()
        imap.logout()

    return processed


def run_forever():
    print(
        f"[imap_worker] Polling {settings.IMAP_USER} every "
        f"{settings.IMAP_POLL_SECONDS}s..."
    )
    while True:
        try:
            count = process_mailbox()
            if count:
                print(f"[imap_worker] Processed {count} message(s)")
        except Exception as exc:
            print(f"[imap_worker] Error: {exc}")
        time.sleep(settings.IMAP_POLL_SECONDS)


if __name__ == "__main__":
    run_forever()

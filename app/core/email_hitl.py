"""
Email-based human-in-the-loop.

Lets the orchestrator ask the user a question by email, then poll the inbox and
read the reply — so any workflow step can be gated on real human approval/input.

The reply parser strips Gmail's quoted history (multi-line "On <date> ... wrote:")
and returns the user's actual words. All values are unicode-safe.

Reused proven logic originally prototyped in run_full_demo.py.
"""
import os
import re
import time
import base64
import uuid
from email.mime.text import MIMEText
from app.core.google_auth import get_gmail_service

DEFAULT_POLL = 12          # seconds between inbox checks
DEFAULT_TIMEOUT = 600      # max seconds to wait for a reply
SUBJECT_TAG = "TAX-AGENT"


def _user_email(to_email: str = None) -> str:
    return to_email or os.getenv("USER_EMAIL", "")


def ask_via_email(question: str, subject: str = "Action required",
                  to_email: str = None, token: str = None) -> dict:
    """
    Send a question email. Returns {token, thread_id, question_id} for await_reply.
    """
    to = _user_email(to_email)
    if not to:
        raise ValueError("No recipient: pass to_email or set USER_EMAIL in the env.")
    token = token or uuid.uuid4().hex[:6].upper()
    gmail = get_gmail_service()
    from app.core.email_format import sanitize_email_body
    msg = MIMEText(sanitize_email_body(question))
    msg["to"] = to
    msg["subject"] = f"[{SUBJECT_TAG} {token}] {sanitize_email_body(subject)}"
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    sent = gmail.users().messages().send(userId="me", body={"raw": raw}).execute()
    return {"token": token, "thread_id": sent["threadId"], "question_id": sent["id"]}


def _decode_body(payload: dict) -> str:
    """Recursively pull the text/plain body out of a Gmail message payload."""
    if payload.get("mimeType", "").startswith("text/plain"):
        data = payload.get("body", {}).get("data")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", "ignore")
    for part in payload.get("parts", []) or []:
        text = _decode_body(part)
        if text:
            return text
    return ""


def clean_reply(text: str) -> str:
    """Return the first real line of a reply, ignoring Gmail quoted history."""
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith(">"):
            continue
        # Attribution can wrap across lines: "On <date> ... <email>" then "wrote:"
        if s.startswith("On ") and ("wrote:" in s or "@" in s):
            break
        return s
    return ""


def check_reply(thread_id: str, question_id: str) -> str:
    """One NON-blocking check for a reply on the thread; returns cleaned text or ""."""
    gmail = get_gmail_service()
    thread = gmail.users().threads().get(
        userId="me", id=thread_id, format="full"
    ).execute()
    replies = [m for m in thread.get("messages", []) if m["id"] != question_id]
    if replies:
        newest = max(replies, key=lambda m: int(m["internalDate"]))
        body = _decode_body(newest["payload"]) or newest.get("snippet", "")
        return clean_reply(body) or newest.get("snippet", "").strip()
    return ""


def await_reply(thread_id: str, question_id: str,
                timeout: int = DEFAULT_TIMEOUT, poll: int = DEFAULT_POLL) -> str:
    """
    BLOCKING poll until a reply appears; returns cleaned text or "" on timeout.
    Async runs use check_reply() (single, non-blocking) via the poller instead.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        reply = check_reply(thread_id, question_id)
        if reply:
            return reply
        time.sleep(poll)
    return ""


def ask_and_wait(question: str, subject: str = "Action required",
                 to_email: str = None, timeout: int = DEFAULT_TIMEOUT,
                 poll: int = DEFAULT_POLL) -> str:
    """Send a question and block until the user replies (or timeout). Returns reply text."""
    info = ask_via_email(question, subject=subject, to_email=to_email)
    return await_reply(info["thread_id"], info["question_id"], timeout=timeout, poll=poll)


def first_number(text: str):
    """First numeric value in a string (commas stripped), or None."""
    if not text:
        return None
    m = re.search(r"[-+]?\d[\d,]*\.?\d*", text.replace(",", ""))
    return float(m.group()) if m else None


def affirmative(text: str, keywords=("approve", "yes", "confirm", "ok", "proceed", "compute")) -> bool:
    """True if the reply contains an approval keyword (and not a denial)."""
    if not text:
        return False
    low = text.lower()
    if any(d in low for d in ("deny", "reject", "stop", "cancel")):
        return False
    return any(k in low for k in keywords)

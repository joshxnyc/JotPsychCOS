"""CAN-SPAM. The parts of it that are actually a legal obligation.

15 U.S.C. 7704 requires commercial email to carry a valid physical postal
address, a clear and conspicuous way to opt out, and honest headers — and
requires the opt-out to be honoured within ten business days. This machine
honours it on the next run, which is at most a day.

The footer is appended after drafting and before quality control, so the model
cannot omit it, reword it, or be talked out of it. QC then verifies it survived.
"""
import hashlib, hmac, os
from . import config

# CAN-SPAM requires a genuine physical address in every commercial message, so
# this default is JotPsych's real one rather than a plausible-looking stand-in.
POSTAL_ADDRESS = (os.getenv("POSTAL_ADDRESS") or
                  "JotPsych, Brooklyn Navy Yard, Dock 72, 7th Floor, "
                  "Brooklyn, NY 11205").strip()
APP_URL = (os.getenv("APP_URL") or "").strip().rstrip("/")
SECRET = (os.getenv("APP_SECRET") or "dev-secret-not-for-production").encode()

MARKER = "You are receiving this because you signed up for JotPsych."


def token(email: str) -> str:
    """Signed, so an unsubscribe link cannot be used to unsubscribe someone else."""
    e = (email or "").strip().lower()
    sig = hmac.new(SECRET, e.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{e}:{sig}"


def verify(tok: str) -> str:
    """Returns the email if the signature is good, otherwise an empty string."""
    email, _, sig = (tok or "").rpartition(":")
    if not email or not sig:
        return ""
    good = hmac.new(SECRET, email.encode(), hashlib.sha256).hexdigest()[:16]
    return email if hmac.compare_digest(sig, good) else ""


def unsubscribe_url(email: str) -> str:
    if not APP_URL:
        return ""
    return f"{APP_URL}/unsubscribe?t={token(email)}"


def footer(email: str) -> str:
    url = unsubscribe_url(email)
    opt_out = (f"Unsubscribe: {url}" if url else
               "To stop receiving these, reply with the word STOP.")
    return (f"\n\n--\n{MARKER}\n{opt_out}\n{POSTAL_ADDRESS}")


def apply(draft: dict) -> dict:
    """Append the footer unless it is already there. Never modifies the subject."""
    body = (draft.get("body") or "").rstrip()
    if MARKER in body:
        return draft
    return {**draft, "body": body + footer(draft.get("to", ""))}


def headers(email: str) -> dict:
    """One-click unsubscribe. Gmail and Yahoo require this for bulk senders, and
    it is what stops an annoyed clinician reaching for the spam button instead."""
    url = unsubscribe_url(email)
    if not url:
        return {}
    return {"List-Unsubscribe": f"<{url}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}


def present(body: str) -> bool:
    b = body or ""
    return MARKER in b and (POSTAL_ADDRESS.split(",")[0] in b)

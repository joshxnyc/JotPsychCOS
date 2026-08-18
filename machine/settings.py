"""Settings a person can change without a deploy.

Three layers, in order: what the console holds, then the environment, then the
built-in default. Anything not in SCHEMA below is deployment-level on purpose —
credentials and the sending switch are not things a workspace should be able to
change about itself.
"""
import os

# key -> (label, default, help, kind)
SCHEMA = {
    "approval_mode": (
        "Approval", "autopilot",
        "autopilot: messages that pass every check send on their own, and only "
        "'needs a person' items wait for you. review: every message waits for "
        "approval — human time then grows with the audience, which is the "
        "trade you are choosing.", "choice:autopilot,review"),
    "test_recipient": (
        "Test recipient", "",
        "Where sample messages go by default. Anyone can still enter a different "
        "address on an individual message.", "email"),
    "postal_address": (
        "Postal address", "JotPsych, Brooklyn Navy Yard, Dock 72, 7th Floor, Brooklyn, NY 11205",
        "Appears in every message. CAN-SPAM requires a genuine physical address.", "text"),
    "keep_warm_days": (
        "Quarterly note, in days", "90",
        "How long a clinician hears nothing before a keep-warm note is due.", "int"),
    "moment_cooldown_days": (
        "Cooldown after writing, in days", "30",
        "Never two messages inside this window, however strong the signal.", "int"),
    "confidence_verified": (
        "Confident at", "70",
        "Score at or above which a message may name specialty, state and city.", "int"),
    "confidence_probable": (
        "Likely at", "40",
        "Score at or above which a message may name specialty and state only. "
        "Below it, nothing about them is said at all.", "int"),
    "max_sends_per_run": (
        "Messages written per cycle", "5",
        "The cost cap. Anything over it waits for the next cycle.", "int"),
    "prospect_states": (
        "Watch these states", "NY,CA,TX,FL,IL,MA,WA,CO,GA,NC",
        "Where to look for newly registered practices.", "text"),
    "prospect_window_days": (
        "New practice window, in days", "90",
        "How recently a practice must have registered to count as new.", "int"),
}

_ENV = {"test_recipient": "DIGEST_TO", "postal_address": "POSTAL_ADDRESS",
        "max_sends_per_run": "MAX_SENDS_PER_RUN",
        "prospect_states": "PROSPECT_STATES",
        "prospect_window_days": "PROSPECT_WINDOW_DAYS"}


def get(key: str) -> str:
    """Console value, then environment, then default. Never raises — a settings
    lookup must not be able to stop a cycle."""
    label, default, _help, _kind = SCHEMA.get(key, ("", "", "", "text"))
    try:
        from . import db
        c = db.connect()
        try:
            v = db.get_setting(c, key, "")
        finally:
            c.close()
        if v:
            return v
    except Exception:
        pass
    return (os.getenv(_ENV.get(key, "")) or "").strip() or default


def get_int(key: str) -> int:
    try:
        return int(float(get(key)))
    except (TypeError, ValueError):
        return int(SCHEMA[key][1])


def get_list(key: str) -> list[str]:
    return [x.strip().upper() for x in get(key).split(",") if x.strip()]


def validate(key: str, value: str) -> tuple[bool, str]:
    """Reject values that would quietly break the machine rather than storing
    them and failing on the next cycle."""
    kind = SCHEMA.get(key, (None, None, None, "text"))[3]
    v = (value or "").strip()
    if kind == "int":
        if not v.isdigit() or int(v) < 0:
            return False, f"{SCHEMA[key][0]} must be a whole number."
        if key == "max_sends_per_run" and int(v) > 200:
            return False, "That cap is high enough to be a mistake. 200 is the limit here."
    if kind.startswith("choice:") and v not in kind.split(":")[1].split(","):
        return False, f"{SCHEMA[key][0]} must be one of: " + kind.split(":")[1].replace(",", ", ")
    if kind == "email" and v and ("@" not in v or len(v) < 6):
        return False, "That does not look like an email address."
    if key == "postal_address" and len(v) < 10:
        return False, "A postal address is required in every message and must be real."
    return True, ""

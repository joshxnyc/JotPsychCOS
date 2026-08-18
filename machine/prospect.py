"""NEWLY ENUMERATED NPIs — reaching clinicians before they have chosen anything.

The dormant list is people who already looked at JotPsych. This is the opposite
end: a behavioural-health NPI enumerated in the last few weeks is a practice
being *formed*. Nobody has picked an EHR yet, no contract is running, and the
objection that made the dormant list dormant does not exist yet.

It needs no list from anyone. CMS publishes the register, and the machine reads
it directly.

One honest constraint shapes everything here: **NPPES publishes no email
address.** It publishes a name, a taxonomy, a practice address and a business
phone. So a registry prospect never becomes an automated email. It becomes a
short brief for a person, with the practice phone from the public record. That
is the whole output, and pretending otherwise would be inventing contact details
for a real clinician.
"""
import datetime, os
from . import db, io_input

# The taxonomies JotPsych actually serves. Anything outside this is not a
# prospect, however new it is.
TAXONOMIES = [
    "Psychiatry", "Psychiatric", "Psychologist", "Social Worker",
    "Counselor", "Marriage & Family Therapist", "Mental Health",
]
DEFAULT_STATES = ["NY", "CA", "TX", "FL", "IL", "MA", "WA", "CO", "GA", "NC"]


def _states() -> list[str]:
    raw = (os.getenv("PROSPECT_STATES") or "").strip()
    return [s.strip().upper() for s in raw.split(",") if s.strip()] or DEFAULT_STATES


def _days() -> int:
    return int(os.getenv("PROSPECT_WINDOW_DAYS") or 90)


def _recent(date_str: str, days: int) -> bool:
    try:
        d = datetime.datetime.strptime(date_str, "%Y-%m-%d").replace(
            tzinfo=datetime.timezone.utc)
    except (ValueError, TypeError):
        return False
    return 0 <= (datetime.datetime.now(datetime.timezone.utc) - d).days <= days


def discover(limit_per_query: int = 200, max_new: int = 200) -> list[dict]:
    """Sweep the register for behavioural-health NPIs enumerated recently.

    The public API has no 'enumerated since' filter, so this queries by state and
    taxonomy and filters on enumeration_date locally. That is correct and slow.
    At production volume the monthly NPPES full file plus the weekly incremental
    replaces this entirely — and the weekly incremental *is* a new-enumeration
    feed, which is the whole reason to move to it.
    """
    days, found = _days(), []
    for state in _states():
        for tax in TAXONOMIES:
            hits = io_input.nppes_lookup(state=state, taxonomy=tax,
                                         limit=limit_per_query)
            for h in hits:
                if "_error" in h or not h.get("npi"):
                    continue
                if _recent(h.get("enumerated", ""), days):
                    found.append(h)
            if len(found) >= max_new:
                return found[:max_new]
    return found[:max_new]


def sync(c, actor: str = "machine") -> dict:
    """Write what the sweep found into the store. Only ever adds; a prospect who
    later signs up is matched by NPI and stops being a prospect."""
    new = seen = 0
    for r in discover():
        existing = c.execute("SELECT id, source FROM clinicians WHERE npi=?",
                             (r["npi"],)).fetchone()
        if existing:
            seen += 1
            continue
        db.upsert_clinician(
            c, name=r.get("name", "") or "(organisation)", email="", npi=r["npi"],
            source="prospect", tier="verified", score=100, candidates=1,
            specialty=r.get("taxonomy", ""), city=r.get("city", ""),
            state=r.get("state", ""), phone=r.get("phone", ""),
            enumerated_on=r.get("enumerated", ""), resolved_at=db.now())
        new += 1
    db.log(c, "prospects_synced", actor=actor,
           detail=f"{new} new, {seen} already known, window {_days()} days")
    return {"new": new, "already_known": seen, "window_days": _days(),
            "states": _states()}


def brief(row) -> str:
    """What a person needs to make the call. No draft email, because we have no
    address to send one to."""
    when = row["enumerated_on"] or "recently"
    where = ", ".join(x for x in (row["city"], row["state"]) if x)
    return (f"{row['name']} registered a new {row['specialty'] or 'behavioural health'} "
            f"NPI on {when} in {where or 'their state'}. A practice this new has not "
            f"chosen its systems yet — there is no contract to wait out and nothing to "
            f"migrate. Public practice line: {row['phone'] or 'not published'}. "
            f"NPI {row['npi']}, from the public federal register.")

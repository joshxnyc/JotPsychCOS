"""THE WATCH. What changed in the federal registry since our last run.

Enrichment and monitoring are the same call. Resolving a clinician produces a
profile; *keeping* that profile turns the next run into a diff. That is why
memory is not decoration here — without state/ the machine is structurally
incapable of noticing a moment. Delete the snapshot and it goes blind.

Two files:
  state/registry_snapshot.json  - what the registry said last time
  state/registry_history.jsonl  - append-only log of every change ever seen

The workflow commits both back to the repo, so the git log of state/ is the
change history, timestamped by GitHub rather than by us.
"""
import json, datetime
from . import config

SNAPSHOT = config.STATE / "registry_snapshot.json"
HISTORY  = config.STATE / "registry_history.jsonl"

# The fields worth watching, and what a change in each one means commercially.
# A practice that changes shape is a practice whose software question reopened.
WATCHED = {
    "taxonomy":  ("taxonomy_change",
                  "their registered specialty changed"),
    "city":      ("practice_move",
                  "their practice location moved"),
    "state":     ("practice_move_state",
                  "their practice moved to another state"),
    "address_1": ("practice_move",
                  "their practice address changed"),
    "entity":    ("became_organization",
                  "they went from an individual NPI to an organizational one"),
    "name":      ("practice_renamed",
                  "the registered practice name changed"),
}

# How strong a buying signal each change is. Drives who gets a message and who
# gets a human. Tunable without code.
TRIGGER_WEIGHT = {
    "became_organization":  100,   # solo -> group. The strongest signal we have.
    "practice_move_state":   85,
    "practice_move":         70,
    "practice_renamed":      60,
    "taxonomy_change":       55,
    "newly_enumerated":      50,
    "registry_touched":      20,
}

def _fields(res: dict) -> dict:
    r = res.get("registry", {}) or {}
    return {k: r.get(k, "") for k in
            ("taxonomy", "city", "state", "address_1", "entity", "name",
             "last_updated", "enumeration_date")}

def load_snapshot() -> dict:
    if SNAPSHOT.exists():
        try:
            return json.loads(SNAPSHOT.read_text())
        except json.JSONDecodeError:
            pass
    return {}

def save_snapshot(snap: dict) -> None:
    SNAPSHOT.write_text(json.dumps(snap, indent=2, sort_keys=True))

def observe(resolutions: dict, run_id: str) -> dict:
    """Compare this run's registry reads against last run's. Returns
    {target_id: [trigger, ...]} and appends every change to the history."""
    prev = load_snapshot()
    curr, triggers, history_rows = {}, {}, []
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    for tid, res in resolutions.items():
        if not res.get("npi"):
            continue                      # nothing to watch without an identity
        curr[tid] = _fields(res)
        before = prev.get(tid)

        if before is None:
            # First sighting. Not a change — but a very recent enumeration is
            # itself a signal: this clinician only just appeared on the register.
            if _is_recent(curr[tid].get("enumeration_date", ""), days=120):
                triggers.setdefault(tid, []).append({
                    "type": "newly_enumerated",
                    "weight": TRIGGER_WEIGHT["newly_enumerated"],
                    "detail": "their NPI was enumerated in the last few months",
                    "field": "enumeration_date", "before": "", "after": curr[tid]["enumeration_date"]})
            continue

        for field, (ttype, meaning) in WATCHED.items():
            old, new = (before.get(field) or "").strip(), (curr[tid].get(field) or "").strip()
            if old and new and old != new:
                triggers.setdefault(tid, []).append({
                    "type": ttype, "weight": TRIGGER_WEIGHT[ttype], "detail": meaning,
                    "field": field, "before": old, "after": new})
                history_rows.append({"ts": now, "run_id": run_id, "target_id": tid,
                                     "npi": res["npi"], "field": field,
                                     "before": old, "after": new, "trigger": ttype})

        # CMS stamps its own last_updated. If it moved but nothing we watch did,
        # something changed that we do not model. Weak signal, logged not acted on.
        if (before.get("last_updated") != curr[tid].get("last_updated")
                and tid not in triggers):
            triggers.setdefault(tid, []).append({
                "type": "registry_touched", "weight": TRIGGER_WEIGHT["registry_touched"],
                "detail": "their registry record was updated in a way we do not model",
                "field": "last_updated", "before": before.get("last_updated", ""),
                "after": curr[tid].get("last_updated", "")})

    # Carry forward anyone we did not read this run, so history is not lost.
    merged = {**prev, **curr}
    save_snapshot(merged)
    if history_rows:
        with HISTORY.open("a", encoding="utf-8") as f:
            for row in history_rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return triggers

def _is_recent(date_str: str, days: int) -> bool:
    try:
        d = datetime.datetime.strptime(date_str, "%Y-%m-%d").replace(
            tzinfo=datetime.timezone.utc)
    except (ValueError, TypeError):
        return False
    return (datetime.datetime.now(datetime.timezone.utc) - d).days <= days

def history() -> list[dict]:
    if not HISTORY.exists():
        return []
    out = []
    for line in HISTORY.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try: out.append(json.loads(line))
            except json.JSONDecodeError: pass
    return out

def best_trigger(triggers: list[dict]) -> dict | None:
    return max(triggers, key=lambda t: t["weight"]) if triggers else None

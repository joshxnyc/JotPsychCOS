"""State that survives runs. This is how the machine learns."""
import json, datetime
from . import config

DEFAULT = {
    "run_count": 0,
    "first_run": None,
    "last_run": None,
    "angles": {},        # angle -> {"sent": n, "replied": n, "blocked": n}
    "notes": [],
}

def load() -> dict:
    if config.STATEFILE.exists():
        try:
            s = json.loads(config.STATEFILE.read_text())
            return {**DEFAULT, **s}
        except json.JSONDecodeError:
            pass
    return dict(DEFAULT)

def save(state: dict) -> None:
    config.STATEFILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))

def start_run(state: dict) -> dict:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    state["run_count"] = state.get("run_count", 0) + 1
    state["first_run"] = state.get("first_run") or now
    state["last_run"] = now
    return state

def record(state: dict, angle: str, outcome: str) -> dict:
    a = state.setdefault("angles", {}).setdefault(
        angle, {"sent": 0, "replied": 0, "blocked": 0})
    a[outcome] = a.get(outcome, 0) + 1
    return state

def angle_weights(state: dict, angles: list[str]) -> dict[str, float]:
    """Laplace-smoothed reply rate per angle. The machine leans on what works."""
    w = {}
    for a in angles:
        s = state.get("angles", {}).get(a, {})
        sent, rep = s.get("sent", 0), s.get("replied", 0)
        w[a] = (rep + 1) / (sent + 2)
    return w

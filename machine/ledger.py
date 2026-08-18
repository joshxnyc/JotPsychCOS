"""Append-only record of every decision the machine made."""
import json, datetime
from . import config

_RUN_ID = 0

def set_run(run_id: int) -> None:
    """Stamp every row with the run that wrote it, so the run history is
    reconstructable from the ledger alone."""
    global _RUN_ID
    _RUN_ID = run_id

def append(record: dict) -> None:
    record = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "run": _RUN_ID, **record}
    with config.LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

def all_records() -> list[dict]:
    if not config.LEDGER.exists():
        return []
    out = []
    for line in config.LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try: out.append(json.loads(line))
            except json.JSONDecodeError: pass
    return out

def already_sent_ids() -> set[str]:
    return {r.get("target_id") for r in all_records()
            if r.get("action") == "sent" and r.get("target_id")}

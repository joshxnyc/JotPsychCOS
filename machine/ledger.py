"""Append-only record of every decision the machine made."""
import json, datetime
from . import config

def append(record: dict) -> None:
    record = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(), **record}
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

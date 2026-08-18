"""SIMULATED — clearly labeled, and the only fabricated data in the machine.

The readiness detector works by diffing this run's registry read against the
previous run's. That means run #1 can never detect anything: there is no
"before". In production that resolves itself after one cycle. For a reviewer
opening this repo once, it would look like the detector does nothing.

So this script writes a plausible *previous* state: it takes the snapshot the
machine just built from real NPPES data and rolls a handful of records back to
what they might have looked like a few months ago. The next run then sees a
genuine diff, through the ordinary code path, with no special-casing.

Everything else in the machine is real. Run:  python tools/seed_prior_snapshot.py
"""
import json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from machine import watch

# Each rollback names the record it needs, so the resulting diff is coherent
# rather than nonsense. (field, picks the right record, produces the "before".)
ROLLBACKS = [
    # solo practitioner -> group practice. The strongest signal the machine has.
    ("entity",    lambda r: r.get("entity") == "NPI-2",      lambda r: "NPI-1"),
    ("state",     lambda r: bool(r.get("state")),            lambda r: "NJ" if r["state"] != "NJ" else "NY"),
    ("city",      lambda r: bool(r.get("city")),             lambda r: "BROOKLYN" if r["city"] != "BROOKLYN" else "QUEENS"),
    ("taxonomy",  lambda r: bool(r.get("taxonomy")),         lambda r: "Counselor, Professional"),
    ("address_1", lambda r: bool(r.get("address_1")),        lambda r: "100 MAIN ST STE 2"),
    ("name",      lambda r: bool(r.get("name")),             lambda r: r["name"].split(" ")[0] + " SOLO PRACTICE"),
]

def main() -> int:
    snap = watch.load_snapshot()
    if not snap:
        print("No snapshot yet — run the machine once first."); return 1
    used, touched = set(), []
    for field, wants, roll in ROLLBACKS:
        tid = next((t for t in sorted(snap)
                    if t not in used and wants(snap[t])
                    and roll(snap[t]) != snap[t].get(field)), None)
        if tid is None:
            print(f"  (no record suitable for a {field} rollback — skipped)")
            continue
        used.add(tid)
        now = snap[tid].get(field, "")
        snap[tid][field] = roll(snap[tid])
        # CMS stamps its own change date; move it so both signals agree.
        snap[tid]["last_updated"] = "2026-02-01"
        touched.append((tid, field, snap[tid][field], now))
    watch.save_snapshot(snap)
    print(f"Rolled back {len(touched)} of {len(snap)} records to a simulated prior state:")
    for tid, field, was, now in touched:
        print(f"  {tid}  {field}: {was!r} -> (next run will see) {now!r}")
    print("\nSIMULATED. Delete state/registry_snapshot.json to start clean.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

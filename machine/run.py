"""ORCHESTRATOR. One pass of the loop:
   read input -> decide -> draft -> QC -> send -> log -> learn -> report
Run:  python -m machine.run [--limit N] [--live]
"""
import argparse, sys, json
from . import config, ledger, memory, qc, send, strategy, report

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=config.MAX_SENDS_PER_RUN)
    ap.add_argument("--live", action="store_true", help="actually send (overrides DRY_RUN)")
    ap.add_argument("--report-only", action="store_true")
    a = ap.parse_args(argv)
    if a.live:
        config.DRY_RUN = False

    state = memory.start_run(memory.load())

    if a.report_only:
        report.build(state); memory.save(state); return 0

    inputs = strategy.load_inputs()
    n_in = sum(len(v) for v in inputs.values() if isinstance(v, list))
    print(f"[input]  {n_in} records read from {config.INBOX}")
    if n_in == 0:
        print("[input]  nothing to do - drop a CSV in inbox/ and re-run")
        report.build(state); memory.save(state); return 0

    plans = strategy.decide(inputs, state)
    print(f"[decide] {len(plans)} plans")

    seen = ledger.already_sent_ids()
    sent = blocked = skipped = 0

    for plan in plans:
        if sent >= a.limit:
            print(f"[limit]  stopping at {a.limit} sends this run"); break
        if plan.target_id in seen:
            ledger.append({"action": "skipped", "target_id": plan.target_id,
                           "reason": "already contacted"}); skipped += 1; continue
        if not plan.to and not config.MAIL_TO_OVERRIDE:
            ledger.append({"action": "skipped", "target_id": plan.target_id,
                           "reason": "no email address"}); skipped += 1; continue

        d = strategy.draft(plan, state)
        v = qc.check(d, plan.context)

        if not v.ok:
            p = qc.quarantine(d, v, plan.context)
            ledger.append({"action": "blocked", "target_id": plan.target_id,
                           "angle": d["angle"], "subject": d["subject"],
                           "failures": v.failures, "warnings": v.warnings,
                           "quarantine": str(p.name)})
            memory.record(state, d["angle"], "blocked")
            blocked += 1
            print(f"[QC]     BLOCKED {plan.target_id}: {v.failures[0]}")
            continue

        r = send.send_email(d["to"], d["subject"], d["body"])
        ledger.append({"action": "sent" if r.ok else "send_failed",
                       "target_id": plan.target_id, "angle": d["angle"],
                       "to": r.get("to"), "subject": d["subject"],
                       "channel": r.get("channel"), "reason": plan.reason,
                       "warnings": v.warnings, "claims": d.get("claims", []),
                       "error": r.get("error")})
        if r.ok:
            memory.record(state, d["angle"], "sent"); sent += 1
            print(f"[send]   {r.get('channel')} -> {r.get('to')} :: {d['subject']}")
        else:
            print(f"[send]   FAILED {r.get('error')}")

    report.build(state)
    memory.save(state)
    print(f"\n[done]   sent={sent} blocked={blocked} skipped={skipped}")
    print(f"[done]   report  {config.DASH}")
    print(f"[done]   queue   {config.HUMANQ}")
    return 0

if __name__ == "__main__":
    sys.exit(main())

"""ORCHESTRATOR. One pass:
   read -> resolve -> watch -> decide -> draft -> QC -> send -> attribute -> report

Run:  python -m machine.run [--limit N] [--live]
"""
import argparse, sys, datetime
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
    print(f"[input]  {len(inputs['dormant'])} dormant clinicians, "
          f"{len(inputs['peers'])} peers, {len(inputs['returns'])} return events")

    plans = strategy.decide(inputs, state)
    counts = {}
    for p in plans:
        counts[p.action] = counts.get(p.action, 0) + 1
    print(f"[decide] {counts}")

    seen = ledger.already_sent_ids()
    sent = blocked = skipped = silent = queued = 0
    human_queue = []

    for plan in plans:
        # Silence is an outcome, not an absence. It is logged so the silence
        # rate is measurable rather than merely claimed.
        if plan.action == "silence":
            ledger.append({"action": "silence", "target_id": plan.target_id,
                           "reason": plan.reason})
            silent += 1
            continue

        if plan.action == "human_call":
            human_queue.append(plan)
            ledger.append({"action": "human_call", "target_id": plan.target_id,
                           "reason": plan.reason,
                           "peer": (plan.context.get("peer") or {}).get("name", "")})
            queued += 1
            continue

        # The model call is the cost, so the budget counts drafts, not sends.
        # Anything over budget waits for the next run rather than being dropped.
        if sent + blocked >= a.limit:
            ledger.append({"action": "deferred", "target_id": plan.target_id,
                           "reason": f"draft budget of {a.limit} spent this run"})
            skipped += 1
            continue
        if not plan.to and not config.MAIL_TO_OVERRIDE:
            ledger.append({"action": "skipped", "target_id": plan.target_id,
                           "reason": "no email address"}); skipped += 1; continue

        d = strategy.draft(plan, state)
        v = qc.check(d, plan.context)

        if not v.ok:
            p = qc.quarantine(d, v, plan.context)
            ledger.append({"action": "blocked", "target_id": plan.target_id,
                           "angle": d["angle"], "subject": d["subject"],
                           "plan_action": plan.action, "reason": plan.reason,
                           "failures": v.failures, "warnings": v.warnings,
                           "quarantine": p.name})
            memory.record(state, d["angle"], "blocked")
            blocked += 1
            print(f"[QC]     BLOCKED {plan.target_id}: {v.failures[0]}")
            continue

        r = send.deliver(d, plan.channel)
        ledger.append({"action": "sent" if r.ok else "send_failed",
                       "target_id": plan.target_id, "angle": d["angle"],
                       "plan_action": plan.action, "channel": r.get("channel"),
                       "to": r.get("to"), "subject": d["subject"],
                       "reason": plan.reason, "warnings": v.warnings,
                       "claims": d.get("claims", []), "error": r.get("error")})
        if r.ok:
            memory.record(state, d["angle"], "sent")
            _mark_contacted(state, plan, d)
            sent += 1
            print(f"[send]   {r.get('channel')} -> {r.get('to')} :: {d['subject']}")
        else:
            print(f"[send]   FAILED {r.get('error')}")

    report.write_human_queue(human_queue, state)
    report.build(state)
    memory.save(state)
    print(f"\n[done]   sent={sent} blocked={blocked} silent={silent} "
          f"human_queue={queued} skipped={skipped}")
    print(f"[done]   report  {config.DASH}")
    print(f"[done]   queue   {config.HUMANQ}")
    return 0


def _mark_contacted(state: dict, plan, draft: dict) -> None:
    h = state.setdefault("contacted", {}).setdefault(plan.target_id, {})
    h["last_ts"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    h["count"] = h.get("count", 0) + 1
    h["angle"] = draft["angle"]
    h["channel"] = plan.channel
    trig = plan.context.get("trigger")
    h["trigger"] = trig["type"] if trig else "keep_warm"


if __name__ == "__main__":
    sys.exit(main())

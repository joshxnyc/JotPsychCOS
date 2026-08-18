"""ORCHESTRATOR. One pass:
   read -> resolve -> watch -> decide -> draft -> QC -> send -> attribute -> report

Run:  python -m machine.run [--limit N] [--live]
"""
import argparse, os, sys, datetime
from . import compliance, config, db, digest, ledger, memory, qc, send, strategy, report

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    from . import settings as _settings
    ap.add_argument("--limit", type=int,
                    default=_settings.get_int("max_sends_per_run"))
    ap.add_argument("--live", action="store_true", help="actually send (overrides DRY_RUN)")
    ap.add_argument("--report-only", action="store_true")
    a = ap.parse_args(argv)
    if a.live:
        config.DRY_RUN = False

    state = memory.start_run(memory.load())
    ledger.set_run(state.get("run_count", 0))
    if a.report_only:
        report.build(state); memory.save(state); return 0

    # Everything a person can act on goes to the store. The files stay as they
    # were — they are what makes the machine inspectable — but the store is what
    # the web app reads and writes.
    conn = db.connect()
    run_id = db.start_run(conn, trigger=os.getenv("RUN_TRIGGER", "schedule"))

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

        d = compliance.apply(strategy.draft(plan, state))
        v = qc.check(d, plan.context)

        # A clinician handed to a person still gets a written email. The person
        # should be editing and sending, not composing from a bullet list — and
        # it goes through exactly the same checks as anything the machine sends.
        # source='run': a record the machine wrote back about someone it acted
        # on. Only uploads carry source='list', and only 'list' rows count as
        # the workspace audience — otherwise a file-based cycle would write its
        # three contacted clinicians into the store and the store would then
        # shadow the forty-person file on the very next cycle.
        cid = db.upsert_clinician(
            conn, name=plan.context.get("name", ""), email=plan.to,
            mobile=plan.context.get("mobile", ""), source="run",
            npi=plan.context.get("npi", ""), tier=plan.context.get("tier", ""),
            score=plan.context.get("score", 0))

        if v.ok and plan.action == "human_call":
            plan.context["draft"] = {"subject": d["subject"], "body": d["body"]}
            plan.context["draft_id"] = db.add_draft(
                conn, run_id=run_id, clinician_id=cid, kind="human_call",
                channel=plan.channel, angle=d["angle"], subject=d["subject"],
                body=d["body"], reason=plan.reason, status="staged",
                peer=(plan.context.get("peer") or {}).get("name", ""))
            human_queue.append(plan)
            ledger.append({"action": "human_call", "target_id": plan.target_id,
                           "reason": plan.reason, "subject": d["subject"],
                           "peer": (plan.context.get("peer") or {}).get("name", "")})
            queued += 1
            continue

        if not v.ok:
            db.add_draft(conn, run_id=run_id, clinician_id=cid, kind=plan.action,
                         channel=plan.channel, angle=d["angle"], subject=d["subject"],
                         body=d["body"], reason=plan.reason, status="blocked",
                         qc=__import__("json").dumps(v.as_dict()))
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

        # Autopilot is the design: a message that passed every check sends on
        # its own, and the person's hours go to the queue, not to re-reading
        # what the checks already read. Review mode is the deliberate opt-out.
        autopilot = _settings.get("approval_mode") != "review"
        will_send = config.SEND_TO_CLINICIANS and autopilot
        db.add_draft(conn, run_id=run_id, clinician_id=cid, kind=plan.action,
                     channel=plan.channel, angle=d["angle"], subject=d["subject"],
                     body=d["body"], reason=plan.reason,
                     status="sent" if will_send else "staged")
        if not autopilot and config.SEND_TO_CLINICIANS:
            # review mode with sending on: hold it for a person instead
            ledger.append({"action": "staged", "target_id": plan.target_id,
                           "angle": d["angle"], "plan_action": plan.action,
                           "subject": d["subject"], "reason": plan.reason})
            memory.record(state, d["angle"], "sent")
            _mark_contacted(state, plan, d)
            sent += 1
            print(f"[hold]   awaiting approval -> {d['subject']}")
            continue
        r = send.deliver(d, plan.channel)
        ledger.append({"action": ("staged" if not config.SEND_TO_CLINICIANS
                                  else "sent") if r.ok else "send_failed",
                       "target_id": plan.target_id, "angle": d["angle"],
                       "plan_action": plan.action, "channel": r.get("channel"),
                       "to": r.get("to"), "subject": d["subject"],
                       "reason": plan.reason, "warnings": v.warnings,
                       "claims": d.get("claims", []), "error": r.get("error")})
        if r.ok:
            memory.record(state, d["angle"], "sent")
            _mark_contacted(state, plan, d)
            sent += 1
            print(f"[{'send' if config.SEND_TO_CLINICIANS else 'stage'}]  "
                  f"{r.get('channel')} -> {r.get('to')} :: {d['subject']}")
        else:
            print(f"[send]   FAILED {r.get('error')}")

    # The queue is state, not just a markdown file, so the dashboard can show
    # what needs a person without re-deriving it.
    state["queue"] = [{
        "target_id": p.target_id, "name": p.context.get("name", ""),
        "email": p.to, "tier": p.context.get("tier", ""), "score": p.context.get("score", 0),
        "why": (p.context.get("trigger") or {}).get("detail", ""),
        "peer": (p.context.get("peer") or {}).get("name", ""),
        "peer_line": (p.context.get("peer") or {}).get("attestation", ""),
        "subject": (p.context.get("draft") or {}).get("subject", ""),
        "body": (p.context.get("draft") or {}).get("body", ""),
        "peer_role": " — ".join(x for x in ((p.context.get("peer") or {}).get("specialty", ""),
                                            (p.context.get("peer") or {}).get("state", "")) if x),
    } for p in human_queue]
    # The output that leaves on every cycle: a report to the operator. The
    # machine reports to a person by default and writes to clinicians only when
    # someone has deliberately turned that on.
    if config.SEND_DIGEST:
        dg = digest.send_report(state, human_queue)
        print(f"[digest] {dg.get('channel')} -> {dg.get('to')} "
              f"{'' if dg.ok else dg.get('error', '')}")
        ledger.append({"action": "digest", "target_id": "operator",
                       "reason": f"run summary to {dg.get('to')}",
                       "channel": dg.get("channel")})

    report.write_human_queue(human_queue, state)
    report.build(state)
    memory.save(state)
    db.end_run(conn, run_id, {"staged": sent, "blocked": blocked, "silent": silent,
                              "human_queue": queued, "skipped": skipped})
    db.log(conn, "run_finished", detail=f"run {run_id}: {sent} ready, {blocked} blocked")
    conn.close()
    verb = "sent" if config.SEND_TO_CLINICIANS else "staged"
    print(f"\n[done]   {verb}={sent} blocked={blocked} silent={silent} "
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

"""THE DECISION. What to do about each dormant clinician, and why.

The brief asks two questions: keep them hearing from JotPsych until they are
ready, and know when that moment arrives. This module answers both, and its
most common answer is silence.

That is deliberate. At thousands of clinicians, a machine that writes to
everyone on a cadence is a newsletter, and a newsletter is how a brand gets
tuned out by exactly the audience it needs. So the default is to say nothing,
and a message has to be earned — by a change in the public record that means
this clinician's software question genuinely reopened.

    load_inputs()          -> everything read from the world
    decide(inputs, state)  -> a plan per clinician, each with a one-line reason
    draft(plan, state)     -> the message itself
"""
import csv, datetime, hashlib, re
from dataclasses import dataclass, field, asdict

import yaml

from . import config, io_input, llm, memory, resolve, watch

RULES = yaml.safe_load((config.CONFIG / "guardrails.yaml").read_text())
FACTS = (config.CONFIG / "fact_pack.md").read_text()
BRAND = (config.CONFIG / "brand.md").read_text()

# What we can honestly say, mapped to the situation that makes it relevant.
ANGLES = {
    "no_migration": "You do not have to leave the system you are on. It runs alongside it.",
    "denials":      "Claims and notes are checked against payer rules before they go out.",
    "audit":        "Notes that hold up when a payer asks for them.",
    "time_back":    "The documentation time comes back.",
    "scaling":      "Consistency across a team that just got bigger.",
}

# Which angle fits which moment. Memory reweights within this, it does not
# override it — a clinician who just moved state should not get a scaling pitch.
ANGLE_FOR_TRIGGER = {
    "became_organization":  ["scaling", "no_migration", "audit"],
    "practice_move_state":  ["no_migration", "denials", "audit"],
    "practice_move":        ["no_migration", "time_back"],
    "practice_renamed":     ["scaling", "no_migration"],
    "taxonomy_change":      ["denials", "audit"],
    "newly_enumerated":     ["time_back", "no_migration"],
    "registry_touched":     ["no_migration"],
    "_keep_warm":           ["denials", "audit", "time_back"],
}

KEEP_WARM_DAYS = 90        # how long before a quiet clinician hears from us again
RUNS_PER_CYCLE = 20        # keep-warm is spread evenly across this many runs
MOMENT_COOLDOWN_DAYS = 30  # never two moment-messages inside a month
HUMAN_QUEUE_MAX = 10       # the human's month, capped so it stays 1-2 hours


@dataclass
class Plan:
    target_id: str
    to: str
    angle: str
    reason: str
    action: str = "moment"          # moment | keep_warm | human_call | silence
    channel: str = "email"          # email | sms
    context: dict = field(default_factory=dict)
    def dict(self): return asdict(self)


# ------------------------------------------------------------------ input ---
def _tid(email: str) -> str:
    return hashlib.sha1(email.strip().lower().encode()).hexdigest()[:12]

def load_inputs() -> dict:
    """Everything the machine reads and did not write.

    Swap the real list in by dropping inbox/dormant.csv next to the sample.
    Columns are the contract: name, email, mobile. Nothing else is required."""
    dormant = io_input.read_csv("dormant.csv") or io_input.read_csv("dormant.sample.csv")
    peers   = io_input.read_csv("peers.csv")   or io_input.read_csv("peers.sample.csv")
    returns = io_input.read_csv("returns.csv") or io_input.read_csv("returns.sample.csv")
    suppress= io_input.read_csv("suppress.csv")or io_input.read_csv("suppress.sample.csv")
    for r in dormant:
        r["target_id"] = _tid(r.get("email", ""))
    return {"dormant": dormant, "peers": peers, "returns": returns,
            "suppress": suppress}


# --------------------------------------------------------------- decision ---
def decide(inputs: dict, state: dict) -> list[Plan]:
    run_id = f"run{state.get('run_count', 0)}"
    blocked = {r["email"].strip().lower() for r in inputs["suppress"] if r.get("email")}

    by_email_all = {r["target_id"]: r for r in inputs["dormant"]}

    # 1. Three fields -> a verified practice profile, or an honest refusal.
    resolutions = {}
    for row in inputs["dormant"]:
        if row.get("email", "").strip().lower() in blocked:
            continue
        resolutions[row["target_id"]] = resolve.resolve(row, RULES)
    state.setdefault("resolution_scores", {}).update(
        {t: {"score": r["score"], "tier": r["tier"]} for t, r in resolutions.items()})

    # The roster is what the dashboard shows as "the data": every clinician the
    # machine knows about, what it worked out about them, and how sure it is.
    roster = state.setdefault("roster", {})
    for tid, r in resolutions.items():
        row, reg = by_email_all[tid], r.get("registry", {})
        roster[tid] = {
            "name": row.get("name", ""), "email": row.get("email", ""),
            "mobile": row.get("mobile", ""),
            "tier": r["tier"], "score": r["score"], "npi": r.get("npi", ""),
            "specialty": reg.get("taxonomy", ""), "state_code": reg.get("state", ""),
            "city": reg.get("city", ""), "candidates": r.get("candidates", 0),
            "signals": r.get("signals", []),
            "mobile_state": r.get("mobile_state", ""),
        }

    # 2. What changed since last run. This is the whole readiness detector.
    triggers = watch.observe(resolutions, run_id)

    # 3. Attribute returns before deciding, so a clinician who already came back
    #    is never written to again.
    returned = _attribute(inputs, state)

    plans, contacted = [], state.setdefault("contacted", {})
    by_email = {r["target_id"]: r for r in inputs["dormant"]}

    for tid, res in resolutions.items():
        row = by_email[tid]
        hist = contacted.get(tid, {})
        days = _days_since(hist.get("last_ts"))

        if tid in returned:
            plans.append(_silence(tid, row, "already came back — the machine stops here"))
            continue

        # A change in the registry only means something if we are confident the
        # record is actually theirs. Below the threshold the change may belong
        # to a same-named stranger, and acting on it would be worse than silence.
        trig = (watch.best_trigger(triggers.get(tid, []))
                if res["tier"] in ("verified", "probable") else None)
        if triggers.get(tid) and trig is None:
            plans.append(_silence(tid, row,
                f"registry change seen but identity only {res['tier']} at "
                f"{res['score']} — cannot attribute the change to this person"))
            continue

        if trig and days is not None and days < MOMENT_COOLDOWN_DAYS:
            plans.append(_silence(tid, row,
                f"{trig['type']} detected but last contacted {days}d ago — inside cooldown"))
            continue

        if trig:
            peer = _match_peer(res, inputs["peers"])
            # The strongest signals with a credible peer are worth a person, not
            # an email. That is what the human's monthly hours are for.
            action = "human_call" if (trig["weight"] >= 85 and peer) else "moment"
            angle = _pick_angle(state, ANGLE_FOR_TRIGGER.get(trig["type"], ["no_migration"]))
            plans.append(Plan(
                target_id=tid, to=row.get("email", ""), angle=angle, action=action,
                channel=_channel(tid, state),
                reason=(f"{trig['type']}: {trig['detail']} "
                        f"({trig['field']} {trig['before']!r} -> {trig['after']!r}); "
                        f"identity {res['tier']} at {res['score']}; angle {angle}"),
                context=_context(row, res, trig, peer)))
            continue

        if days is None or days >= KEEP_WARM_DAYS:
            # Due is not the same as due today. Each clinician gets a fixed slot
            # in the cycle, derived from their own id, so the quarterly touch is
            # spread evenly instead of arriving as one blast. At 15,000 names
            # that is the difference between a campaign and a machine.
            if not _in_slot(tid, state):
                plans.append(_silence(tid, row,
                    "due for keep-warm but not in this run's slot — staggered "
                    f"across {RUNS_PER_CYCLE} runs to avoid a blast"))
                continue
            angle = _pick_angle(state, ANGLE_FOR_TRIGGER["_keep_warm"])
            plans.append(Plan(
                target_id=tid, to=row.get("email", ""), angle=angle, action="keep_warm",
                channel="email",
                reason=(f"no registry change; last contact "
                        f"{'never' if days is None else str(days) + 'd ago'} "
                        f">= {KEEP_WARM_DAYS}d — quarterly keep-warm; "
                        f"identity {res['tier']} at {res['score']}; angle {angle}"),
                context=_context(row, res, None, None)))
            continue

        plans.append(_silence(tid, row,
            f"no registry change and contacted {days}d ago — nothing to say"))

    # Highest-value first, and cap the human's queue so the month stays 1-2 hours.
    plans.sort(key=lambda p: (p.action != "human_call", p.action != "moment"))
    for extra in [p for p in plans if p.action == "human_call"][HUMAN_QUEUE_MAX:]:
        extra.action = "moment"
        extra.reason += " | human queue full this cycle, downgraded to a message"
    return plans


def _silence(tid: str, row: dict, why: str) -> Plan:
    return Plan(target_id=tid, to=row.get("email", ""), angle="none",
                action="silence", reason=why, context={})

def _context(row: dict, res: dict, trig: dict | None, peer: dict | None) -> dict:
    reg = res.get("registry", {})
    allowed = RULES["tier_permissions"][res["tier"]]
    facts = {}
    if "specialty" in allowed: facts["specialty"] = reg.get("taxonomy", "")
    if "state" in allowed:     facts["state"] = reg.get("state", "")
    if "city" in allowed:      facts["city"] = reg.get("city", "")
    # What the drafter is NOT allowed to say. QC checks the draft against this
    # independently, so an over-reaching model is caught rather than trusted.
    forbidden = {k: v for k, v in (("specialty", reg.get("taxonomy", "")),
                                   ("state", reg.get("state", "")),
                                   ("city", reg.get("city", "")),
                                   ("practice_name", reg.get("name", "")))
                 if v and k not in allowed}
    # True of every row on this list by definition — it is what "dormant" means,
    # and it is the one thing we know without the registry. The judge was right
    # to reject it while it was missing from the record.
    first = (res.get("first") or "").strip(".")
    return {"name": row.get("name", ""),
            "first_name": first if len(first) > 1 else "",
            "known_relationship": ("they signed up for JotPsych at some point and "
                                   "did not become a paying customer"),
            "tier": res["tier"], "score": res["score"],
            "forbidden_facts": forbidden,
            "npi": res.get("npi", ""), "signals": res.get("signals", []),
            "allowed_facts": facts, "tier_permissions": allowed,
            "registry_verified": res["tier"] in ("verified", "probable"),
            "trigger": trig, "peer": peer,
            "must_not_mention": ["NPI", "registry", "records"]}

def _pick_angle(state: dict, candidates: list[str]) -> str:
    """Memory chooses within what the situation permits. The machine leans on
    the angle that has actually produced returns, not replies."""
    w = memory.angle_weights(state, candidates)
    return max(candidates, key=lambda a: w.get(a, 0))

def _channel(tid: str, state: dict) -> str:
    """A mobile number is not consent to text. SMS unlocks only after the
    clinician has engaged with us first."""
    if not RULES["sms"]["requires_prior_engagement"]:
        return "sms"
    engaged = state.get("engaged", {}).get(tid)
    return "sms" if engaged else "email"

def _match_peer(res: dict, peers: list[dict]) -> dict | None:
    """The runner-up concept, demoted to where it belongs: a human action.
    Only consenting peers, and only a real specialty-and-state fit."""
    reg = res.get("registry", {})
    tax, st = (reg.get("taxonomy") or "").lower(), reg.get("state", "")
    best, best_score = None, 0
    for p in peers:
        if (p.get("consent") or "").strip().lower() != "yes":
            continue
        s = 0
        if p.get("state") and p["state"] == st: s += 3
        if p.get("specialty") and p["specialty"].lower().split(",")[0] in tax: s += 4
        if s > best_score:
            best, best_score = p, s
    return best if best_score >= 4 else None

def _in_slot(tid: str, state: dict) -> bool:
    return int(tid[:8], 16) % RUNS_PER_CYCLE == state.get("run_count", 0) % RUNS_PER_CYCLE

def _days_since(ts: str | None) -> int | None:
    if not ts:
        return None
    try:
        d = datetime.datetime.fromisoformat(ts)
    except ValueError:
        return None
    return (datetime.datetime.now(datetime.timezone.utc) - d).days

def _attribute(inputs: dict, state: dict) -> set[str]:
    """Join the returns feed to what the machine actually sent. This is how a
    clinician coming back is traced to the machine rather than assumed."""
    contacted = state.get("contacted", {})
    returns = state.setdefault("returns", {})
    seen = set()
    for r in inputs["returns"]:
        tid = _tid(r.get("email", ""))
        seen.add(tid)
        if tid in returns:
            continue
        hist = contacted.get(tid)
        returns[tid] = {
            "event": r.get("event", ""), "date": r.get("date", ""),
            "attributed": bool(hist),
            "angle": (hist or {}).get("angle", ""),
            "trigger": (hist or {}).get("trigger", ""),
            "touches": (hist or {}).get("count", 0),
        }
        if hist:                       # the angle that produced a return is the
            memory.record(state, hist.get("angle", "unknown"), "replied")
    return seen


# ---------------------------------------------------------------- drafting --
DRAFT_SYSTEM = """You write for JotPsych. You are writing one message to one \
licensed behavioral-health clinician who tried JotPsych once and did not buy.

You will be given a FACT PACK, a VOICE spec, and a RECIPIENT RECORD.

Absolute rules:
- Assert nothing about JotPsych that is not in the FACT PACK.
- Assert nothing about the recipient that is not in ALLOWED FACTS or KNOWN
  RELATIONSHIP. If a fact is not there, you do not know it. Do not guess, infer
  or hedge toward it. In particular you do not know their practice size, their
  current software, why they left, or anything about their patients.
- Do not characterise their specialty's documentation burden unless the FACT
  PACK says something about it. Speak about JotPsych, not about their field.
- Never address anyone by an initial. If no first name is given, use none.
- NEVER say or imply how we know anything about them. Do not mention records,
  registries, listings, or that you noticed anything. Write to the situation.
- No clinical, reimbursement or audit-outcome guarantees.
- Follow the VOICE spec exactly, including the banned register.
- End with a plain-language way to stop hearing from us.

Return JSON only:
{"subject": string, "body": string, "claims": [string]}
"claims" lists every factual assertion you made about JotPsych, so it can be
checked against the fact pack."""

def draft(plan: Plan, state: dict) -> dict:
    ctx = plan.context
    trig = ctx.get("trigger")
    situation = (trig["detail"] if trig else
                 "nothing about their practice has visibly changed; this is a "
                 "quarterly keep-warm message")
    peer = ctx.get("peer")
    user = f"""FACT PACK
---
{FACTS}

VOICE
---
{BRAND}

RECIPIENT RECORD
---
Name: {ctx.get('name')}
First name you may use: {ctx.get('first_name') or 'NONE — we only have an initial. Do not address them by a first name at all.'}
Known relationship (true of everyone on this list): {ctx.get('known_relationship')}
Identity confidence: {ctx.get('tier')} (score {ctx.get('score')})
ALLOWED FACTS (the only things you may say about them): {ctx.get('allowed_facts') or 'none'}
Situation you are writing into (DO NOT REPEAT THIS BACK TO THEM, it is why you
are writing, not something they told you): {situation}
Angle to take: {plan.angle} — {ANGLES.get(plan.angle, '')}
{"A peer who has agreed to speak to them: " + peer['name'] + ', ' + peer['credential'] + ', ' + peer['specialty'] + ' in ' + peer['state'] if peer else ""}

Write the message. Under 140 words."""
    try:
        out = llm.complete_json(DRAFT_SYSTEM, user, temperature=0.5)
    except Exception as e:
        out = {"subject": "", "body": "", "claims": [], "_error": str(e)}
    return {"to": plan.to, "subject": (out.get("subject") or "").strip(),
            "body": (out.get("body") or "").strip(), "angle": plan.angle,
            "claims": out.get("claims", []), "action": plan.action,
            "channel": plan.channel}

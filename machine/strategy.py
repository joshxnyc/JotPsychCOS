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
import csv, datetime, hashlib, os, re
from dataclasses import dataclass, field, asdict

import yaml

from . import config, io_input, llm, memory, resolve, watch

RULES = yaml.safe_load((config.CONFIG / "guardrails.yaml").read_text())
FACTS = (config.CONFIG / "fact_pack.md").read_text()
BRAND = (config.CONFIG / "brand.md").read_text()

# What we can honestly say, mapped to the situation that makes it relevant.
ANGLE_NAME = {
    "no_migration": "no migration needed",
    "denials": "payer rules and denials",
    "audit": "notes that survive an audit",
    "time_back": "documentation time back",
    "scaling": "consistency across a growing team",
}

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

# At 15,000 clinicians, resolving everyone every run would mean 15,000 federal
# API calls per pass. It would also be pointless: a practice does not move twice
# a week. So each run re-reads the registry for the staleest slice of the list
# and reuses the stored profile for everyone else. The whole list stays fresh on
# a rolling basis, and the cost per run is flat no matter how long the list is.
RESOLVE_BUDGET = int(os.getenv("RESOLVE_BUDGET_PER_RUN") or 400)
RESOLVE_TTL_DAYS = int(os.getenv("RESOLVE_TTL_DAYS") or 14)
MOMENT_COOLDOWN_DAYS = 30  # never two moment-messages inside a month
HUMAN_QUEUE_MAX = 10       # the human's month, capped so it stays 1-2 hours


TIER_WORD = {"verified": "we are confident who they are",
             "probable": "they are likely the right person",
             "unresolved": "we could not identify them"}


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
    dormant  = io_input.read_source("dormant",  "DORMANT_URL")
    peers    = io_input.read_source("peers",    "PEERS_URL")
    returns  = io_input.read_source("returns",  "RETURNS_URL")
    suppress = io_input.read_source("suppress", "SUPPRESS_URL")
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
    #    Only the staleest slice is re-read from the registry this run; the rest
    #    reuse the stored profile, so cost per run does not grow with the list.
    roster = state.setdefault("roster", {})
    live = [r for r in inputs["dormant"]
            if r.get("email", "").strip().lower() not in blocked]
    due = sorted(live, key=lambda r: (roster.get(r["target_id"], {}).get("resolved_at") or ""))
    fresh_cutoff = (datetime.datetime.now(datetime.timezone.utc)
                    - datetime.timedelta(days=RESOLVE_TTL_DAYS)).isoformat()

    resolutions, profiles, reread = {}, {}, 0
    for row in due:
        tid = row["target_id"]
        cached = roster.get(tid)
        stale = not cached or (cached.get("resolved_at") or "") < fresh_cutoff
        if stale and reread < RESOLVE_BUDGET:
            r = resolve.resolve(row, RULES)
            resolutions[tid] = r          # only fresh reads can reveal a change
            profiles[tid] = r
            reread += 1
        elif cached:
            profiles[tid] = {"tier": cached["tier"], "score": cached["score"],
                             "npi": cached.get("npi", ""), "first": cached.get("first", ""),
                             "registry": cached.get("registry", {}),
                             "candidates": cached.get("candidates", 0),
                             "signals": cached.get("signals", [])}
    state["resolve_coverage"] = {
        "list_size": len(live), "reread_this_run": reread,
        "budget": RESOLVE_BUDGET, "ttl_days": RESOLVE_TTL_DAYS,
        "runs_for_full_sweep": -(-len(live) // max(RESOLVE_BUDGET, 1)),
        "profiled": len(profiles),
    }
    print(f"[resolve] re-read {reread} of {len(live)} from the registry "
          f"(budget {RESOLVE_BUDGET}); {len(profiles) - reread} reused from memory")
    state.setdefault("resolution_scores", {}).update(
        {t: {"score": r["score"], "tier": r["tier"]} for t, r in profiles.items()})

    # The roster is what the dashboard shows as "the data": every clinician the
    # machine knows about, what it worked out about them, and how sure it is.
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
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
            "first": r.get("first", ""), "registry": r.get("registry", {}),
            "resolved_at": now_iso,
        }

    # 2. What changed since last run. This is the whole readiness detector.
    triggers = watch.observe(resolutions, run_id)

    # 3. Attribute returns before deciding, so a clinician who already came back
    #    is never written to again.
    returned = _attribute(inputs, state)

    plans, contacted = [], state.setdefault("contacted", {})
    by_email = {r["target_id"]: r for r in inputs["dormant"]}

    for tid, res in profiles.items():
        row = by_email[tid]
        hist = contacted.get(tid, {})
        days = _days_since(hist.get("last_ts"))

        if tid in returned:
            plans.append(_silence(tid, row,
                "They already came back. The machine stops contacting them."))
            continue

        # A change in the registry only means something if we are confident the
        # record is actually theirs. Below the threshold the change may belong
        # to a same-named stranger, and acting on it would be worse than silence.
        trig = (watch.best_trigger(triggers.get(tid, []))
                if res["tier"] in ("verified", "probable") else None)
        if triggers.get(tid) and trig is None:
            plans.append(_silence(tid, row,
                f"Something changed in the registry, but {TIER_WORD[res['tier']]} "
                f"(score {res['score']}) — the change may belong to someone else "
                f"with the same name, so we act on nothing."))
            continue

        if trig and days is not None and days < MOMENT_COOLDOWN_DAYS:
            plans.append(_silence(tid, row,
                f"Their practice changed, but we wrote to them {days} days ago. "
                f"Waiting out the {MOMENT_COOLDOWN_DAYS}-day cooldown before writing again."))
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
                reason=(f"{trig['detail'].capitalize()} — "
                        f"{trig['field']} changed from “{trig['before']}” to "
                        f"“{trig['after']}”. {TIER_WORD[res['tier']].capitalize()} "
                        f"(score {res['score']}). Angle: {ANGLE_NAME.get(angle, angle)}."),
                context=_context(row, res, trig, peer)))
            continue

        if days is None or days >= KEEP_WARM_DAYS:
            # Due is not the same as due today. Each clinician gets a fixed slot
            # in the cycle, derived from their own id, so the quarterly touch is
            # spread evenly instead of arriving as one blast. At 15,000 names
            # that is the difference between a campaign and a machine.
            if not _in_slot(tid, state):
                plans.append(_silence(tid, row,
                    f"Due a quarterly note, but their turn falls on a different run. "
                    f"The list is spread across {RUNS_PER_CYCLE} runs so it never goes "
                    f"out as one blast."))
                continue
            angle = _pick_angle(state, ANGLE_FOR_TRIGGER["_keep_warm"])
            plans.append(Plan(
                target_id=tid, to=row.get("email", ""), angle=angle, action="keep_warm",
                channel="email",
                reason=(f"Nothing changed in their practice, and they were "
                        f"{'never contacted' if days is None else f'last contacted {days} days ago'}"
                        f" — due a quarterly note. {TIER_WORD[res['tier']].capitalize()} "
                        f"(score {res['score']}). Angle: {ANGLE_NAME.get(angle, angle)}."),
                context=_context(row, res, None, None)))
            continue

        plans.append(_silence(tid, row,
            f"Nothing changed in their practice and we wrote to them {days} days "
            f"ago. There is nothing worth saying."))

    # Highest-value first, and cap the human's queue so the month stays 1-2 hours.
    plans.sort(key=lambda p: (p.action != "human_call", p.action != "moment"))
    for extra in [p for p in plans if p.action == "human_call"][HUMAN_QUEUE_MAX:]:
        extra.action = "moment"
        extra.reason += (" The human queue was already full this cycle, so this "
                         "becomes a message instead of an introduction.")
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
INTRO_SYSTEM = """You write for JotPsych. Write the email a JotPsych person \
will send by hand to a clinician who tried JotPsych once and did not buy, \
offering to introduce them to a named peer who already uses it.

You will be given a FACT PACK, a VOICE spec, and a RECIPIENT RECORD including
the peer who has agreed to speak to them.

Absolute rules:
- The offer is an introduction to a specific named person. That is the whole ask.
- Quote the peer only using the exact attestation given. Never invent a quote.
- NEVER say or imply how we know anything about them. No records, no registries,
  no "I noticed". Write to the situation, not to the surveillance.
- Assert nothing about JotPsych outside the FACT PACK, nothing about the
  recipient outside ALLOWED FACTS and KNOWN RELATIONSHIP.
- No clinical, reimbursement or audit-outcome guarantees.
- It is signed by a real person and sent from their mailbox, so it may read
  slightly warmer than an automated message — but it still follows the VOICE spec.
- End with a plain way to decline.

Return JSON only: {"subject": string, "body": string, "claims": [string]}"""


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
    """Every plan that is not silence produces a real message. A clinician the
    machine hands to a person still gets a written email — the person should be
    editing and sending, not composing from a bullet list."""
    ctx = plan.context
    trig = ctx.get("trigger")
    situation = (trig["detail"] if trig else
                 "nothing about their practice has visibly changed; this is a "
                 "quarterly keep-warm message")
    peer = ctx.get("peer")
    # Built outside the f-string: it contains quotes, and the peer's words must
    # reach the model verbatim so it cannot paraphrase a real person.
    peer_block = ""
    if peer:
        quote = peer.get("attestation", "")
        peer_block = (
            f"PEER WHO HAS AGREED TO SPEAK TO THEM: {peer['name']}, "
            f"{peer['credential']}, {peer['specialty']} in {peer['state']}, "
            f"{peer.get('months_using', '?')} months on JotPsych.\n"
            f"Their exact words, which you may quote verbatim and may not alter: "
            f"{quote!r}")
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
{peer_block}

Write the message. Under 140 words."""
    system = INTRO_SYSTEM if plan.action == "human_call" else DRAFT_SYSTEM
    try:
        out = llm.complete_json(system, user, temperature=0.5)
    except Exception as e:
        out = {"subject": "", "body": "", "claims": [], "_error": str(e)}
    return {"to": plan.to, "subject": (out.get("subject") or "").strip(),
            "body": (out.get("body") or "").strip(), "angle": plan.angle,
            "claims": out.get("claims", []), "action": plan.action,
            "channel": plan.channel}

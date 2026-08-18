"""THE DECISION. This is the one file we rewrite once the brief appears.

The chassis calls exactly three functions. Keep the signatures, change the guts.

    load_inputs()          -> dict of everything read from the world
    decide(inputs, state)  -> list of Plan objects (who, why, what angle)
    draft(plan, state)     -> {'to','subject','body','angle','claims'}

Nothing else in the repo needs to change to swap the concept.
"""
from dataclasses import dataclass, field, asdict
from . import io_input, llm, memory

ANGLES = ["peer_proof", "time_saved", "audit_risk"]

@dataclass
class Plan:
    target_id: str
    to: str
    angle: str
    reason: str                       # why the machine chose this, in one line
    context: dict = field(default_factory=dict)
    def dict(self): return asdict(self)

# --------------------------------------------------------------------------
def load_inputs() -> dict:
    """Read input the machine did not write. Replace the filenames, not the shape."""
    prospects = io_input.read_csv("prospects.csv") or io_input.read_csv("prospects.sample.csv")
    advocates = io_input.read_csv("advocates.csv") or io_input.read_csv("advocates.sample.csv")
    prospects = io_input.enrich(prospects)          # live NPPES calls
    return {"prospects": prospects, "advocates": advocates}

def decide(inputs: dict, state: dict) -> list[Plan]:
    """Placeholder logic: match each prospect to the best-fitting advocate and
    pick the angle with the best historical reply rate. REWRITE ME."""
    plans, weights = [], memory.angle_weights(state, ANGLES)
    best_angle = max(weights, key=weights.get)
    for p in inputs["prospects"]:
        peer = _best_peer(p, inputs["advocates"])
        if not peer:
            continue
        plans.append(Plan(
            target_id=p["id"],
            to=p.get("email", ""),
            angle=best_angle,
            reason=(f"matched to {peer.get('name','peer')} "
                    f"({peer.get('specialty','')}, {peer.get('state','')}); "
                    f"angle {best_angle} @ {weights[best_angle]:.2f} historical reply rate"),
            context={"prospect": p, "peer": peer,
                     "registry_verified": p.get("registry_verified", False),
                     "must_mention": [peer.get("name", "")]},
        ))
    return plans

def _best_peer(prospect: dict, advocates: list[dict]) -> dict | None:
    reg = prospect.get("registry", {})
    def score(a):
        s = 0
        if a.get("state") and a["state"] == (prospect.get("state") or reg.get("state")): s += 3
        if a.get("specialty") and a["specialty"].lower() in (reg.get("taxonomy", "").lower()): s += 4
        if a.get("practice_size") == prospect.get("practice_size"): s += 2
        if a.get("ehr") and a["ehr"] == prospect.get("ehr"): s += 2
        return s
    ranked = sorted(advocates, key=score, reverse=True)
    return ranked[0] if ranked and score(ranked[0]) > 0 else (ranked[0] if ranked else None)

DRAFT_SYSTEM = """You write one short email from JotPsych to one behavioral-health clinician.

Hard rules:
- Only use facts present in FACT PACK and RECIPIENT RECORD. Invent nothing.
- 70-120 words. Plain text. One ask. No bullet lists. No emoji.
- Sound like a person at a 20-person company, not a marketing department.
- Never promise clinical, billing, or reimbursement outcomes.
Return JSON: {"subject": string, "body": string, "claims": [string]}
"claims" lists every factual assertion you made, so it can be checked."""

def draft(plan: Plan, state: dict) -> dict:
    import json as _json, pathlib
    from . import config
    facts = (config.CONFIG / "fact_pack.md").read_text()
    user = (f"FACT PACK\n---\n{facts}\n\nRECIPIENT RECORD\n---\n"
            f"{_json.dumps(plan.context, indent=2, default=str)[:4000]}\n\n"
            f"ANGLE: {plan.angle}\nWHY THIS RECIPIENT: {plan.reason}")
    if not llm.available():
        out = _fallback_draft(plan)          # keeps the loop provable with no key
    else:
        try:
            out = llm.complete_json(DRAFT_SYSTEM, user, temperature=0.5)
        except Exception as e:
            out = {"subject": "", "body": "", "claims": [], "error": str(e)}
    return {"to": plan.to, "angle": plan.angle,
            "subject": out.get("subject", ""), "body": out.get("body", ""),
            "claims": out.get("claims", [])}


def _fallback_draft(plan: "Plan") -> dict:
    """Deterministic, fact-pack-safe draft used when no LLM key is present.
    Not the product - just enough that the whole loop runs and can be inspected."""
    p = plan.context.get("prospect", {})
    a = plan.context.get("peer", {})
    first = p.get("first_name") or "there"
    state = p.get("state") or p.get("registry", {}).get("state") or "your state"
    body = (
        f"Hi {first} - {a.get('name','A clinician')} runs a "
        f"{a.get('practice_size','small')} {a.get('specialty','behavioral health')} "
        f"practice in {a.get('state', state)} and has used JotPsych for "
        f"{a.get('months_using','several')} months. Their words: "
        f"\"{a.get('attestation','it saves me time')}\" "
        f"You are at the {p.get('stage','early')} stage with us, so instead of another "
        f"demo I can put you two on a ten-minute call. No pitch, just a clinician in "
        f"your position telling you what it is actually like. Want the introduction?"
    )
    return {"subject": f"A {a.get('specialty','behavioral health')} clinician in {a.get('state', state)}",
            "body": body,
            "claims": [f"{a.get('name')} uses JotPsych",
                       f"{a.get('name')} practices in {a.get('state')}"]}

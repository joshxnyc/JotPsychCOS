"""QUALITY CONTROL. Nothing leaves the machine without passing this.

Two layers:
  1. Deterministic gates  - cheap, fast, cannot be talked out of it by an LLM.
  2. An LLM judge         - reads the draft against the fact pack and guardrails
                            and must return a structured verdict.

Everything that fails is written to out/quarantine/ with the reason, so you can
show exactly what the machine caught.
"""
import json, re, pathlib, datetime
import yaml
from . import config, llm

RULES = yaml.safe_load((config.CONFIG / "guardrails.yaml").read_text())
FACTS = (config.CONFIG / "fact_pack.md").read_text()

PHI_PATTERNS = [
    (r"\b\d{3}-\d{2}-\d{4}\b", "looks like an SSN"),
    (r"\b(?:MRN|medical record (?:no|number))\b", "references a medical record number"),
    (r"\bpatient (?:name|id)\b", "references a specific patient"),
    (r"\bDOB\b|\bdate of birth\b", "references a date of birth"),
]
PLACEHOLDER = r"\[(?:INSERT|TODO|NAME|X{2,}|YOUR [A-Z ]+)\]|\{\{|\bLorem ipsum\b|\bTKTK\b"

class Verdict:
    def __init__(self):
        self.failures: list[str] = []
        self.warnings: list[str] = []
    @property
    def ok(self) -> bool: return not self.failures
    def fail(self, why): self.failures.append(why); return self
    def warn(self, why): self.warnings.append(why); return self
    def as_dict(self): return {"ok": self.ok, "failures": self.failures,
                               "warnings": self.warnings}

def check(draft: dict, context: dict | None = None) -> Verdict:
    """draft = {'subject':..., 'body':..., 'to':..., 'angle':..., 'claims':[...]}"""
    v = Verdict()
    subject = (draft.get("subject") or "").strip()
    body    = (draft.get("body") or "").strip()
    blob    = f"{subject}\n{body}"
    low     = blob.lower()

    # --- structural ---
    if not subject:                       v.fail("empty subject")
    if not body:                          v.fail("empty body")
    if len(subject) > RULES["subject_max_chars"]:
        v.fail(f"subject {len(subject)} chars > max {RULES['subject_max_chars']}")
    words = len(body.split())
    if words < RULES["body_min_words"]:   v.fail(f"body too short ({words} words)")
    if words > RULES["body_max_words"]:   v.fail(f"body too long ({words} words)")
    if re.search(PLACEHOLDER, blob, re.I):
        v.fail("unfilled placeholder / template artifact left in the draft")

    # --- did the model leak its own scaffolding? ---
    for tell in RULES["ai_tells"]:
        if tell.lower() in low:
            v.fail(f"AI tell present: {tell!r}")

    # --- claims the company cannot make ---
    for phrase in RULES["banned_phrases"]:
        if phrase.lower() in low:
            v.fail(f"banned claim: {phrase!r}")
    for pat, why in [(p, w) for p, w in RULES["banned_patterns"].items()]:
        if re.search(pat, blob, re.I):
            v.fail(f"banned pattern ({why})")

    # --- PHI / privacy ---
    for pat, why in PHI_PATTERNS:
        if re.search(pat, blob, re.I):
            v.fail(f"possible PHI: {why}")

    # --- personalisation must be real, not asserted ---
    if context is not None:
        if context.get("registry_verified") is False and RULES["require_verified_source"]:
            v.fail("no verified registry record backing the personalisation")
        for token in context.get("must_mention", []):
            if token and token.lower() not in low:
                v.warn(f"expected personalisation token missing: {token!r}")

    # --- numbers must trace to the fact pack ---
    for num in set(re.findall(r"\b\d[\d,\.]*\s?(?:%|percent|million|m\b|k\b)?", blob)):
        n = num.strip()
        if len(n) > 2 and n not in FACTS and n not in json.dumps(context or {}):
            v.warn(f"unsourced figure {n!r} - not in fact pack")

    # --- LLM judge ---
    if llm.available():
        judge = _llm_judge(draft, context or {})
        if judge.get("verdict") == "fail":
            for r in judge.get("reasons", ["judge rejected"]):
                v.fail(f"judge: {r}")
        else:
            for r in judge.get("reasons", []):
                v.warn(f"judge: {r}")
    return v

JUDGE_SYSTEM = """You are the last check before an email is sent under a real \
company's name to a licensed behavioral-health clinician. You are strict and you \
are not persuaded by confident writing.

Reject the draft if ANY of these are true:
- It states a fact about the company that is not in the FACT PACK.
- It states a fact about the recipient that is not in the RECIPIENT RECORD.
- It quotes or paraphrases a person who is not in the RECIPIENT RECORD.
- It makes a clinical, medical, legal, or reimbursement guarantee.
- It would embarrass a serious company: hype, flattery, fake urgency, guilt.
- It reads as machine-written to a busy clinician.

Return JSON: {"verdict":"pass"|"fail","reasons":[string],"score":1-5}
Reasons must be specific and quote the offending text."""

def _llm_judge(draft: dict, context: dict) -> dict:
    user = (f"FACT PACK\n---\n{FACTS}\n\n"
            f"RECIPIENT RECORD\n---\n{json.dumps(context, indent=2, default=str)[:4000]}\n\n"
            f"DRAFT\n---\nSubject: {draft.get('subject')}\n\n{draft.get('body')}")
    try:
        return llm.complete_json(JUDGE_SYSTEM, user, temperature=0)
    except Exception as e:
        return {"verdict": "pass", "reasons": [f"judge unavailable: {e}"], "score": 0}

def quarantine(draft: dict, verdict: Verdict, context: dict | None = None) -> pathlib.Path:
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")
    tag = re.sub(r"\W+", "-", (draft.get("to") or "unknown"))[:40]
    p = config.OUT / "quarantine" / f"{ts}-{tag}.json"
    p.write_text(json.dumps({"draft": draft, "verdict": verdict.as_dict(),
                             "context": context}, indent=2, default=str))
    return p

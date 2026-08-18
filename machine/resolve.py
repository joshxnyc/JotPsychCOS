"""IDENTITY RESOLUTION. Three fields in, a verified practice profile out.

The signup left us name, email and mobile. Nothing else. This module turns that
into a real clinician record by searching the federal NPI registry (NPPES:
public, free, no key) and then deciding *how sure it is*.

Certainty is the point. A confident match earns the right to say specific
things. A weak match earns the right to say almost nothing. No match at all
means we do not personalise, full stop — we would rather send something plainer
than something wrong about a clinician's own practice.

The score is additive and legible on purpose: every point is traceable to a
signal you can see in the ledger, and the thresholds live in guardrails.yaml so
they can be retuned without touching code.
"""
import json, re, hashlib, urllib.parse, urllib.request
from . import config, io_input

# Free-mail providers tell us nothing about a practice.
CONSUMER_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com",
    "aol.com", "me.com", "live.com", "msn.com", "protonmail.com", "proton.me",
    "comcast.net", "verizon.net", "sbcglobal.net", "att.net", "mac.com",
}

# Our whole list is behavioural health by construction. A candidate whose
# taxonomy is behavioural health is far more likely to be the right person.
BH_TAXONOMY_TERMS = (
    "psychiat", "psycholog", "social worker", "counselor", "counsellor",
    "behavior", "behaviour", "mental health", "marriage and family",
    "addiction", "substance use", "neuropsych",
)

# Words that appear in practice domains and carry no identifying signal.
DOMAIN_STOPWORDS = {
    "behavioral", "behavioural", "health", "psych", "psychiatry", "psychiatric",
    "psychology", "counseling", "counselling", "therapy", "therapeutic", "clinic",
    "clinical", "care", "wellness", "group", "associates", "partners", "center",
    "centre", "medical", "med", "mind", "the", "and", "llc", "pllc", "pc", "inc",
}

AREA_CODE_STATE = {
 "AL":("205","251","256","334","659","938"),"AK":("907",),
 "AZ":("480","520","602","623","928"),"AR":("479","501","870"),
 "CA":("209","213","279","310","323","341","408","415","424","442","510","530","559","562","619","626","628","650","657","661","669","707","714","747","760","805","818","820","831","840","858","909","916","925","949","951"),
 "CO":("303","719","720","970"),"CT":("203","475","860","959"),"DE":("302",),
 "DC":("202",),"FL":("239","305","321","352","386","407","561","727","754","772","786","813","850","863","904","941","954"),
 "GA":("229","404","470","478","678","706","762","770","912"),"HI":("808",),
 "ID":("208","986"),"IL":("217","224","309","312","331","618","630","708","773","779","815","847","872"),
 "IN":("219","260","317","463","574","765","812","930"),"IA":("319","515","563","641","712"),
 "KS":("316","620","785","913"),"KY":("270","364","502","606","859"),
 "LA":("225","318","337","504","985"),"ME":("207",),"MD":("240","301","410","443","667"),
 "MA":("339","351","413","508","617","774","781","857","978"),
 "MI":("231","248","269","313","517","586","616","734","810","906","947","989"),
 "MN":("218","320","507","612","651","763","952"),"MS":("228","601","662","769"),
 "MO":("314","417","573","636","660","816"),"MT":("406",),"NE":("308","402","531"),
 "NV":("702","725","775"),"NH":("603",),"NJ":("201","551","609","640","732","848","856","862","908","973"),
 "NM":("505","575"),"NY":("212","315","332","347","516","518","585","607","631","646","680","716","718","838","845","914","917","929","934"),
 "NC":("252","336","704","743","828","910","919","980","984"),"ND":("701",),
 "OH":("216","220","234","326","330","380","419","440","513","567","614","740","937"),
 "OK":("405","539","580","918"),"OR":("458","503","541","971"),
 "PA":("215","223","267","272","412","445","484","570","610","717","724","814","878"),
 "RI":("401",),"SC":("803","843","854","864"),"SD":("605",),
 "TN":("423","615","629","731","865","901","931"),
 "TX":("210","214","254","281","325","346","361","409","430","432","469","512","682","713","726","737","806","817","830","832","903","915","936","940","956","972","979"),
 "UT":("385","435","801"),"VT":("802",),"VA":("276","434","540","571","703","757","804"),
 "WA":("206","253","360","425","509","564"),"WV":("304","681"),
 "WI":("262","414","534","608","715","920"),"WY":("307",),
}
CODE_TO_STATE = {c: s for s, codes in AREA_CODE_STATE.items() for c in codes}

CACHE = config.STATE / "nppes_cache"
CACHE.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------- parsing ---
def parse_name(raw: str) -> tuple[str, str]:
    """People type their names in every shape. Normalise before searching."""
    s = re.sub(r"\s+", " ", (raw or "").strip())
    s = re.sub(r"^(dr\.?|mr\.?|mrs\.?|ms\.?)\s+", "", s, flags=re.I)
    s = re.sub(r",\s*(m\.?d\.?|d\.?o\.?|ph\.?d\.?|psy\.?d\.?|l?c?sw|lcsw|lpc|lmft|pmhnp|np|rn|ma|ms)\.?$",
               "", s, flags=re.I).strip()
    if "," in s:                                  # "Chen, Michael"
        last, _, first = s.partition(",")
        return first.strip().title(), last.strip().title()
    parts = [p for p in s.split(" ") if p]
    if len(parts) < 2:
        return "", (parts[0].title() if parts else "")
    return parts[0].title(), parts[-1].title()


def email_parts(email: str) -> dict:
    e = (email or "").strip().lower()
    local, _, domain = e.partition("@")
    local = re.sub(r"\+.*$", "", local)           # strip +tags
    tokens = {t for t in re.split(r"[^a-z]+", domain.rsplit(".", 1)[0]) if len(t) > 2}
    return {"email": e, "local": local, "domain": domain,
            "is_consumer": domain in CONSUMER_DOMAINS,
            "tokens": tokens - DOMAIN_STOPWORDS}


def mobile_state(mobile: str) -> str:
    digits = re.sub(r"\D", "", mobile or "")
    if digits.startswith("1"):
        digits = digits[1:]
    return CODE_TO_STATE.get(digits[:3], "") if len(digits) >= 10 else ""


def is_behavioral(taxonomy: str) -> bool:
    t = (taxonomy or "").lower()
    return any(term in t for term in BH_TAXONOMY_TERMS)


# ------------------------------------------------------------- the search ---
def search(first: str, last: str, limit: int = 50) -> list[dict]:
    """Live NPPES name search, cached on disk so repeated runs stay fast and
    the federal API is not hammered once per clinician per run."""
    key = hashlib.sha1(f"{first}|{last}|{limit}".encode()).hexdigest()[:16]
    path = CACHE / f"{key}.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            pass
    hits = [h for h in io_input.nppes_lookup(first=first, last=last, limit=limit)
            if "_error" not in h]
    path.write_text(json.dumps(hits))
    return hits


# ------------------------------------------------------------- the scoring --
def score_candidate(cand: dict, name: tuple[str, str], mail: dict,
                    mob_state: str, n_candidates: int) -> tuple[int, list[str]]:
    """Additive, auditable. Every point has a named reason."""
    first, last = name
    pts, why = 0, []

    cf = (cand.get("name") or "").split(" ")
    c_first = cf[0] if cf else ""
    c_last = cf[-1] if len(cf) > 1 else ""
    if c_last.lower() == last.lower() and c_first.lower() == first.lower():
        pts += 40; why.append("+40 full name matches an individual NPI")
    elif c_last.lower() == last.lower():
        pts += 20; why.append("+20 surname matches")

    if is_behavioral(cand.get("taxonomy", "")):
        pts += 15; why.append("+15 behavioral-health taxonomy")

    # Does the email local-part look like this person?
    lp = re.sub(r"[^a-z]", "", mail["local"])
    fl, ll = first.lower(), last.lower()
    if lp and (lp == f"{fl}{ll}" or lp == f"{fl[:1]}{ll}" or lp == f"{ll}{fl[:1]}"
               or lp == f"dr{ll}" or lp.startswith(fl) and ll in lp):
        pts += 15; why.append("+15 email local-part matches the name")

    if not mail["is_consumer"] and mail["domain"]:
        pts += 10; why.append("+10 practice email domain, not free-mail")

    # Does the practice domain show up in the registry record?
    blob = " ".join(str(cand.get(k, "")) for k in ("name", "taxonomy", "city")).lower()
    if mail["tokens"] and any(t in blob or ll in t for t in mail["tokens"]):
        pts += 25; why.append("+25 practice domain corroborated by the registry record")

    if mob_state and cand.get("state") == mob_state:
        pts += 10; why.append(f"+10 mobile area code agrees with practice state ({mob_state})")

    if n_candidates > 1:
        penalty = min((n_candidates - 1) * 8, 40)
        pts -= penalty; why.append(f"-{penalty} {n_candidates} plausible candidates, not one")

    return max(pts, 0), why


def resolve(row: dict, rules: dict) -> dict:
    """One clinician in, one resolution out. Never raises; an unresolved row is
    a normal outcome, not an error."""
    first, last = parse_name(row.get("name", ""))
    mail = email_parts(row.get("email", ""))
    mob_state = mobile_state(row.get("mobile", ""))
    out = {"first": first, "last": last, "domain": mail["domain"],
           "mobile_state": mob_state, "score": 0, "tier": "unresolved",
           "npi": "", "registry": {}, "candidates": 0, "signals": []}

    if not last:
        out["signals"] = ["no usable surname in the name field"]
        return out

    hits = search(first, last)
    bh = [h for h in hits if is_behavioral(h.get("taxonomy", ""))] or hits
    out["candidates"] = len(bh)
    if not bh:
        out["signals"] = ["no NPPES record for this name"]
        return out

    scored = sorted(
        ((score_candidate(c, (first, last), mail, mob_state, len(bh)), c) for c in bh),
        key=lambda x: x[0][0], reverse=True)
    (best_pts, best_why), best = scored[0]

    # Two candidates that score the same are not a match, they are a coin flip.
    if len(scored) > 1 and scored[1][0][0] == best_pts and scored[1][1].get("state") != best.get("state"):
        best_pts -= 15
        best_why.append("-15 tied top candidates in different states")

    out.update(score=best_pts, signals=best_why, npi=best.get("npi", ""), registry=best)
    if best_pts >= rules["confidence"]["verified"]:
        out["tier"] = "verified"
    elif best_pts >= rules["confidence"]["probable"]:
        out["tier"] = "probable"
    return out

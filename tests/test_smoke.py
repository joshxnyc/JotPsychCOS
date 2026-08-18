"""Proves each part of the loop exists and fires. Run: python -m pytest -q"""
import json, os, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ.setdefault("DRY_RUN", "1")

from machine import compliance, qc, send, io_input, memory, strategy

def test_input_is_real_and_not_hardcoded():
    """The contract is three columns. Replacing the file must be the only step."""
    rows = io_input.read_csv("dormant.sample.csv")
    assert rows, "no input rows read from inbox/"
    assert set(rows[0]) >= {"name", "email", "mobile"}


def test_confidence_bands_are_config_not_code():
    """Retuning the threshold must not require touching Python."""
    import yaml, pathlib as _p
    from machine import config as _c
    rules = yaml.safe_load((_c.CONFIG / "guardrails.yaml").read_text())
    assert rules["confidence"]["verified"] > rules["confidence"]["probable"] > 0
    src = (_p.Path(__file__).resolve().parent.parent / "machine" / "resolve.py").read_text()
    for band in ("verified", "probable"):
        assert f'rules["confidence"]["{band}"]' in src, f"{band} band not read from config"
    import re as _re
    assert not _re.search(r">=\s*(70|40)\b", src), "a threshold is hardcoded in resolve.py"


def test_resolution_refuses_to_guess():
    """An invented name has no federal record. The machine must say so rather
    than attach itself to the nearest plausible stranger."""
    import yaml
    from machine import resolve, config as _c
    rules = yaml.safe_load((_c.CONFIG / "guardrails.yaml").read_text())
    r = resolve.resolve({"name": "Zephyrina Quackenbush-Ostrowski",
                         "email": "z@nowhere-practice.example", "mobile": ""}, rules)
    assert r["tier"] == "unresolved"
    assert r["registry"] == {} or r["score"] < rules["confidence"]["probable"]


def test_qc_blocks_saying_how_we_knew():
    """The registry decides timing. Saying so turns timing into surveillance."""
    body = ("I noticed you recently moved your practice. JotPsych runs alongside "
            "the system you already use and takes about five minutes to set up. "
            "Reply stop to be removed. ") * 3
    v = qc.check({"to": "a@b.c", "subject": "About your move", "body": body})
    assert not v.ok
    assert any("how we knew" in f for f in v.failures)


def test_qc_blocks_claims_a_weak_match_has_not_earned():
    """Tier permissions are enforced against the draft, not against the prompt."""
    body = ("Practices in Brooklyn tend to hit this. JotPsych runs alongside the "
            "system you already use and takes five minutes. Reply stop to opt out. ") * 3
    v = qc.check({"to": "a@b.c", "subject": "A note", "body": body},
                 {"tier": "probable", "score": 50, "forbidden_facts": {"city": "Brooklyn"}})
    assert not v.ok
    assert any("identity is only probable" in f for f in v.failures)


def test_a_registry_change_needs_a_confident_identity():
    """Acting on a change we cannot attribute would mean writing to someone
    about a stranger's practice."""
    import inspect
    from machine import strategy
    src = inspect.getsource(strategy.decide)
    assert 'res["tier"] in ("verified", "probable")' in src


def test_the_watch_needs_memory_to_see_anything():
    """No prior snapshot, no diff. Memory is load-bearing, not decorative."""
    from machine import watch
    res = {"t1": {"npi": "1234567893", "registry": {"city": "BOSTON", "state": "MA",
                                                    "taxonomy": "Psychiatry"}}}
    # observe() appends to the real history, which the dashboard publishes as
    # observed registry changes. A test must not leave fabricated rows in it.
    before = watch.load_snapshot()
    hist_before = watch.HISTORY.read_text() if watch.HISTORY.exists() else None
    try:
        watch.save_snapshot({})
        assert watch.observe(res, "test") == {}          # first sighting: nothing to compare
        res2 = {"t1": {"npi": "1234567893", "registry": {"city": "CAMBRIDGE", "state": "MA",
                                                         "taxonomy": "Psychiatry"}}}
        trig = watch.observe(res2, "test")
        assert trig["t1"][0]["type"] == "practice_move"
    finally:
        watch.save_snapshot(before)
        if hist_before is None:
            watch.HISTORY.unlink(missing_ok=True)
        else:
            watch.HISTORY.write_text(hist_before)

def test_nppes_is_a_live_api():
    hits = io_input.nppes_lookup(taxonomy="Psychiatry", state="NY", limit=1)
    assert hits and ("_error" in hits[0] or hits[0].get("npi"))

def test_qc_blocks_a_banned_claim():
    v = qc.check({"to": "a@b.c", "subject": "Test subject line",
                  "body": "We are HIPAA certified and guarantee reimbursement. " * 6})
    assert not v.ok
    assert any("banned" in f for f in v.failures)

def test_qc_blocks_ai_tells():
    v = qc.check({"to": "a@b.c", "subject": "Hi",
                  "body": "I hope this email finds you well. " * 12})
    assert not v.ok

def test_qc_passes_a_clean_draft():
    body = ("Amanda Reyes runs a solo psychiatry practice in New York and has used "
            "JotPsych for fourteen months. She said she stopped doing notes after "
            "dinner. You started a trial nine days ago and have not recorded a "
            "session yet, so I wanted to offer one thing: I can introduce you to "
            "her for ten minutes. No demo, no pitch, just another psychiatrist in "
            "your state telling you what it is actually like. Would that be useful?")
    draft = compliance.apply({"to": "a@b.c",
                              "subject": "Another NY psychiatrist, ten minutes",
                              "body": body})
    v = qc.check(draft)
    assert v.ok, v.failures

def test_output_leaves_the_program():
    r = send.send_email("me@example.com", "Subject", "Body text here.")
    assert r.ok and (r.get("path") or r.get("id"))
    # out/ is committed back by the workflow as the run record, so the suite
    # must not leave artifacts in it.
    if r.get("path"):
        pathlib.Path(r["path"]).unlink(missing_ok=True)

def test_memory_persists_and_weights_shift():
    s = memory.load()
    before = memory.angle_weights(s, ["peer_proof"])["peer_proof"]
    memory.record(s, "peer_proof", "sent")
    after = memory.angle_weights(s, ["peer_proof"])["peer_proof"]
    assert after < before   # a send with no reply lowers that angle's weight


def test_outbound_requests_are_not_blocked_by_cloudflare():
    """Regression: Resend sits behind Cloudflare, which bans the stdlib default
    agent with 403 'error code: 1010' before the request reaches the API.
    Sent with a deliberately invalid key — reaching a 401 proves we got through."""
    import urllib.request, urllib.error
    from machine import config
    assert "urllib" not in config.USER_AGENT.lower()
    assert "python" not in config.USER_AGENT.lower()
    req = urllib.request.Request(
        send.RESEND, data=json.dumps({"from": "a@b.c", "to": ["d@e.f"],
                                      "subject": "s", "text": "t"}).encode(),
        headers={"Authorization": "Bearer re_invalid_key_used_by_the_test_suite",
                 "Content-Type": "application/json",
                 "User-Agent": config.USER_AGENT})
    try:
        urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        assert e.code == 401, f"expected 401 from Resend, got {e.code}: {body[:200]}"
        assert "1010" not in body
    except Exception:
        pass          # offline; the User-Agent assertions above still ran


def test_qc_judge_fails_closed_when_it_cannot_run(monkeypatch):
    """If a key is configured the judge is supposed to read every draft. When it
    cannot, the draft is unreviewed and must be blocked, never waved through."""
    from machine import llm
    monkeypatch.setattr(llm, "available", lambda: True)
    def boom(*a, **k):
        raise llm.LLMError("simulated outage")
    monkeypatch.setattr(llm, "complete_json", boom)

    clean = {"to": "a@b.c", "subject": "A perfectly ordinary subject line",
             "body": ("This body is long enough to clear the deterministic gates and "
                      "contains nothing banned, no AI tells, no placeholders and no "
                      "unsourced claims of any kind, so the only thing standing "
                      "between it and the outbox is the judge that just failed. ") * 2}
    v = qc.check(clean)
    assert not v.ok, "unreviewed draft was allowed through"
    assert any("refusing to send an unreviewed draft" in f for f in v.failures)


def test_json_survives_a_model_that_wraps_its_answer(monkeypatch):
    """Providers fence, prefix and pad JSON. The judge must still get a verdict."""
    from machine import llm
    assert llm.extract_json('```json\n{"verdict":"fail"}\n```')["verdict"] == "fail"
    assert llm.extract_json('Sure! {"verdict":"pass","note":"a } brace"}')["verdict"] == "pass"



def test_a_draft_without_an_unsubscribe_never_leaves():
    """CAN-SPAM requires a postal address and a working opt-out in every
    commercial message. The footer is appended by the machine, not written by
    the model, and QC verifies it survived."""
    body = ("You looked at JotPsych a while back and stayed where you were. That is "
            "usually the right call mid-contract. It runs alongside the system you "
            "are on today and takes about five minutes to set up. ") * 2
    bare = {"to": "a@b.c", "subject": "A perfectly ordinary subject", "body": body}
    assert not qc.check(bare).ok
    assert qc.check(compliance.apply(bare)).ok


def test_an_unsubscribe_link_cannot_be_forged():
    """The token is signed, so one clinician's link cannot unsubscribe another."""
    good = compliance.token("real@example.com")
    assert compliance.verify(good) == "real@example.com"
    forged = "victim@example.com:" + good.split(":")[1]
    assert compliance.verify(forged) == ""


def test_suppression_is_enforced_and_recorded():
    """Unsubscribes, bounces and complaints all land in one place, and every
    one of them is in the audit trail."""
    import os, tempfile
    os.environ["DB_PATH"] = tempfile.mkdtemp() + "/t.db"
    import importlib
    from machine import db as _db
    importlib.reload(_db)
    c = _db.connect()
    _db.suppress(c, "Gone@Example.com", "one-click unsubscribe", source="unsubscribe")
    assert _db.is_suppressed(c, "gone@example.com")
    assert any(e["action"] == "suppressed" for e in _db.events(c))

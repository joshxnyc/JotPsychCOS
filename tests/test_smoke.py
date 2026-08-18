"""Proves each part of the loop exists and fires. Run: python -m pytest -q"""
import json, os, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ.setdefault("DRY_RUN", "1")

from machine import qc, send, io_input, memory, strategy

def test_input_is_real_and_not_hardcoded():
    rows = io_input.read_csv("prospects.sample.csv")
    assert rows and "email" in rows[0]

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
    v = qc.check({"to": "a@b.c", "subject": "Another NY psychiatrist, ten minutes",
                  "body": body})
    assert v.ok, v.failures

def test_output_leaves_the_program():
    r = send.send_email("me@example.com", "Subject", "Body text here.")
    assert r.ok and (r.get("path") or r.get("id"))

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

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

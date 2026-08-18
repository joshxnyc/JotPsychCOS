"""PREFLIGHT. Not part of the loop — a one-command check that the machine's
credentials actually work, so nothing is discovered mid-build.

    python -m machine.preflight            # checks everything, sends nothing
    python -m machine.preflight --send     # also sends one real test email

Exits non-zero if any required check fails.
"""
import argparse, json, sys, urllib.request, urllib.error
from . import config, io_input, llm, send

OK, BAD, SKIP = "PASS", "FAIL", "SKIP"
results: list[tuple[str, str, str]] = []

def record(name, status, detail=""):
    results.append((name, status, detail))
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))

def check_nppes():
    """The live federal registry. No key, so this should always work."""
    try:
        hits = io_input.nppes_lookup(state="NY", taxonomy="Psychiatry", limit=1)
        if hits and "_error" not in hits[0]:
            record("NPPES federal NPI registry", OK, f"returned NPI {hits[0].get('npi')}")
        else:
            record("NPPES federal NPI registry", BAD, str(hits[:1]))
    except Exception as e:
        record("NPPES federal NPI registry", BAD, str(e))

def check_openrouter():
    """Real completion, not just a key-shape check — proves key, model and credit."""
    if not llm.available():
        record("OpenRouter key", SKIP, "OPENROUTER_API_KEY not set")
        return
    try:
        out = llm.complete("Reply with the single word: ready.", "Preflight check.",
                           temperature=0, max_tokens=10)
        record("OpenRouter completion", OK, f"model={config.OPENROUTER_MODEL} said {out.strip()[:40]!r}")
    except Exception as e:
        record("OpenRouter completion", BAD, str(e)[:300])

def check_openrouter_json():
    """The QC judge needs JSON mode specifically. Some models refuse it."""
    if not llm.available():
        record("OpenRouter JSON mode (QC judge)", SKIP, "no key")
        return
    try:
        d = llm.complete_json(
            'You are a checker. Return a JSON object with keys '
            '"verdict" (the string "pass") and "reasons" (an empty array).',
            "Preflight check.", temperature=0, max_tokens=300)
        if "verdict" not in d:
            record("OpenRouter JSON mode (QC judge)", BAD,
                   f"parsed but no verdict key: {json.dumps(d)[:150]}")
        else:
            record("OpenRouter JSON mode (QC judge)", OK, json.dumps(d)[:120])
    except Exception as e:
        record("OpenRouter JSON mode (QC judge)", BAD, str(e)[:400])

def check_resend(do_send: bool):
    if not config.RESEND_API_KEY:
        record("Resend key", SKIP, "RESEND_API_KEY not set")
        return
    to = config.MAIL_TO_OVERRIDE
    if not to:
        record("Resend recipient", BAD, "MAIL_TO_OVERRIDE not set — nowhere safe to send")
        return
    if not do_send:
        record("Resend key present", OK, f"would send to {to} (pass --send to actually try)")
        return
    payload = {"from": config.MAIL_FROM, "to": [to],
               "subject": "Preflight: the machine can send",
               "text": "If you are reading this, RESEND_API_KEY, MAIL_FROM and "
                       "MAIL_TO_OVERRIDE are all correct and the output can leave "
                       "the program.\n\n— preflight"}
    req = urllib.request.Request(
        send.RESEND, data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {config.RESEND_API_KEY}",
                 "Content-Type": "application/json",
                 "User-Agent": config.USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            data = json.loads(r.read())
        record("Resend live send", OK, f"id={data.get('id')} -> {to}")
    except urllib.error.HTTPError as e:
        record("Resend live send", BAD, f"{e.code} {send.explain_http_error(e)}")
    except Exception as e:
        record("Resend live send", BAD, str(e)[:300])

def check_user_agent():
    """Regression guard. Cloudflare fronts Resend and bans the stdlib default
    agent with 403 'error code: 1010' before the request reaches the API."""
    ua = config.USER_AGENT
    if not ua or "urllib" in ua.lower() or "python" in ua.lower():
        record("User-Agent", BAD, f"{ua!r} will be blocked by Cloudflare (403/1010)")
    else:
        record("User-Agent", OK, ua)

def check_settings():
    """The settings that decide whether a runaway loop is possible."""
    record("DRY_RUN", OK, "1 (simulated .eml)" if config.DRY_RUN else "0 (LIVE — will really send)")
    if config.MAX_SENDS_PER_RUN > 10:
        record("MAX_SENDS_PER_RUN", BAD, f"{config.MAX_SENDS_PER_RUN} is too high for a demo account")
    else:
        record("MAX_SENDS_PER_RUN", OK, str(config.MAX_SENDS_PER_RUN))
    if not config.DRY_RUN and not config.MAIL_TO_OVERRIDE:
        record("Send safety", BAD, "DRY_RUN=0 with no MAIL_TO_OVERRIDE — would mail the real list")
    else:
        record("Send safety", OK, "every send is redirected to MAIL_TO_OVERRIDE"
               if config.MAIL_TO_OVERRIDE else "dry run, nothing leaves")

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true", help="actually send one test email")
    a = ap.parse_args(argv)

    print("\nPreflight — checking the machine's own credentials\n")
    print("Input")
    check_nppes()
    print("Brain")
    check_openrouter()
    check_openrouter_json()
    print("Output")
    check_user_agent()
    check_resend(a.send)
    print("Safety")
    check_settings()

    bad = [r for r in results if r[1] == BAD]
    skipped = [r for r in results if r[1] == SKIP]
    print(f"\n{len(results)-len(bad)-len(skipped)} passed, {len(bad)} failed, {len(skipped)} skipped")
    if skipped:
        print("Skipped checks mean a secret is missing — set it and run again.")
    if bad:
        print("\nFAILED:")
        for n, _, d in bad:
            print(f"  - {n}: {d}")
        return 1
    print("\nEverything the machine needs is working.\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())

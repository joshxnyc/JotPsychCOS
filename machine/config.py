"""Central config. Everything the machine needs to know about itself."""
import os, pathlib
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

ROOT   = pathlib.Path(__file__).resolve().parent.parent
INBOX  = ROOT / "inbox"      # <-- INPUT LIVES HERE. Replace these files with yours.
OUT    = ROOT / "out"
STATE  = ROOT / "state"
CONFIG = ROOT / "config"
for p in (INBOX, OUT, STATE, OUT / "outbox", OUT / "quarantine"):
    p.mkdir(parents=True, exist_ok=True)

def _s(k, d=""):
    """An unset GitHub Actions variable arrives as an empty string, not as absent.
    Treat empty as unset so a forgotten repo variable falls back to the default
    instead of silently overriding it."""
    return (os.getenv(k) or "").strip() or d

def _b(k, d=True):
    v = _s(k)
    return d if v == "" else v.lower() in ("1", "true", "yes", "on")

def _i(k, d):
    try:
        return int(_s(k, str(d)))
    except ValueError:
        return d

OPENROUTER_API_KEY = _s("OPENROUTER_API_KEY")
OPENROUTER_MODEL   = _s("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.5")
RESEND_API_KEY     = _s("RESEND_API_KEY")
MAIL_FROM          = _s("MAIL_FROM", "JotPsych Machine <onboarding@resend.dev>")
MAIL_TO_OVERRIDE   = _s("MAIL_TO_OVERRIDE")
DRY_RUN            = _b("DRY_RUN", True)          # fail safe: unset means simulate
MAX_SENDS_PER_RUN  = _i("MAX_SENDS_PER_RUN", 5)

# Every outbound HTTP call identifies itself. Resend sits behind Cloudflare,
# whose browser-integrity check bans the default "Python-urllib/3.11" agent
# with 403 "error code: 1010" before the request ever reaches the API.
USER_AGENT = _s("USER_AGENT", "jotpsych-machine/1.0")

LEDGER   = OUT / "ledger.jsonl"        # append-only record of every decision
DASH     = OUT / "index.html"          # the dashboard we publish
HUMANQ   = OUT / "human_queue.md"      # the 1-2 hrs/month of human work
STATEFILE= STATE / "state.json"        # memory across runs

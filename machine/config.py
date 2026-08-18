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

def _b(k, d="0"): return os.getenv(k, d).strip().lower() in ("1", "true", "yes")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL   = os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.5").strip()
RESEND_API_KEY     = os.getenv("RESEND_API_KEY", "").strip()
MAIL_FROM          = os.getenv("MAIL_FROM", "JotPsych Machine <onboarding@resend.dev>").strip()
MAIL_TO_OVERRIDE   = os.getenv("MAIL_TO_OVERRIDE", "").strip()
DRY_RUN            = _b("DRY_RUN", "1")
MAX_SENDS_PER_RUN  = int(os.getenv("MAX_SENDS_PER_RUN", "5"))

LEDGER   = OUT / "ledger.jsonl"        # append-only record of every decision
DASH     = OUT / "index.html"          # the dashboard we publish
HUMANQ   = OUT / "human_queue.md"      # the 1-2 hrs/month of human work
STATEFILE= STATE / "state.json"        # memory across runs

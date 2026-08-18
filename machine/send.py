"""OUTPUT. The part that actually leaves the program.

Primary : Resend HTTPS API (works from CI, no SMTP ports needed).
Fallback: writes a real .eml to out/outbox/ so the loop is still provable
          with no key. DRY_RUN=1 forces the fallback.
"""
import json, urllib.request, urllib.error, datetime, re, pathlib
from email.message import EmailMessage
from . import config

RESEND = "https://api.resend.com/emails"

class SendResult(dict):
    @property
    def ok(self): return bool(self.get("ok"))

def send_email(to: str, subject: str, body: str, *, reply_to: str = "") -> SendResult:
    to = config.MAIL_TO_OVERRIDE or to
    if config.DRY_RUN or not config.RESEND_API_KEY:
        return _write_eml(to, subject, body, reason="DRY_RUN" if config.DRY_RUN else "no RESEND_API_KEY")
    payload = {"from": config.MAIL_FROM, "to": [to], "subject": subject, "text": body}
    if reply_to:
        payload["reply_to"] = reply_to
    req = urllib.request.Request(
        RESEND, data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {config.RESEND_API_KEY}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            data = json.loads(r.read())
        return SendResult(ok=True, channel="resend", id=data.get("id"), to=to)
    except urllib.error.HTTPError as e:
        return SendResult(ok=False, channel="resend", to=to,
                          error=f"{e.code} {e.read()[:300]!r}")
    except Exception as e:
        return SendResult(ok=False, channel="resend", to=to, error=str(e))

def _write_eml(to, subject, body, reason="") -> SendResult:
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = config.MAIL_FROM, to, subject
    m["Date"] = datetime.datetime.now(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    m["X-Machine-Simulated"] = reason or "1"
    m.set_content(body)
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")
    slug = re.sub(r"\W+", "-", to)[:40]
    p = config.OUT / "outbox" / f"{ts}-{slug}.eml"
    p.write_bytes(bytes(m))
    return SendResult(ok=True, channel="outbox(simulated)", path=str(p), to=to, reason=reason)

def post_webhook(url: str, payload: dict) -> SendResult:
    """Second output channel: fire a webhook (Slack, Zapier, your own endpoint)."""
    if not url:
        return SendResult(ok=False, error="no webhook url")
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return SendResult(ok=True, channel="webhook", status=r.status)
    except Exception as e:
        return SendResult(ok=False, channel="webhook", error=str(e))

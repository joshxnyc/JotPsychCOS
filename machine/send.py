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
                 "Content-Type": "application/json",
                 "User-Agent": config.USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            data = json.loads(r.read())
        return SendResult(ok=True, channel="resend", id=data.get("id"), to=to)
    except urllib.error.HTTPError as e:
        return SendResult(ok=False, channel="resend", to=to,
                          error=f"{e.code} {explain_http_error(e)}")
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
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": config.USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return SendResult(ok=True, channel="webhook", status=r.status)
    except Exception as e:
        return SendResult(ok=False, channel="webhook", error=str(e))


def explain_http_error(e) -> str:
    """Resend's failures are usually configuration, not code. Name the fix."""
    body = e.read().decode(errors="replace")[:300]
    if e.code == 403 and "1010" in body:
        return (f"{body}  <- Cloudflare blocked the User-Agent, not Resend. "
                f"Set a non-default User-Agent header.")
    if e.code == 403 and "testing emails" in body:
        return (f"{body}  <- with no verified domain Resend only delivers to the "
                f"address the account was created with. Set MAIL_TO_OVERRIDE to it.")
    if e.code == 403:
        return f"{body}  <- check the key is valid and MAIL_FROM's domain is verified."
    if e.code == 422 and "from" in body:
        return f"{body}  <- MAIL_FROM must be a verified domain, or onboarding@resend.dev."
    return body

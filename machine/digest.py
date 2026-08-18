"""THE REPORT EMAIL. What leaves the program on every cycle.

The machine writes to a person, not to a database. Every run it emails whoever
operates it a summary of what it decided, what it refused to send, and the
messages waiting for a human — each one already written, subject and body, ready
to edit and send.

Writing to clinicians is a separate switch (SEND_TO_CLINICIANS) that a company
turns on once, deliberately. This report is on by default, because a machine
nobody hears from is a machine nobody trusts.
"""
import collections, datetime, html, os
from . import config, ledger, send, watch

DASHBOARD = (os.getenv("DASHBOARD_URL") or "").strip() or (
    "https://" + (os.getenv("GITHUB_REPOSITORY_OWNER") or "joshxnyc") + ".github.io/"
    + (os.getenv("GITHUB_REPOSITORY", "joshxnyc/JotPsychCOS").split("/")[-1]) + "/")


def _e(x) -> str:
    return html.escape(str(x if x is not None else ""))


def compose(state: dict, queue: list) -> tuple[str, str, str]:
    """Returns (subject, text, html). Text is the real message; HTML is a
    courtesy. Both say the same thing."""
    recs = ledger.all_records()
    run = state.get("run_count", 0)
    this_run = [r for r in recs if r.get("run") == run]
    by = collections.Counter(r.get("action") for r in this_run)
    staged, sent = by.get("staged", 0), by.get("sent", 0)
    blocked, silent = by.get("blocked", 0), by.get("silence", 0)
    changes = [h for h in watch.history() if h.get("run_id", "").endswith(str(run))]
    cov = state.get("resolve_coverage", {})
    verb = "sent" if config.SEND_TO_CLINICIANS else "staged"
    out = staged + sent

    if queue:
        subject = (f"{len(queue)} clinician{'s' if len(queue) > 1 else ''} worth "
                   f"your time this cycle")
    elif out:
        subject = f"{out} message{'s' if out != 1 else ''} {verb}, nothing needs you"
    else:
        subject = "Quiet cycle — nothing worth sending"

    L = [f"Run {run} · {datetime.datetime.now(datetime.timezone.utc):%d %b %Y %H:%M UTC}", ""]
    L += [f"Looked at {cov.get('list_size', 0):,} clinicians. Re-read "
          f"{cov.get('reread_this_run', 0)} from the federal registry; the rest were "
          f"still fresh.", ""]
    L += [f"  {len(changes):>3}  practice changes detected",
          f"  {out:>3}  messages {verb}",
          f"  {blocked:>3}  drafts stopped by quality control",
          f"  {silent:>3}  clinicians deliberately left alone",
          f"  {len(queue):>3}  waiting for you (~{len(queue) * 12} minutes)", ""]

    if queue:
        L += ["-" * 62, "",
              "WORTH YOUR TIME — each email is written and checked. Edit if you",
              "want to, then send it from your own mailbox.", ""]
        for i, p in enumerate(queue, 1):
            c, d = p.context, (p.context.get("draft") or {})
            peer = c.get("peer") or {}
            L += [f"{i}. {c.get('name', 'Unknown')}  <{p.to}>",
                  f"   Why now: {(c.get('trigger') or {}).get('detail', 'strongest signal')}",
                  f"   Peer to offer: {peer.get('name', '—')}, {peer.get('specialty', '')}"
                  f" in {peer.get('state', '')}", "",
                  f"   Subject: {d.get('subject', '')}", ""]
            L += ["   " + ln for ln in (d.get("body", "") or "").splitlines()]
            L += ["", "   (Do not mention that anything was looked up. You are offering",
                  "    an introduction, not reporting on their practice.)", ""]

    if blocked:
        L += ["-" * 62, "", "STOPPED BEFORE SENDING", ""]
        for r in [x for x in this_run if x.get("action") == "blocked"][:5]:
            L += [f"  \"{r.get('subject', '(no subject)')}\"",
                  f"    {(r.get('failures') or ['—'])[0]}", ""]

    if not config.SEND_TO_CLINICIANS and out:
        L += ["-" * 62, "",
              f"{out} approved message{'s are' if out != 1 else ' is'} staged in "
              f"out/outbox/ and NOT delivered to anyone.",
              "Nothing reaches a clinician until SEND_TO_CLINICIANS is turned on.", ""]

    L += ["-" * 62, "", f"Full report: {DASHBOARD}",
          "Change what it says or when: config/brand.md and config/guardrails.yaml.",
          "", "— Second Window"]
    text = "\n".join(L)

    rows = "".join(
        f'<tr><td style="padding:4px 14px 4px 0;font:600 22px Archivo,sans-serif;'
        f'color:#1C1E85">{n}</td><td style="padding:4px 0;color:#545B6E;font-size:14px">'
        f'{_e(lbl)}</td></tr>'
        for n, lbl in ((len(changes), "practice changes detected"),
                       (out, f"messages {verb}"),
                       (blocked, "drafts stopped by quality control"),
                       (silent, "clinicians deliberately left alone"),
                       (len(queue), f"waiting for you (~{len(queue) * 12} min)")))
    cards = "".join(
        f'<div style="border:1px solid #E4E7EE;border-radius:10px;padding:14px 16px;'
        f'margin:10px 0;background:#FCFDFE">'
        f'<div style="font:700 16px Archivo,sans-serif;color:#0E1016">'
        f'{_e(p.context.get("name", "Unknown"))}</div>'
        f'<div style="font-size:13px;color:#545B6E;margin:4px 0 10px">'
        f'{_e((p.context.get("trigger") or {}).get("detail", ""))} · peer: '
        f'{_e((p.context.get("peer") or {}).get("name", "—"))}</div>'
        f'<div style="background:#fff;border:1px solid #E4E7EE;border-radius:8px;padding:12px">'
        f'<div style="font-size:12px;color:#878EA0;text-transform:uppercase;'
        f'letter-spacing:.06em">Subject</div>'
        f'<div style="font-weight:600;margin-bottom:8px">'
        f'{_e((p.context.get("draft") or {}).get("subject", ""))}</div>'
        f'<div style="white-space:pre-wrap;font-size:14px;line-height:1.55">'
        f'{_e((p.context.get("draft") or {}).get("body", ""))}</div></div></div>'
        for p in queue)
    body_html = f"""<div style="font-family:Inter,-apple-system,sans-serif;max-width:640px;
 margin:0 auto;padding:24px;color:#0E1016">
<div style="font:700 20px Archivo,sans-serif">Second Window</div>
<div style="color:#878EA0;font-size:13px;margin-bottom:18px">Run {run} ·
 {datetime.datetime.now(datetime.timezone.utc):%d %b %Y %H:%M UTC}</div>
<p style="color:#545B6E;font-size:14px">Looked at {cov.get('list_size', 0):,} clinicians.
 Re-read {cov.get('reread_this_run', 0)} from the federal registry; the rest were still fresh.</p>
<table style="border-collapse:collapse;margin:16px 0">{rows}</table>
{('<h3 style="font:700 15px Archivo,sans-serif;margin:22px 0 4px">Worth your time</h3>'
  '<p style="color:#545B6E;font-size:13px;margin:0 0 6px">Each email is written and has'
  ' passed every check. Edit if you want to, then send from your own mailbox.</p>' + cards)
 if queue else '<p style="color:#545B6E;font-size:14px">Nothing needs you this cycle.</p>'}
{(f'<p style="background:#FFF8EF;border:1px solid #F5D9B0;border-radius:8px;padding:12px;'
  f'font-size:13px;color:#7A4A08">{out} approved message(s) staged in out/outbox/ and '
  f'<b>not delivered to anyone</b>. Nothing reaches a clinician until '
  f'SEND_TO_CLINICIANS is turned on.</p>') if not config.SEND_TO_CLINICIANS and out else ''}
<p style="margin-top:22px"><a href="{DASHBOARD}"
 style="color:#4F52D9;font-weight:600">Open the full report →</a></p>
</div>"""
    return subject, text, body_html


def send_report(state: dict, queue: list):
    subject, text, _ = compose(state, queue)
    to = config.DIGEST_TO
    if not to:
        return send.SendResult(ok=False, error="DIGEST_TO / MAIL_TO_OVERRIDE not set")
    return send.send_email(to, subject, text)

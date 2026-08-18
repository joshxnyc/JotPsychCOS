"""Rendering. Plain functions returning HTML — no template engine, because the
surface is small enough that the indirection would cost more than it saves.

Design follows JotPsych's own system: Archivo and Inter, indigo #1C1E85 (the
logo's own ink), teal for confirmation, and a light surface because that is what
the logo was drawn for.
"""
import html, json, datetime

BRAND = "#1C1E85"


def e(x) -> str:
    return html.escape(str(x if x is not None else ""))


def ago(ts: str) -> str:
    try:
        d = datetime.datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return ts or "—"
    secs = (datetime.datetime.now(datetime.timezone.utc) - d).total_seconds()
    for n, unit in ((86400, "d"), (3600, "h"), (60, "m")):
        if secs >= n:
            return f"{int(secs // n)}{unit} ago"
    return "just now"


CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{--canvas:#F5F6F8;--surface:#fff;--line:#E4E7EE;--line2:#EFF1F5;
 --ink:#0E1016;--ink2:#545B6E;--ink3:#878EA0;--brand:#1C1E85;--brand2:#4F52D9;
 --teal:#0B7A6E;--pos:#067647;--neg:#D92D20;--warn:#B54708;
 --sh:0 1px 2px rgba(16,18,32,.04),0 4px 16px rgba(16,18,32,.05);--r:12px}
body{background:var(--canvas);color:var(--ink);font:15px/1.55 Inter,system-ui,sans-serif;
 -webkit-font-smoothing:antialiased}
h1,h2,h3,.big,.logo{font-family:Archivo,system-ui,sans-serif;letter-spacing:-.02em}
a{color:var(--brand2);text-decoration:none}a:hover{text-decoration:underline}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px}
.top{position:sticky;top:0;z-index:40;background:rgba(255,255,255,.93);
 backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}
.top-in{max-width:1140px;margin:0 auto;padding:13px 24px;display:flex;align-items:center;gap:14px}
.top img{height:22px}.sep{width:1px;height:19px;background:var(--line)}
.logo{font-weight:700;font-size:15px}.sp{flex:1}
.badge{font-size:11.5px;font-weight:600;padding:4px 10px;border-radius:999px;
 border:1px solid var(--line);color:var(--ink2);background:#fff;white-space:nowrap}
.badge.warn{color:var(--warn);border-color:#F5D9B0;background:#FFF8EF}
.badge.live{color:var(--neg);border-color:#F3C3BF;background:#FEF4F3}
nav.tabs{max-width:1140px;margin:0 auto;padding:0 24px;display:flex;gap:2px;overflow-x:auto}
nav.tabs a{color:var(--ink3);font-weight:550;padding:11px 13px;border-bottom:2px solid transparent;
 white-space:nowrap}
nav.tabs a:hover{color:var(--ink);text-decoration:none}
nav.tabs a.on{color:var(--brand);border-bottom-color:var(--brand)}
.tabwrap{border-bottom:1px solid var(--line);background:rgba(255,255,255,.93)}
main{max-width:1140px;margin:0 auto;padding:26px 24px 80px}
h1{font-size:26px;margin-bottom:6px}
.lede{color:var(--ink2);max-width:74ch;margin-bottom:22px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:13px;margin-bottom:20px}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);
 padding:15px 17px;box-shadow:var(--sh)}
.kpi .l{font-size:12.5px;color:var(--ink2);font-weight:550}
.kpi .v{font-family:Archivo,sans-serif;font-size:30px;font-weight:700;line-height:1.2;margin:5px 0 2px}
.kpi .s{font-size:12.5px;color:var(--ink3)}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);
 padding:20px 22px;box-shadow:var(--sh);margin-bottom:18px}
.card h2{font-size:16px;margin-bottom:5px}
.note{color:var(--ink2);font-size:13.5px;margin-bottom:14px;max-width:86ch}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--ink3);
 font-weight:650;padding:8px 11px;border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:10px 11px;border-bottom:1px solid var(--line2);vertical-align:top}
tr:last-child td{border-bottom:0}tbody tr:hover{background:#FAFBFD}
.scroll{overflow-x:auto}
.sub{font-size:12px;color:var(--ink3);margin-top:2px}
.pill{display:inline-block;font-size:11.5px;font-weight:650;padding:3px 10px;border-radius:999px;
 border:1px solid var(--line);white-space:nowrap}
.p-staged{color:var(--brand);border-color:#C9CBF2;background:#F3F3FE}
.p-sent{color:var(--pos);border-color:#B7E4C7;background:#F2FBF5}
.p-rejected{color:var(--ink3);background:#F7F8FA}
.p-blocked{color:var(--neg);border-color:#F3C3BF;background:#FEF4F3}
.p-verified{color:var(--teal);border-color:#A8DED6;background:#EFFAF8}
.p-probable{color:#0E7490;border-color:#B6E0EA;background:#F1FAFC}
.p-unresolved{color:var(--ink3);background:#F7F8FA}
.p-prospect{color:var(--warn);border-color:#F5D9B0;background:#FFF8EF}
.btn{font:inherit;font-size:13.5px;font-weight:600;padding:8px 15px;border-radius:9px;
 border:1px solid var(--line);background:#fff;color:var(--ink);cursor:pointer}
.btn:hover{border-color:var(--brand2);color:var(--brand2)}
.btn.primary{background:var(--brand);border-color:var(--brand);color:#fff}
.btn.primary:hover{background:#171A73;color:#fff}
.btn.danger:hover{border-color:var(--neg);color:var(--neg)}
input[type=text],input[type=email],input[type=password],input[type=search],select,textarea{
 font:inherit;font-size:14px;padding:9px 11px;border:1px solid var(--line);border-radius:9px;
 background:#fff;color:var(--ink);width:100%}
textarea{font:14px/1.6 Inter,sans-serif;resize:vertical}
input:focus,textarea:focus,select:focus{outline:2px solid #DDE0FA;border-color:var(--brand2)}
label{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.06em;
 color:var(--ink3);font-weight:650;margin-bottom:5px}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.draft{border:1px solid var(--line);border-radius:11px;margin-bottom:16px;overflow:hidden}
.draft-h{display:flex;justify-content:space-between;align-items:flex-start;gap:14px;
 padding:14px 16px;background:#FBFCFD;border-bottom:1px solid var(--line)}
.draft-h b{font-family:Archivo,sans-serif;font-size:15.5px}
.draft-b{padding:14px 16px}
.field{margin-bottom:12px}
.why{background:#F3F3FE;border-left:3px solid var(--brand2);padding:9px 12px;
 border-radius:0 7px 7px 0;font-size:13px;color:var(--ink2);margin-bottom:14px}
.compliance{background:#F7F8FA;border:1px dashed var(--line);border-radius:8px;padding:9px 12px;
 font-size:12px;color:var(--ink3);margin-bottom:12px;white-space:pre-wrap}
.flash{padding:11px 15px;border-radius:9px;margin-bottom:18px;font-size:13.5px;font-weight:550}
.flash.ok{background:#F2FBF5;border:1px solid #B7E4C7;color:var(--pos)}
.flash.err{background:#FEF4F3;border:1px solid #F3C3BF;color:var(--neg)}
.empty{color:var(--ink3);padding:22px;text-align:center;font-size:13.5px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:18px}
@media(max-width:820px){.two{grid-template-columns:1fr}}
footer{max-width:1140px;margin:0 auto;padding:0 24px 50px;color:var(--ink3);font-size:12.5px;max-width:88ch}
.login{max-width:380px;margin:12vh auto;padding:0 24px}
"""

TABS = [("/", "Overview"), ("/review", "Review &amp; send"), ("/clinicians", "Clinicians"),
        ("/prospects", "New practices"), ("/activity", "Activity"), ("/settings", "Settings")]


def page(title: str, body: str, *, active: str = "/", badges: str = "",
         flash: tuple = ()) -> str:
    tabs = "".join(f'<a href="{h}" class="{"on" if h == active else ""}">{t}</a>'
                   for h, t in TABS)
    fl = (f'<div class="flash {e(flash[0])}">{e(flash[1])}</div>' if flash else "")
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)} · Second Window</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>
<div class="top"><div class="top-in">
  <img src="/static/jotpsych-logo.svg" alt="JotPsych">
  <span class="sep"></span><span class="logo">Second Window</span>
  <span class="sp"></span>{badges}
  <form method="post" action="/logout" style="display:inline">
    <button class="badge" style="cursor:pointer">Sign out</button></form>
</div></div>
<div class="tabwrap"><nav class="tabs">{tabs}</nav></div>
<main>{fl}{body}</main>
<footer>Second Window re-engages behavioural-health clinicians who tried JotPsych and did
not subscribe. It watches the federal NPI registry for the practice changes that reopen a
software decision, drafts what to say, checks it, and holds it for a person.
Every message carries an unsubscribe link and a postal address, and every approval is
recorded against the person who made it.</footer>
</body></html>"""


# ------------------------------------------------------------------ pages ---
def kpi(label, value, sub="") -> str:
    return (f'<div class="kpi"><div class="l">{e(label)}</div>'
            f'<div class="v">{e(value)}</div><div class="s">{e(sub)}</div></div>')


def overview_page(counts, runs, staged, prospects, changes) -> str:
    last = runs[0] if runs else None
    run_rows = "".join(
        f'<tr><td><b>Run {r["id"]}</b><div class="sub">{e(r["trigger"])}</div></td>'
        f'<td class="mono">{e(ago(r["started_at"]))}</td>'
        f'<td>{e(json.loads(r["summary"] or "{}").get("staged", 0))}</td>'
        f'<td>{e(json.loads(r["summary"] or "{}").get("blocked", 0))}</td>'
        f'<td>{e(json.loads(r["summary"] or "{}").get("silent", 0))}</td>'
        f'<td>{e(json.loads(r["summary"] or "{}").get("human_queue", 0))}</td></tr>'
        for r in runs[:8]) or '<tr><td colspan=6 class="empty">No runs yet.</td></tr>'
    return f"""
<h1>Overview</h1>
<p class="lede">Second Window keeps clinicians who tried JotPsych in view until their
situation changes, and tells you the moment it does. Nothing reaches a clinician without
a person approving it.</p>
<div class="kpis">
  {kpi("Waiting for you", counts["awaiting"], "drafted, checked, not sent")}
  {kpi("Clinicians tracked", f'{counts["clinicians"]:,}', "from your list")}
  {kpi("New practices found", f'{counts["prospects"]:,}', "registered in the last 90 days")}
  {kpi("Approved and sent", counts["sent"], f'{counts["rejected"]} rejected by a person')}
  {kpi("Stopped by checks", counts["blocked"], "never reached review")}
  {kpi("Do not contact", counts["suppressed"], "unsubscribes, bounces, complaints")}
</div>
<div class="two">
  <div class="card"><h2>What needs you now</h2>
    <p class="note">{counts["awaiting"]} message(s) drafted and checked, waiting for a
    decision. About {counts["awaiting"] * 2} minutes.</p>
    <a class="btn primary" href="/review">Open review queue</a></div>
  <div class="card"><h2>Run the machine</h2>
    <p class="note">Runs on a schedule. Trigger one now to pick up new list rows, re-read
    the registry and draft anything the change warrants.</p>
    <form method="post" action="/run"><button class="btn">Run now</button></form>
    <p class="note" style="margin:12px 0 0">Last run
    {e(ago(last["started_at"])) if last else "never"}.</p></div>
</div>
<div class="card"><h2>Recent runs</h2>
  <div class="scroll"><table>
  <thead><tr><th>Run</th><th>When</th><th>Drafted</th><th>Blocked</th>
    <th>Left alone</th><th>To a person</th></tr></thead>
  <tbody>{run_rows}</tbody></table></div></div>"""


def review_page(rows) -> str:
    if not rows:
        body = ('<div class="card"><div class="empty">Nothing waiting. The machine will '
                'draft again when something changes.</div></div>')
    else:
        body = "".join(f"""
<form class="draft" method="post" action="/decide">
  <input type="hidden" name="draft_id" value="{r['id']}">
  <div class="draft-h">
    <div><b>{e(r['name'])}</b>
      <div class="sub">{e(r['email'])} · {e(r['specialty'] or 'specialty unknown')}
        {' · ' + e(r['city']) if r['city'] else ''} {e(r['state'])}</div></div>
    <div class="row">
      <span class="pill p-{e(r['tier'])}">{e(r['tier'])} · {r['score']}</span>
      <span class="pill p-staged">{e(r['kind'].replace('_', ' '))}</span></div>
  </div>
  <div class="draft-b">
    <div class="why"><b>Why the machine drafted this:</b> {e(r['reason'])}</div>
    <div class="field"><label>Subject</label>
      <input type="text" name="subject" value="{e(r['subject'])}"></div>
    <div class="field"><label>Message</label>
      <textarea name="body" rows="9">{e(_strip_footer(r['body']))}</textarea></div>
    <div class="compliance">Appended automatically on send, and required by law:
{e(_footer_of(r['body']))}</div>
    <div class="row">
      <button class="btn primary" name="action" value="approve">Approve &amp; send</button>
      <button class="btn danger" name="action" value="reject">Reject</button>
      <button class="btn danger" name="action" value="suppress">Reject &amp; never contact</button>
    </div>
  </div>
</form>""" for r in rows)
    return f"""
<h1>Review &amp; send</h1>
<p class="lede">Every message the machine drafted and its own checks approved. Edit
anything before it goes. Approving sends it through Resend with an unsubscribe header;
rejecting records why and leaves the clinician alone.</p>
{body}"""


def _strip_footer(body: str) -> str:
    return (body or "").split("\n--\n")[0].rstrip()


def _footer_of(body: str) -> str:
    parts = (body or "").split("\n--\n")
    return ("--\n" + parts[1]) if len(parts) > 1 else "(added on send)"


def clinicians_page(rows, q: str) -> str:
    tr = "".join(
        f'<tr><td><b>{e(r["name"])}</b><div class="sub">{e(r["email"] or "no email")}</div></td>'
        f'<td><span class="pill p-{e(r["tier"])}">{e(r["tier"])}</span>'
        f'<div class="sub">score {r["score"]}</div></td>'
        f'<td>{e(r["specialty"] or "—")}<div class="sub">'
        f'{e(" · ".join(x for x in (r["city"], r["state"]) if x) or "—")}</div></td>'
        f'<td class="mono">{e(r["npi"] or "—")}</td>'
        f'<td><form method="post" action="/suppress" class="row">'
        f'<input type="hidden" name="email" value="{e(r["email"] or "")}">'
        f'<button class="btn danger" style="padding:5px 10px;font-size:12px">Never contact</button>'
        f'</form></td></tr>' for r in rows)
    return f"""
<h1>Clinicians</h1>
<p class="lede">Everyone on your list, and what the machine worked out about them from the
three fields a signup leaves behind — name, email, mobile. Everything in the Practice
column came from the federal NPI registry.</p>
<div class="card">
  <form method="get" class="row" style="margin-bottom:14px">
    <input type="search" name="q" value="{e(q)}" placeholder="Search name, email, specialty…"
      style="max-width:340px"><button class="btn">Search</button>
    <span class="sub" style="margin-left:auto">{len(rows):,} shown</span></form>
  <div class="scroll"><table>
  <thead><tr><th>Clinician</th><th>Identity match</th><th>Practice</th><th>NPI</th><th></th></tr></thead>
  <tbody>{tr or '<tr><td colspan=5 class="empty">No clinicians yet. Upload a list in Settings.</td></tr>'}</tbody>
  </table></div></div>"""


def prospects_page(rows, briefs, cfg) -> str:
    cards = "".join(f"""
<div class="draft"><div class="draft-h">
  <div><b>{e(r['name'])}</b><div class="sub">
    {e(r['specialty'])} · {e(" · ".join(x for x in (r['city'], r['state']) if x))}</div></div>
  <span class="pill p-prospect">registered {e(r['enumerated_on'] or '—')}</span>
</div><div class="draft-b">
  <p style="font-size:13.5px;color:var(--ink2)">{e(briefs[r['id']])}</p>
  <div class="row" style="margin-top:12px">
    <span class="pill">Practice line: {e(r['phone'] or 'not published')}</span>
    <span class="pill mono">NPI {e(r['npi'])}</span></div>
</div></div>""" for r in rows)
    return f"""
<h1>New practices</h1>
<p class="lede">Behavioural-health NPIs registered in the last {e(cfg['window_days'])} days
across {e(', '.join(cfg['states']))}. A practice this new has not chosen its systems yet —
there is no contract to wait out and nothing to migrate. This is the earliest point at
which JotPsych can be in the conversation.</p>
<div class="card">
  <h2>Where this comes from</h2>
  <p class="note"><b>The federal NPI register publishes no email address.</b> It publishes a
  name, a taxonomy, a practice address and a business phone. So these never become automated
  email — they become a call list. Inventing a contact address for a real clinician is not
  something this machine will do.</p>
  <form method="post" action="/prospects/sync" class="row">
    <button class="btn primary">Check the register for new practices</button>
    <span class="sub">{len(rows):,} found so far</span></form>
</div>
{cards or '<div class="card"><div class="empty">None yet. Run a check above.</div></div>'}"""


def activity_page(events) -> str:
    tr = "".join(
        f'<tr><td class="mono">{e(ago(ev["ts"]))}</td>'
        f'<td><span class="pill">{e(ev["actor"])}</span></td>'
        f'<td><b>{e(ev["action"].replace("_", " "))}</b></td>'
        f'<td class="sub">{e(ev["detail"])}</td></tr>' for ev in events)
    return f"""
<h1>Activity</h1>
<p class="lede">Every state change, and who made it. This is the record that makes it
reasonable to let a machine draft under your name — nothing it or anyone else did is
invisible after the fact.</p>
<div class="card"><div class="scroll"><table>
<thead><tr><th>When</th><th>Who</th><th>What</th><th>Detail</th></tr></thead>
<tbody>{tr or '<tr><td colspan=4 class="empty">Nothing yet.</td></tr>'}</tbody>
</table></div></div>"""


def settings_page(suppressions, cfg) -> str:
    sup = "".join(
        f'<tr><td class="mono">{e(s["email"])}</td><td>{e(s["reason"])}</td>'
        f'<td><span class="pill">{e(s["source"])}</span></td>'
        f'<td class="sub">{e(ago(s["created_at"]))}</td></tr>' for s in suppressions)
    rows = "".join(
        f'<tr><td class="mono">{e(k)}</td><td>{e(v[0])}</td>'
        f'<td class="sub">{e(v[1])}</td></tr>' for k, v in cfg.items())
    return f"""
<h1>Settings</h1>
<div class="two">
  <div class="card"><h2>Add clinicians</h2>
    <p class="note">CSV with three columns: <span class="mono">name, email, mobile</span>.
    Rows already present are updated, not duplicated. Anyone on the do-not-contact list is
    ignored.</p>
    <form method="post" action="/upload" enctype="multipart/form-data" class="row">
      <input type="file" name="file" accept=".csv" required>
      <button class="btn primary">Upload</button></form></div>
  <div class="card"><h2>Never contact</h2>
    <p class="note">Enforced when the machine decides and again at send time. Unsubscribes,
    bounces and spam complaints land here automatically.</p>
    <form method="post" action="/suppress" class="row">
      <input type="email" name="email" placeholder="clinician@example.com" required
        style="max-width:280px">
      <button class="btn">Add</button></form></div>
</div>
<div class="card"><h2>Configuration</h2>
  <p class="note">Set as environment variables on the machine. Sending to clinicians is off
  until someone turns it on deliberately.</p>
  <div class="scroll"><table>
  <thead><tr><th>Setting</th><th>Value</th><th>What it does</th></tr></thead>
  <tbody>{rows}</tbody></table></div></div>
<div class="card"><h2>Do not contact ({len(suppressions)})</h2>
  <div class="scroll"><table>
  <thead><tr><th>Email</th><th>Reason</th><th>Source</th><th>When</th></tr></thead>
  <tbody>{sup or '<tr><td colspan=4 class="empty">Nobody yet.</td></tr>'}</tbody>
  </table></div></div>"""


def login_page(err: str = "") -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Second Window</title>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;600;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body><div class="login">
<div style="text-align:center;margin-bottom:22px">
  <img src="/static/jotpsych-logo.svg" alt="JotPsych" style="height:26px">
  <div class="logo" style="font-size:19px;margin-top:10px">Second Window</div>
  <div class="sub" style="margin-top:4px">Behavioural-health re-engagement</div></div>
<div class="card">
  {f'<div class="flash err">{e(err)}</div>' if err else ''}
  <form method="post" action="/login">
    <div class="field"><label>Password</label>
      <input type="password" name="password" autofocus required></div>
    <button class="btn primary" style="width:100%">Sign in</button></form>
</div></div></body></html>"""


def unsubscribe_page(email: str, ok: bool) -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Unsubscribed</title>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;600;700&family=Inter:wght@400;500&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body><div class="login"><div class="card">
{'<h2>You are unsubscribed</h2><p class="note">' + e(email) +
 ' will not receive anything further from JotPsych. Nothing else is needed from you.</p>'
 if ok else
 '<h2>That link is not valid</h2><p class="note">It may have been altered. Reply to any '
 'message from us with the word STOP and we will remove you.</p>'}
</div></div></body></html>"""

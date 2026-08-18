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
.preview{display:flex;justify-content:space-between;align-items:center;gap:16px;
 flex-wrap:wrap;margin-top:16px;padding:14px 16px;background:#F3F3FE;
 border:1px solid #C9CBF2;border-radius:10px}
.preview b{font-size:14px}
.conns{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
.conn{border:1px solid var(--line2);border-radius:10px;padding:13px 15px;background:#FBFCFD}
.conn-h{display:flex;justify-content:space-between;align-items:center;gap:10px}
"""

TABS = [("/", "Overview"), ("/review", "Outbox"), ("/clinicians", "Audience"),
        ("/prospects", "New practices"), ("/sources", "Data sources"),
        ("/activity", "Activity"), ("/settings", "Settings")]


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
</div></div>
<div class="tabwrap"><nav class="tabs">{tabs}</nav></div>
<main>{fl}{body}</main>
<footer><b>Second Window</b> finds the moment a behavioural-health clinician is ready to
reconsider, and writes to them then. It reads the federal NPI registry, notices when a
practice changes shape, drafts what to say, checks it against what JotPsych can honestly
claim, and holds it for a person to approve.
<br><br>This workspace runs on sample data. Clinician names and contact details are
invented; registry records are real public NPPES data. Nothing is delivered to anyone
except the sample messages you ask for.</footer>
</body></html>"""


# ------------------------------------------------------------------ pages ---
def kpi(label, value, sub="") -> str:
    return (f'<div class="kpi"><div class="l">{e(label)}</div>'
            f'<div class="v">{e(value)}</div><div class="s">{e(sub)}</div></div>')


def overview_page(counts, runs, staged, prospects, changes) -> str:
    last = runs[0] if runs else None
    run_rows = "".join(
        f'<tr><td><b>Cycle {r["id"]}</b><div class="sub">{e(r["trigger"])}</div></td>'
        f'<td class="mono">{e(ago(r["started_at"]))}</td>'
        f'<td>{e(json.loads(r["summary"] or "{}").get("staged", 0))}</td>'
        f'<td>{e(json.loads(r["summary"] or "{}").get("blocked", 0))}</td>'
        f'<td>{e(json.loads(r["summary"] or "{}").get("silent", 0))}</td>'
        f'<td>{e(json.loads(r["summary"] or "{}").get("human_queue", 0))}</td></tr>'
        for r in runs[:8]) or '<tr><td colspan=6 class="empty">No cycles yet.</td></tr>'
    return f"""
<h1>Overview</h1>
<p class="lede">Thousands of clinicians tried JotPsych and did not subscribe. Most did not
say no — the timing was wrong. Second Window watches the federal NPI registry for the
practice changes that reopen that decision, writes to them at that moment, and stays quiet
the rest of the time.</p>
<div class="kpis">
  {kpi("In the outbox", counts["awaiting"], "written and checked, awaiting approval")}
  {kpi("Audience", f'{counts["clinicians"]:,}', "clinicians being watched")}
  {kpi("New practices", f'{counts["prospects"]:,}', "registered in the last 90 days")}
  {kpi("Came back", counts.get("returns", 0),
       f'{counts.get("attributed", 0)} attributed to the machine')}
  {kpi("Stopped by checks", counts["blocked"], "never reached the outbox")}
  {kpi("Do not contact", counts["suppressed"], "unsubscribes, bounces, complaints")}
</div>
<div class="two">
  <div class="card"><h2>Your outbox</h2>
    <p class="note">{counts["awaiting"]} message(s) written and checked, waiting on a
    decision. Roughly {counts["awaiting"] * 2} minutes of reading.</p>
    <a class="btn primary" href="/review">Open the outbox</a></div>
  <div class="card"><h2>Run a cycle</h2>
    <p class="note">Cycles run on a schedule. Start one now to pick up new records,
    re-read the registry, and write to anyone whose situation has changed.</p>
    <form method="post" action="/run"><button class="btn">Run a cycle now</button></form>
    <p class="note" style="margin:12px 0 0">Last cycle
    {e(ago(last["started_at"])) if last else "not yet run"}.</p></div>
</div>
<div class="card"><h2>Recent cycles</h2>
  <div class="scroll"><table>
  <thead><tr><th>Cycle</th><th>When</th><th>Written</th><th>Stopped by checks</th>
    <th>Left alone</th><th>Needs a person</th></tr></thead>
  <tbody>{run_rows}</tbody></table></div></div>"""


def blocked_card(blocked) -> str:
    if not blocked:
        return ""
    rows = []
    for r in blocked:
        try:
            fails = json.loads(r["qc"] or "{}").get("failures", [])
        except Exception:
            fails = []
        rows.append(
            f'<tr><td><b>{e(r["name"])}</b><div class="sub">{e(r["subject"] or "(no subject)")}'
            f'</div></td><td class="sub" style="color:var(--neg)">'
            + ("<br>".join(e(f) for f in fails[:3]) or "—")
            + f'</td><td class="sub">{e(ago(r["created_at"]))}</td></tr>')
    return f"""
<div class="card">
  <h2>Stopped by checks ({len(blocked)})</h2>
  <p class="note">Messages the machine wrote and then refused to let out, with the exact
  check that stopped each one. Nothing here was delivered, and nothing here needs action —
  unless the same check keeps firing, in which case the fix is a settings or rules change,
  not a rewrite.</p>
  <div class="scroll"><table>
  <thead><tr><th>Clinician / subject</th><th>What stopped it</th><th>When</th></tr></thead>
  <tbody>{''.join(rows)}</tbody></table></div>
</div>"""


def review_page(rows, blocked=None, demo: bool = True) -> str:
    if not rows:
        body = ('<div class="card"><div class="empty">Your outbox is empty. The next cycle '
                'will write to anyone whose situation has changed.</div></div>')
    else:
        body = "".join(f"""
<div class="draft">
  <div class="draft-h">
    <div><b>{e(r['name'])}</b>
      <div class="sub">{e(r['email'])} · {e(r['specialty'] or 'specialty not established')}
        {' · ' + e(r['city']) if r['city'] else ''} {e(r['state'])}</div></div>
    <div class="row">
      <span class="pill p-{e(r['tier'])}">{e(r['tier'])} · {r['score']}</span>
      <span class="pill p-staged">{e(r['kind'].replace('_', ' '))}</span></div>
  </div>
  <div class="draft-b">
    <div class="why"><b>Why now:</b> {e(r['reason'])}</div>
    <form method="post" action="/decide">
      <input type="hidden" name="draft_id" value="{r['id']}">
      <div class="field"><label>Subject</label>
        <input type="text" name="subject" value="{e(r['subject'])}"></div>
      <div class="field"><label>Message</label>
        <textarea name="body" rows="9">{e(_strip_footer(r['body']))}</textarea></div>
      <div class="compliance">Added automatically on send. Required by law, and not editable away.
{e(_footer_of(r['body']))}</div>
      <div class="row">
        <button class="btn primary" name="action" value="approve">Approve</button>
        <button class="btn danger" name="action" value="reject">Reject</button>
        <button class="btn danger" name="action" value="suppress">Reject &amp; never contact</button>
      </div>
    </form>
    {_preview_box(r['id']) if demo else ''}
  </div>
</div>""" for r in rows)
    banner = ('<div class="card" style="border-color:#F5D9B0;background:#FFF8EF">'
              '<h2>Sending is off in this workspace</h2>'
              '<p class="note" style="margin:0">The clinicians in this workspace are '
              'invented, so there is nobody real to write to. But a message only makes '
              'sense in an inbox — so put your address on any message below and it will '
              'be sent to you, through the same send path a real one would take.</p></div>'
              ) if demo else ''
    return f"""
<h1>Outbox</h1>
<p class="lede">Everything the machine has written and its own checks have cleared. Edit
anything before it goes out. Approving records the decision against you; rejecting leaves
the clinician alone and says why.</p>
{banner}
{body}
{blocked_card(blocked or [])}"""


def _preview_box(draft_id: int) -> str:
    return f"""
<form method="post" action="/preview" class="preview">
  <input type="hidden" name="draft_id" value="{draft_id}">
  <div>
    <b>See it in your own inbox</b>
    <div class="sub">Sent through the same path a clinician's message would take,
    with the same footer. Nobody else receives anything.</div>
  </div>
  <div class="row" style="flex-wrap:nowrap">
    <input type="email" name="email" placeholder="you@company.com" required
      style="min-width:230px">
    <button class="btn">Send it to me</button>
  </div>
</form>"""


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
        f'<td><div class="row" style="flex-wrap:nowrap">'
        f'<form method="post" action="/returned">'
        f'<input type="hidden" name="clinician_id" value="{e(r["id"])}">'
        f'<button class="btn" style="padding:5px 10px;font-size:12px" '
        f'title="They signed up or subscribed again. Attribution is worked out from the send history, not assumed.">Came back</button></form>'
        f'<form method="post" action="/suppress">'
        f'<input type="hidden" name="email" value="{e(r["email"] or "")}">'
        f'<button class="btn danger" style="padding:5px 10px;font-size:12px">Never contact</button>'
        f'</form></div></td></tr>' for r in rows)
    return f"""
<h1>Audience</h1>
<p class="lede">Everyone Second Window is watching, and what it established about them from
the three fields a signup leaves behind. Everything under Practice came from the federal
NPI registry, matched on name and email domain and scored for confidence.</p>
<div class="card">
  <form method="get" class="row" style="margin-bottom:14px">
    <input type="search" name="q" value="{e(q)}" placeholder="Search name, email, specialty…"
      style="max-width:340px"><button class="btn">Search</button>
    <span class="sub" style="margin-left:auto">{len(rows):,} shown</span></form>
  <div class="scroll"><table>
  <thead><tr><th>Clinician</th><th>Identity match</th><th>Practice</th><th>NPI</th><th></th></tr></thead>
  <tbody>{tr or '<tr><td colspan=5 class="empty">Nobody yet — add an audience under Data sources.</td></tr>'}</tbody>
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
<p class="lede">Behavioural-health practices that registered with CMS in the last
{e(cfg['window_days'])} days across {e(', '.join(cfg['states']))}. A practice this new has
not chosen its systems yet — no contract to wait out, nothing to migrate. It is the
earliest point at which JotPsych can be in the conversation, and it needs no list from
anyone.</p>
<div class="card">
  <h2>Where this comes from</h2>
  <p class="note"><b>The federal NPI register publishes no email address.</b> It publishes a
  name, a taxonomy, a practice address and a business phone. So these never become automated
  email — they become a call list. Inventing a contact address for a real clinician is not
  something this machine will do.</p>
  <form method="post" action="/prospects/sync" class="row">
    <button class="btn primary">Check the register now</button>
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
<p class="lede">Every change, and who made it. This is what makes it reasonable to let
software draft under your name: nothing it did, and nothing anyone did to it, is invisible
afterwards.</p>
<div class="card"><div class="scroll"><table>
<thead><tr><th>When</th><th>Who</th><th>What</th><th>Detail</th></tr></thead>
<tbody>{tr or '<tr><td colspan=4 class="empty">Nothing yet.</td></tr>'}</tbody>
</table></div></div>"""


def settings_page(suppressions, values, schema) -> str:
    sup = "".join(
        f'<tr><td class="mono">{e(s["email"])}</td><td>{e(s["reason"])}</td>'
        f'<td><span class="pill">{e(s["source"])}</span></td>'
        f'<td class="sub">{e(ago(s["created_at"]))}</td></tr>' for s in suppressions)

    fields = []
    for key, (label, _default, help_, kind) in schema.items():
        val = values.get(key, "")
        if kind.startswith("choice:"):
            opts = "".join(
                f'<option value="{e(o)}" {"selected" if o == val else ""}>{e(o)}</option>'
                for o in kind.split(":")[1].split(","))
            control = f'<select name="{e(key)}">{opts}</select>'
        else:
            itype = "email" if kind == "email" else "text"
            control = f'<input type="{itype}" name="{e(key)}" value="{e(val)}">'
        fields.append(
            f'<div class="field"><label>{e(label)}</label>{control}'
            f'<p class="sub" style="margin-top:5px">{e(help_)}</p></div>')

    return f"""
<h1>Settings</h1>
<p class="lede">How the workspace behaves — cadence, confidence thresholds, where samples
go. Changes apply from the next cycle and every change is recorded in Activity.
Credentials and the sending switch live on the deployment, not here, so a workspace
cannot be talked into sending by anyone who can reach it.</p>
<div class="two">
  <div class="card">
    <h2>Workspace</h2>
    <form method="post" action="/settings">
      {''.join(fields)}
      <div class="field" style="border-top:1px solid var(--line2);padding-top:14px">
        <label>Settings password</label>
        <input type="password" name="settings_password" placeholder="Required to save" required>
        <p class="sub" style="margin-top:5px">Browsing is open; changing how the machine
        behaves is not.</p></div>
      <button class="btn primary">Save changes</button>
    </form>
  </div>
  <div>
    <div class="card"><h2>Audience</h2>
      <p class="note">Where the three fields come from — a file you upload, or a system
      read directly.</p>
      <a class="btn primary" href="/sources">Manage data sources</a></div>
    <div class="card"><h2>Do not contact</h2>
      <p class="note">Checked when a message is written and again the moment before it is
      sent. Unsubscribes, bounces and spam complaints arrive here on their own.</p>
      <form method="post" action="/suppress" class="row">
        <input type="email" name="email" placeholder="clinician@example.com" required
          style="max-width:260px">
        <button class="btn">Add</button></form></div>
    <div class="card"><h2>Do not contact ({len(suppressions)})</h2>
      <div class="scroll"><table>
      <thead><tr><th>Email</th><th>Reason</th><th>Source</th><th>When</th></tr></thead>
      <tbody>{sup or '<tr><td colspan=4 class="empty">Nobody yet.</td></tr>'}</tbody>
      </table></div></div>
  </div>
</div>"""


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


def sources_page(counts) -> str:
    def connector(name, what, state, note):
        cls = {"live": "p-sent", "soon": "p-prospect"}.get(state, "p-rejected")
        word = {"live": "Connected", "soon": "Not available yet"}.get(state, "Not available yet")
        return (f'<div class="conn"><div class="conn-h"><b>{e(name)}</b>'
                f'<span class="pill {cls}">{e(word)}</span></div>'
                f'<p class="sub" style="margin:6px 0 0">{e(what)}</p>'
                f'<p class="sub" style="margin:6px 0 0;color:var(--ink2)">{e(note)}</p></div>')
    return f"""
<h1>Data sources</h1>
<p class="lede">Second Window needs three fields per clinician — name, email and mobile —
which is what a signup leaves behind. Everything else it works out itself from the federal
NPI registry. Point it at wherever those three fields already live.</p>

<div class="card">
  <h2>Upload a file</h2>
  <p class="note">A CSV with columns <span class="mono">name, email, mobile</span>. Rows
  already present are updated rather than duplicated, and anyone on the do-not-contact list
  is skipped on the way in. Currently watching
  <b>{counts['clinicians']:,}</b> clinician(s).</p>
  <form method="post" action="/upload" enctype="multipart/form-data" class="row">
    <input type="file" name="file" accept=".csv" required>
    <button class="btn primary">Upload</button></form>
</div>

<div class="card">
  <h2>Connect a system</h2>
  <p class="note">A file is a snapshot. A connection keeps the audience current on its own —
  a clinician who signs up on Tuesday is being watched by Wednesday, and one who
  unsubscribes anywhere stops being written to everywhere. None of these are wired up yet;
  each is an ingest adapter against the same three fields.</p>
  <div class="conns">
    {connector("CSV upload", "A file you export and upload yourself.", "live",
               "Available now, above.")}
    {connector("Google Sheets", "A sheet published to the web as CSV, re-read every cycle.",
               "soon", "The adapter exists in the batch runner (DORMANT_URL) and needs a UI to hold the link.")}
    {connector("HubSpot", "Contacts from a list or a saved view.", "soon",
               "Needs an OAuth app and a property mapping to name, email and mobile.")}
    {connector("Salesforce", "Leads or Contacts from a report.", "soon",
               "Same shape as HubSpot. Report export, then the same three fields.")}
    {connector("Segment / warehouse", "Whatever your signup writes to, read directly.",
               "soon", "The most durable option: no export step and no drift between systems.")}
    {connector("Webhook", "Your signup posts each new clinician as it happens.", "soon",
               "The lowest-latency route, and the least work on your side once it exists.")}
  </div>
</div>

<div class="card">
  <h2>The register, which needs no list at all</h2>
  <p class="note">CMS publishes every newly enumerated NPI. Second Window reads it directly
  to find practices being formed right now — nobody has to send it anything. That source is
  live today under <a href="/prospects">New practices</a>, with
  <b>{counts['prospects']:,}</b> found so far.</p>
</div>"""

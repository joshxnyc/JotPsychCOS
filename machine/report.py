"""THE REPORT. What the machine did, what it caught, and whether it is working.

Two outputs:
  out/index.html      - the dashboard, published to GitHub Pages
  out/human_queue.md  - the 1-2 hours of human time, as instructions not data

Styled to JotPsych's own brand: Archivo/Inter, teal #128276, indigo #1c1e85.
"""
import html, json, shutil, datetime, collections
from . import config, ledger, memory, watch

BRAND = {"teal": "#128276", "teal_lift": "#16a394", "indigo": "#1c1e85",
         "ink": "#0b1220", "panel": "#121a2a", "line": "#22304a",
         "text": "#e8edf6", "muted": "#93a3bd",
         "good": "#22c55e", "bad": "#ef4444", "warn": "#f59e0b",
         "indigo_lift": "#7c7ff5"}


# ------------------------------------------------------------------ maths ---
def metrics(state: dict) -> dict:
    recs = ledger.all_records()
    by = collections.Counter(r.get("action") for r in recs)
    sent    = by.get("sent", 0)
    blocked = by.get("blocked", 0)
    silent  = by.get("silence", 0)
    queued  = by.get("human_call", 0)
    drafted = sent + blocked
    considered = sent + blocked + silent + queued + by.get("deferred", 0) + by.get("skipped", 0)

    returns = state.get("returns", {})
    attributed = [r for r in returns.values() if r.get("attributed")]
    touches = sum(r.get("touches", 0) for r in attributed)

    tiers = collections.Counter(v["tier"] for v in state.get("resolution_scores", {}).values())
    triggers = collections.Counter(
        (r.get("reason") or "").split(":")[0] for r in recs
        if r.get("action") in ("sent", "human_call", "blocked")
        and ":" in (r.get("reason") or ""))

    return {
        "runs": state.get("run_count", 0),
        "considered": considered, "sent": sent, "blocked": blocked,
        "silent": silent, "queued": queued, "drafted": drafted,
        "silence_rate": (silent / considered * 100) if considered else 0,
        "catch_rate": (blocked / drafted * 100) if drafted else 0,
        "returns_total": len(returns),
        "returns_attributed": len(attributed),
        "touches_per_return": (touches / len(attributed)) if attributed else 0,
        "human_minutes": queued * 12,      # 12 min per warm intro, the whole job
        "tiers": tiers, "triggers": triggers,
        "changes_seen": len(watch.history()),
    }


# ---------------------------------------------------------------- helpers ---
def _e(x) -> str:
    return html.escape(str(x if x is not None else ""))

def _tile(label, value, sub="", tone="") -> str:
    color = {"good": BRAND["good"], "bad": BRAND["bad"], "warn": BRAND["warn"]}.get(tone, BRAND["teal_lift"])
    return (f'<div class="tile"><div class="tile-l">{_e(label)}</div>'
            f'<div class="tile-v" style="color:{color}">{_e(value)}</div>'
            f'<div class="tile-s">{_e(sub)}</div></div>')

def _bar(label, n, total, tone="teal_lift") -> str:
    pct = (n / total * 100) if total else 0
    return (f'<div class="bar"><div class="bar-h"><span>{_e(label)}</span>'
            f'<b>{n}</b></div><div class="bar-t">'
            f'<div class="bar-f" style="width:{pct:.1f}%;background:{BRAND[tone]}"></div></div></div>')


# ------------------------------------------------------------------ build ---
def build(state: dict) -> None:
    m = metrics(state)
    recs = ledger.all_records()

    # the logo travels with the published site
    src = config.ROOT / "assets" / "jotpsych-logo.svg"
    if src.exists():
        shutil.copy(src, config.OUT / "jotpsych-logo.svg")

    blocked_rows = [r for r in recs
                    if r.get("action") in ("blocked", "red_team_blocked")][-14:][::-1]
    decision_rows = [r for r in recs if r.get("action") in
                     ("sent", "human_call", "silence", "blocked")][-30:][::-1]
    angle_rows = sorted(state.get("angles", {}).items(),
                        key=lambda kv: kv[1].get("sent", 0), reverse=True)

    qc_table = "".join(
        f"<tr><td>{'<span class=pill pill-redteam>red team</span>' if r.get('action')=='red_team_blocked' else '<span class=pill pill-blocked>live</span>'}</td>"
        f"<td>{_e(r.get('case') or r.get('subject') or '—')}</td>"
        f"<td class='bad'>" + "<br>".join(_e(f) for f in (r.get("failures") or ["—"])) + "</td>"
        f"<td class='reason'>{_e(r.get('why_it_matters') or '')}</td>"
        f"<td class='mono dim'>{_e(r.get('quarantine'))}</td></tr>"
        for r in blocked_rows) or "<tr><td colspan=5 class='dim'>Nothing blocked yet.</td></tr>"

    dec_table = "".join(
        f"<tr><td><span class='pill pill-{_e(r.get('action'))}'>{_e(r.get('action'))}</span></td>"
        f"<td class='mono'>{_e(r.get('target_id'))}</td>"
        f"<td class='reason'>{_e(r.get('reason'))}</td></tr>"
        for r in decision_rows)

    angle_table = "".join(
        f"<tr><td>{_e(a)}</td><td>{v.get('sent',0)}</td><td>{v.get('blocked',0)}</td>"
        f"<td class='good'>{v.get('replied',0)}</td>"
        f"<td class='mono'>{memory.angle_weights(state,[a])[a]:.3f}</td></tr>"
        for a, v in angle_rows) or "<tr><td colspan=5 class='dim'>No angles used yet.</td></tr>"

    hist = watch.history()[-10:][::-1]
    hist_table = "".join(
        f"<tr><td class='mono'>{_e(h.get('npi'))}</td><td>{_e(h.get('field'))}</td>"
        f"<td class='dim'>{_e(h.get('before'))}</td><td class='good'>{_e(h.get('after'))}</td>"
        f"<td><span class='pill pill-trigger'>{_e(h.get('trigger'))}</span></td></tr>"
        for h in hist) or "<tr><td colspan=5 class='dim'>No registry changes observed yet.</td></tr>"

    tier_bars = "".join(_bar(t, m["tiers"].get(t, 0), sum(m["tiers"].values()) or 1,
                             {"verified": "good", "probable": "teal_lift", "unresolved": "muted"}[t])
                        for t in ("verified", "probable", "unresolved"))

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    dry = "SIMULATED SEND" if config.DRY_RUN else "LIVE SEND"

    tiles = "".join([
        _tile("Clinicians considered", m["considered"], f"across {m['runs']} runs"),
        _tile("Stayed silent", f"{m['silence_rate']:.0f}%",
              f"{m['silent']} deliberately not contacted", "good"),
        _tile("Messages sent", m["sent"], "after passing every check"),
        _tile("QC catch rate", f"{m['catch_rate']:.0f}%",
              f"{m['blocked']} of {m['drafted']} drafts blocked",
              "bad" if m["blocked"] else ""),
        _tile("Registry changes seen", m["changes_seen"], "the readiness signal"),
        _tile("Returns attributed", m["returns_attributed"],
              f"of {m['returns_total']} total returns", "good"),
        _tile("Touches per return", f"{m['touches_per_return']:.1f}"
              if m["returns_attributed"] else "—", "lower is better"),
        _tile("Human time this cycle", f"{m['human_minutes']//60}h {m['human_minutes']%60}m",
              f"{m['queued']} warm intros to make", "warn"),
    ])
    config.DASH.write_text(_PAGE.format(
        b=BRAND, now=now, dry=dry, m=m, tiles=tiles,
        dry_cls="live" if not config.DRY_RUN else "",
        tier_bars=tier_bars, qc_table=qc_table, dec_table=dec_table,
        angle_table=angle_table, hist_table=hist_table,
    ), encoding="utf-8")


def write_human_queue(plans: list, state: dict) -> None:
    """Not a list of people. A list of instructions, each one a warm
    introduction between two real clinicians — the thing a machine cannot do."""
    lines = ["# The human hour", "",
             f"_Generated {datetime.datetime.now(datetime.timezone.utc):%Y-%m-%d %H:%M UTC} "
             f"· run {state.get('run_count', 0)}_", "",
             "These are the only clinicians this cycle where a person beats a message.",
             "Each one hit the strongest class of signal **and** has a consenting peer",
             "in their specialty and state. Twelve minutes each. Nothing else needs you.", ""]
    if not plans:
        lines += ["_Nothing this cycle. The machine handled everything it detected._", ""]
    for i, p in enumerate(plans, 1):
        c = p.context
        peer, trig = c.get("peer") or {}, c.get("trigger") or {}
        lines += [
            f"## {i}. {c.get('name', 'Unknown')}",
            f"- **Why now:** {trig.get('detail', 'n/a')}",
            f"- **Identity confidence:** {c.get('tier')} ({c.get('score')})",
            f"- **Peer to offer:** {peer.get('name', '—')}, {peer.get('credential', '')} "
            f"— {peer.get('specialty', '')} in {peer.get('state', '')}, "
            f"{peer.get('months_using', '?')} months on JotPsych",
            f"- **Open with:** \"{peer.get('attestation', '')}\"",
            f"- **Do not say:** that anything was looked up. You are offering an "
            f"introduction, not reporting on their practice.", ""]
    lines += ["---", "", "**Also worth your time this month:**",
              "- Skim `out/quarantine/` — if the machine is blocking the same thing "
              "repeatedly, the fix is a line in `config/guardrails.yaml`, not a rewrite.",
              "- Check the angle table on the dashboard. Retire anything with sends "
              "and no returns after two cycles."]
    config.HUMANQ.write_text("\n".join(lines), encoding="utf-8")


_PAGE = """<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Second Window — JotPsych</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:{b[ink]};color:{b[text]};font-family:Inter,system-ui,sans-serif;
 font-size:15px;line-height:1.55;padding:32px 20px 80px}}
.wrap{{max-width:1080px;margin:0 auto}}
h1,h2,h3,.tile-v{{font-family:Archivo,system-ui,sans-serif;font-weight:700;letter-spacing:-.02em}}
header{{display:flex;align-items:center;gap:18px;flex-wrap:wrap;margin-bottom:6px}}
header img{{height:30px;width:auto}}
.tag{{font-size:11px;text-transform:uppercase;letter-spacing:.12em;color:{b[muted]};
 border:1px solid {b[line]};border-radius:999px;padding:4px 11px}}
.tag.live{{color:{b[warn]};border-color:{b[warn]}}}
h1{{font-size:30px;margin:16px 0 6px}}
.sub{{color:{b[muted]};max-width:70ch;margin-bottom:28px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));gap:12px;margin-bottom:14px}}
.tile{{background:{b[panel]};border:1px solid {b[line]};border-radius:12px;padding:14px 16px}}
.tile-l{{font-size:11px;text-transform:uppercase;letter-spacing:.09em;color:{b[muted]}}}
.tile-v{{font-size:27px;line-height:1.25;margin:3px 0}}
.tile-s{{font-size:12px;color:{b[muted]}}}
section{{background:{b[panel]};border:1px solid {b[line]};border-radius:14px;
 padding:20px 22px;margin-top:20px}}
h2{{font-size:17px;margin-bottom:4px}}
.note{{color:{b[muted]};font-size:13px;margin-bottom:14px;max-width:80ch}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.07em;
 color:{b[muted]};font-weight:600;padding:7px 10px;border-bottom:1px solid {b[line]}}}
td{{padding:8px 10px;border-bottom:1px solid {b[line]};vertical-align:top}}
tr:last-child td{{border-bottom:none}}
.scroll{{overflow-x:auto}}
.mono{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}}
.dim{{color:{b[muted]}}} .good{{color:{b[good]}}} .bad{{color:{b[bad]}}}
.reason{{color:{b[muted]};max-width:62ch}}
.pill{{display:inline-block;font-size:11px;font-weight:600;padding:2px 9px;border-radius:999px;
 border:1px solid {b[line]};white-space:nowrap}}
.pill-sent{{color:{b[good]};border-color:{b[good]}}}
.pill-blocked{{color:{b[bad]};border-color:{b[bad]}}}
.pill-silence{{color:{b[muted]}}}
.pill-human_call{{color:{b[warn]};border-color:{b[warn]}}}
.pill-trigger{{color:{b[teal_lift]};border-color:{b[teal_lift]}}}
.pill-redteam{{color:{b[indigo_lift]};border-color:{b[indigo_lift]}}}
.bar{{margin-bottom:11px}}
.bar-h{{display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px}}
.bar-t{{height:7px;background:{b[ink]};border-radius:999px;overflow:hidden}}
.bar-f{{height:100%;border-radius:999px}}
.cols{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
@media(max-width:760px){{.cols{{grid-template-columns:1fr}}}}
footer{{color:{b[muted]};font-size:12px;margin-top:34px;border-top:1px solid {b[line]};
 padding-top:16px;max-width:80ch}}
a{{color:{b[teal_lift]}}}
</style></head><body><div class="wrap">

<header>
  <img src="jotpsych-logo.svg" alt="JotPsych">
  <span class="tag">Second Window</span>
  <span class="tag {dry_cls}">{dry}</span>
  <span class="tag">run {m[runs]} · {now}</span>
</header>

<h1>Bringing dormant clinicians back</h1>
<p class="sub">Three fields — name, email, mobile — become a verified practice profile from
the federal NPI registry. The machine watches that registry for the practice changes that
reopen a software decision, and writes only at that moment. Everyone else gets silence.</p>

<div class="grid">
  {tiles}
</div>

<section>
  <h2>What QC caught</h2>
  <p class="note">Nothing leaves without passing both a deterministic gate and an LLM judge
  that reads the draft against the fact pack. If the judge cannot return a verdict, the draft
  is blocked, not sent. Every blocked draft is on disk in <span class="mono">out/quarantine/</span>.</p>
  <div class="scroll"><table>
    <tr><th>Source</th><th>Draft</th><th>What the check caught</th><th>Why it matters</th><th>File</th></tr>
    {qc_table}
  </table></div>
</section>

<div class="cols">
  <section>
    <h2>Identity confidence</h2>
    <p class="note">How sure the machine is that it found the right clinician. Below the
    threshold it refuses to personalise rather than guess.</p>
    {tier_bars}
  </section>
  <section>
    <h2>Angle performance</h2>
    <p class="note">The machine leans toward the angle that has produced returns. This table
    is what changes its behaviour next cycle — no one rewrites it.</p>
    <div class="scroll"><table>
      <tr><th>Angle</th><th>Sent</th><th>Blocked</th><th>Returned</th><th>Weight</th></tr>
      {angle_table}
    </table></div>
  </section>
</div>

<section>
  <h2>Registry changes observed</h2>
  <p class="note">The readiness detector. Each row is a real difference between what the
  federal registry said last run and what it says now — the machine cannot see these without
  its own memory of the previous run.</p>
  <div class="scroll"><table>
    <tr><th>NPI</th><th>Field</th><th>Was</th><th>Now</th><th>Trigger</th></tr>
    {hist_table}
  </table></div>
</section>

<section>
  <h2>Every decision, with its reason</h2>
  <p class="note">Including the ones where it chose to stay quiet. Silence is logged so the
  silence rate is measured rather than claimed.</p>
  <div class="scroll"><table>
    <tr><th>Action</th><th>Clinician</th><th>Why</th></tr>
    {dec_table}
  </table></div>
</section>

<footer>
Case-study prototype built for JotPsych by Josh. Not an official JotPsych property.
Sample clinician names, emails and mobile numbers are invented; registry records are real
public NPPES data. No message is delivered to any real clinician — every send is redirected
to the operator's own address.
</footer>
</div></body></html>"""

"""REPORTING. What it did, what it caught, what improved, and the short list of
things a human should spend their 1-2 hours a month on."""
import json, html, datetime, collections
from . import config, ledger

def build(state: dict) -> None:
    recs = ledger.all_records()
    sent    = [r for r in recs if r.get("action") == "sent"]
    blocked = [r for r in recs if r.get("action") == "blocked"]
    skipped = [r for r in recs if r.get("action") == "skipped"]
    by_angle = collections.defaultdict(lambda: {"sent": 0, "blocked": 0})
    for r in recs:
        a = r.get("angle") or "-"
        if r.get("action") in ("sent", "blocked"):
            by_angle[a][r["action"]] += 1
    reasons = collections.Counter(f for r in blocked for f in r.get("failures", []))

    _human_queue(state, blocked, sent, reasons)
    _dashboard(state, recs, sent, blocked, skipped, by_angle, reasons)

def _human_queue(state, blocked, sent, reasons):
    lines = ["# Human queue",
             f"_generated {datetime.datetime.now(datetime.timezone.utc):%Y-%m-%d %H:%M UTC} "
             f"- run #{state.get('run_count')}_", "",
             "The machine handles the rest. These are the only items that need a person.", ""]
    top = reasons.most_common(3)
    if top:
        lines += ["## 1. Fix the top block reason", ""]
        for why, n in top:
            lines.append(f"- **{n}x** - {why}")
        lines += ["", "_Each of these is a one-line edit to `config/guardrails.yaml` "
                  "or `config/fact_pack.md`._", ""]
    weak = [a for a, s in state.get("angles", {}).items()
            if s.get("sent", 0) >= 5 and s.get("replied", 0) / max(s["sent"], 1) < 0.05]
    if weak:
        lines += ["## 2. Retire or rewrite these angles", ""] + \
                 [f"- `{a}` - under 5% reply after {state['angles'][a]['sent']} sends" for a in weak] + [""]
    lines += ["## 3. Refresh the roster", "",
              "- Add any clinician who replied positively to `inbox/advocates.csv` "
              "so the machine can quote them next cycle.",
              "- Drop anyone who asked to be left alone into `inbox/suppress.csv`.", ""]
    config.HUMANQ.write_text("\n".join(lines))

def _dashboard(state, recs, sent, blocked, skipped, by_angle, reasons):
    def row(cells, tag="td"):
        return "<tr>" + "".join(f"<{tag}>{html.escape(str(c))}</{tag}>" for c in cells) + "</tr>"
    angle_rows = "".join(
        row([a, s["sent"], s["blocked"],
             f"{state.get('angles',{}).get(a,{}).get('replied',0)}",
             f"{(state.get('angles',{}).get(a,{}).get('replied',0)/max(s['sent'],1)):.0%}"])
        for a, s in sorted(by_angle.items()))
    block_rows = "".join(row([why, n]) for why, n in reasons.most_common(12))
    recent = "".join(
        row([r.get("ts", "")[:19], r.get("action"), r.get("angle", "-"),
             (r.get("subject") or "-")[:70],
             "; ".join(r.get("failures", []))[:90] or "-"])
        for r in recs[-25:][::-1])
    caught_rate = len(blocked) / max(len(blocked) + len(sent), 1)
    hq = config.HUMANQ.read_text() if config.HUMANQ.exists() else ""

    config.DASH.write_text(f"""<!doctype html><meta charset="utf-8">
<title>Machine run report</title>
<style>
:root{{color-scheme:light dark}}
body{{font:15px/1.55 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
max-width:900px;margin:2rem auto;padding:0 1rem}}
h1{{font-size:1.5rem;margin:0 0 .25rem}} h2{{font-size:1.05rem;margin:2rem 0 .5rem}}
.sub{{opacity:.6;margin:0 0 1.5rem}}
.k{{display:flex;gap:.75rem;flex-wrap:wrap;margin:1rem 0}}
.kpi{{flex:1 1 120px;border:1px solid color-mix(in srgb,currentColor 18%,transparent);
border-radius:10px;padding:.7rem .9rem}}
.kpi b{{display:block;font-size:1.6rem;line-height:1.1}}
.kpi span{{font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;opacity:.6}}
table{{border-collapse:collapse;width:100%;font-size:.85rem}}
th,td{{text-align:left;padding:.4rem .5rem;border-bottom:1px solid
color-mix(in srgb,currentColor 12%,transparent);vertical-align:top}}
th{{font-size:.7rem;text-transform:uppercase;letter-spacing:.06em;opacity:.6}}
pre{{white-space:pre-wrap;font:13px/1.5 ui-monospace,monospace;
background:color-mix(in srgb,currentColor 5%,transparent);padding:1rem;border-radius:10px}}
</style>
<h1>Machine run report</h1>
<p class="sub">Run #{state.get('run_count')} &middot; last run {state.get('last_run','')[:19]} UTC
&middot; first run {(state.get('first_run') or '')[:19]} UTC</p>
<div class="k">
  <div class="kpi"><b>{len(sent)}</b><span>sent</span></div>
  <div class="kpi"><b>{len(blocked)}</b><span>blocked by QC</span></div>
  <div class="kpi"><b>{caught_rate:.0%}</b><span>catch rate</span></div>
  <div class="kpi"><b>{len(skipped)}</b><span>skipped</span></div>
  <div class="kpi"><b>{state.get('run_count',0)}</b><span>runs</span></div>
</div>
<h2>Performance by angle</h2>
<table><tr><th>Angle<th>Sent<th>Blocked<th>Replied<th>Reply rate</tr>{angle_rows or row(['no data','','','',''])}</table>
<h2>What QC caught</h2>
<table><tr><th>Reason<th>Count</tr>{block_rows or row(['nothing blocked yet',''])}</table>
<h2>Last 25 decisions</h2>
<table><tr><th>When<th>Action<th>Angle<th>Subject<th>QC failures</tr>{recent}</table>
<h2>Human queue</h2>
<pre>{html.escape(hq)}</pre>
""")

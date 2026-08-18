"""THE REPORT. An operator's console, not a data dump.

Five views, because five different questions get asked of this machine:
  Overview   - is it working, and what did it just do?
  Clinicians - what does it actually know about the people on the list?
  Runs       - what happened each cycle, and when?
  Quality    - what did it refuse to send, and which check stopped it?
  Files      - where is every artifact, openable in one click?

Built in JotPsych's own brand. The logo is #1C1E85 indigo on transparent, so
the surface is light; the categorical series palette is validated for
colour-vision deficiency rather than chosen by eye.
"""
import html, json, shutil, datetime, collections, pathlib
from . import config, ledger, memory, watch

REPO = "https://github.com/joshxnyc/JotPsychCOS"
BLOB = REPO + "/blob/main/"

# Validated categorical series (all six checks pass on a light surface).
# Three chromatic actions (validated: lightness band, chroma floor, CVD
# separation, normal-vision floor, contrast) plus a deliberately neutral rest
# state — silence is the absence of an action, and should recede. Every segment
# is direct-labeled, so identity never rests on colour alone.
SERIES = {"moment": "#4F52D9", "keep_warm": "#0FA396",
          "human_call": "#D97706", "silence": "#C7CCD8"}
TIER_RAMP = {"verified": "#0B7A6E", "probable": "#3FB8A6", "unresolved": "#BFD9D4"}

CHECKS = {
    "how we knew": ("Surveillance", "The registry decides when to write. Saying "
        "so out loud turns a well-timed message into being watched — and a "
        "clinician who feels watched never comes back."),
    "identity is only": ("Unearned claim", "The identity match was not confident "
        "enough to name this fact. If it is the wrong person, we just wrote to a "
        "stranger about someone else's practice."),
    "echoes the registry": ("Signal leak", "Quoting the value that changed proves "
        "we were watching, even without admitting it."),
    "banned claim": ("Forbidden claim", "Something JotPsych cannot say — a "
        "reimbursement guarantee, or a certification that does not exist."),
    "AI tell": ("Reads as AI", "Phrasing that tells a busy clinician nobody read "
        "this before it was sent."),
    "possible PHI": ("Patient data", "Behavioural health. Nothing resembling "
        "patient information may ever appear in outbound."),
    "judge:": ("Judge", "The LLM judge read the draft against the fact pack and "
        "the voice spec and rejected it, quoting the offending text."),
    "placeholder": ("Template artifact", "An unfilled placeholder survived into "
        "the draft."),
    "empty": ("Malformed", "The drafter returned nothing usable, or the draft is "
        "the wrong length for a clinician to read."),
    "too short": ("Malformed", "The drafter returned nothing usable, or the draft "
        "is the wrong length for a clinician to read."),
    "too long": ("Malformed", "The drafter returned nothing usable, or the draft "
        "is the wrong length for a clinician to read."),
}


def _e(x) -> str:
    return html.escape(str(x if x is not None else ""))


def classify(failure: str) -> tuple[str, str]:
    for key, (label, why) in CHECKS.items():
        if key.lower() in failure.lower():
            return label, why
    return "Other", "A deterministic gate rejected this draft."


# ------------------------------------------------------------------ maths ---
def metrics(state: dict) -> dict:
    recs = ledger.all_records()
    by = collections.Counter(r.get("action") for r in recs)
    sent, blocked = by.get("sent", 0), by.get("blocked", 0)
    silent, queued = by.get("silence", 0), by.get("human_call", 0)
    drafted = sent + blocked
    considered = sum(by.get(k, 0) for k in
                     ("sent", "blocked", "silence", "human_call", "deferred", "skipped"))
    returns = state.get("returns", {})
    attributed = [r for r in returns.values() if r.get("attributed")]
    touches = sum(r.get("touches", 0) for r in attributed)
    return {
        "runs": state.get("run_count", 0), "considered": considered,
        "sent": sent, "blocked": blocked, "silent": silent, "queued": queued,
        "drafted": drafted, "roster": len(state.get("roster", {})),
        "silence_rate": (silent / considered * 100) if considered else 0,
        "catch_rate": (blocked / drafted * 100) if drafted else 0,
        "returns_total": len(returns), "returns_attributed": len(attributed),
        "touches_per_return": (touches / len(attributed)) if attributed else 0,
        "human_minutes": queued * 12,
        "tiers": collections.Counter(v["tier"] for v in state.get("roster", {}).values()),
        "changes_seen": len(watch.history()),
        "actions": by,
    }


# --------------------------------------------------------------- fragments --
def _kpi(label, value, sub, tip, tone="") -> str:
    return (f'<div class="kpi"><div class="kpi-top"><span class="kpi-l">{_e(label)}</span>'
            f'<span class="info" data-tip="{_e(tip)}">?</span></div>'
            f'<div class="kpi-v {tone}">{_e(value)}</div>'
            f'<div class="kpi-s">{_e(sub)}</div></div>')


def _stacked(counts: dict, order: list, colors: dict, total: int) -> str:
    if not total:
        return '<p class="empty">Nothing yet.</p>'
    segs, keys = [], [k for k in order if counts.get(k)]
    for k in keys:
        pct = counts[k] / total * 100
        segs.append(f'<div class="seg" style="width:{pct:.2f}%;background:{colors[k]}" '
                    f'data-tip="{_e(k.replace("_", " "))}: {counts[k]} of {total}"></div>')
    legend = "".join(
        f'<span class="lg"><i style="background:{colors[k]}"></i>'
        f'{_e(k.replace("_"," "))} <b>{counts[k]}</b></span>' for k in keys)
    return f'<div class="stack">{"".join(segs)}</div><div class="legend">{legend}</div>'


def build(state: dict) -> None:
    m = metrics(state)
    recs = ledger.all_records()
    src = config.ROOT / "assets" / "jotpsych-logo.svg"
    if src.exists():
        shutil.copy(src, config.OUT / "jotpsych-logo.svg")

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    mode = "Simulated send" if config.DRY_RUN else "Live send"

    page = _TEMPLATE
    page = page.replace("%%CSS%%", _CSS)
    page = page.replace("%%NOW%%", _e(now))
    page = page.replace("%%MODE%%", _e(mode))
    page = page.replace("%%RUNS%%", str(m["runs"]))
    page = page.replace("%%REPO%%", REPO)
    page = page.replace("%%OVERVIEW%%", _overview(m, state, recs))
    page = page.replace("%%PEOPLE%%", _people(state, recs))
    page = page.replace("%%RUNSTAB%%", _runs(recs, state))
    page = page.replace("%%QUALITY%%", _quality(recs, m))
    page = page.replace("%%FILES%%", _files(m))
    config.DASH.write_text(page, encoding="utf-8")


# ---------------------------------------------------------------- overview --
def _overview(m, state, recs) -> str:
    kpis = "".join([
        _kpi("Stayed silent", f"{m['silence_rate']:.0f}%",
             f"{m['silent']} of {m['considered']} decisions",
             "The share of decisions where the machine deliberately said nothing. "
             "At thousands of clinicians, restraint is the product — a machine "
             "that writes to everyone is a newsletter.", "pos"),
        _kpi("Moments found", m["changes_seen"],
             "practice changes in the registry",
             "Changes in the federal NPI registry since the previous run — a "
             "practice that moved, renamed, changed specialty or became a group. "
             "This is the readiness signal. Zero means the detector is dead."),
        _kpi("Messages sent", m["sent"],
             f"{m['blocked']} blocked before sending",
             "Drafts that passed every quality check and left the program as "
             "email. Blocked drafts never reach a clinician."),
        _kpi("Returns traced", f"{m['returns_attributed']} of {m['returns_total']}",
             ("none contacted before returning yet" if not m["returns_attributed"]
              else f"{m['touches_per_return']:.1f} touches per return"),
             "Clinicians who came back AND had been contacted by the machine first, "
             "matched through its own ledger. If we never wrote to them the machine "
             "takes no credit — which is why this can read 0 of 3.",
             "pos" if m["returns_attributed"] else ""),
    ])
    # A "sent" row in the ledger records delivery; the decision that produced it
    # is in plan_action. Counting deliveries here would hide keep_warm entirely.
    dec = collections.Counter()
    for r in recs:
        a = r.get("action")
        if a in ("silence", "human_call"):
            dec[a] += 1
        elif a in ("sent", "blocked", "deferred") and r.get("plan_action"):
            dec[r["plan_action"]] += 1
    tiers = "".join(
        f'<div class="tier"><div class="tier-h"><span><i style="background:{TIER_RAMP[t]}"></i>'
        f'{t}</span><b>{m["tiers"].get(t,0)}</b></div>'
        f'<div class="track"><div class="fill" style="width:'
        f'{(m["tiers"].get(t,0)/max(sum(m["tiers"].values()),1)*100):.1f}%;'
        f'background:{TIER_RAMP[t]}"></div></div>'
        f'<p class="tier-s">{_e(d)}</p></div>'
        for t, d in (("verified", "May name specialty, state and city."),
                     ("probable", "Specialty and state only — never a city."),
                     ("unresolved", "Nothing about them at all.")))
    return f"""
<section class="hero">
  <div>
    <h1>Second Window</h1>
    <p class="lede">Thousands of clinicians tried JotPsych and did not buy. Most did not
    say no — the timing was wrong. This machine watches the federal NPI registry for the
    practice changes that reopen that decision, and writes to a clinician only at that
    moment. Everyone else gets silence.</p>
  </div>
</section>

<div class="flow">
  <div class="step"><span class="n">1</span><b>Three fields</b>
    <p>name, email, mobile — all a signup left behind</p></div>
  <div class="arrow"></div>
  <div class="step"><span class="n">2</span><b>Identify</b>
    <p>match against the federal NPI registry, and score how sure we are</p></div>
  <div class="arrow"></div>
  <div class="step"><span class="n">3</span><b>Watch</b>
    <p>diff today's registry against last run's — what changed?</p></div>
  <div class="arrow"></div>
  <div class="step"><span class="n">4</span><b>Decide</b>
    <p>silence, keep warm, write, or hand to a person</p></div>
  <div class="arrow"></div>
  <div class="step"><span class="n">5</span><b>Check &amp; send</b>
    <p>two gates and a judge, then real email</p></div>
</div>

<div class="kpis">{kpis}</div>

<div class="two">
  <section class="card">
    <div class="card-h"><h2>What it decided</h2>
      <span class="info" data-tip="Every clinician gets exactly one decision per run, and every decision is logged with a reason — including the silent ones. That is what makes the silence rate a measurement rather than a claim.">?</span></div>
    {_stacked(dec, list(SERIES), SERIES, sum(dec.values()))}
    <dl class="defs">
      <dt style="color:{SERIES['silence']}">silence</dt><dd>Nothing to say, or not confident enough to say it.</dd>
      <dt style="color:{SERIES['keep_warm']}">keep warm</dt><dd>A quarterly touch, staggered so it never arrives as a blast.</dd>
      <dt style="color:{SERIES['moment']}">moment</dt><dd>Their practice changed. Write now.</dd>
      <dt style="color:{SERIES['human_call']}">human call</dt><dd>Strongest signal plus a matching peer. A person should do this one.</dd>
    </dl>
  </section>
  <section class="card">
    <div class="card-h"><h2>How sure it is who they are</h2>
      <span class="info" data-tip="A name and an email are not an identity. The machine scores each match 0-100 from named signals, and what a message is allowed to say depends on that score. Thresholds live in config/guardrails.yaml, not in code.">?</span></div>
    {tiers}
  </section>
</div>"""


# --------------------------------------------------------------- clinicians --
def _people(state, recs) -> str:
    latest = {}
    for r in recs:
        if r.get("target_id") and r.get("action") in ("sent", "blocked", "silence",
                                                      "human_call", "deferred", "skipped"):
            latest[r["target_id"]] = r
    roster = state.get("roster", {})
    rows = []
    for tid, p in sorted(roster.items(), key=lambda kv: -kv[1]["score"]):
        r = latest.get(tid, {})
        act = r.get("action", "—")
        practice = " · ".join(x for x in (p.get("specialty"), p.get("city"),
                                          p.get("state_code")) if x) or "—"
        sig = "<br>".join(_e(s) for s in p.get("signals", [])) or "—"
        rows.append(
            f'<tr data-tier="{_e(p["tier"])}" data-act="{_e(act)}" '
            f'data-q="{_e((p["name"] + " " + p["email"] + " " + practice).lower())}">'
            f'<td><b>{_e(p["name"])}</b><div class="sub">{_e(p["email"])}</div>'
            f'<div class="sub">{_e(p["mobile"]) or "—"}</div></td>'
            f'<td><span class="pill t-{_e(p["tier"])}">{_e(p["tier"])}</span>'
            f'<div class="sub">score {p["score"]} · {p["candidates"]} candidate(s)</div></td>'
            f'<td>{_e(practice)}<div class="sub mono">{_e(p["npi"]) or "no NPI matched"}</div></td>'
            f'<td class="tipcell" data-tip="{sig.replace("<br>", " | ")}">'
            f'<span class="pill a-{_e(act)}">{_e(act)}</span></td>'
            f'<td class="reason">{_e(r.get("reason", "—"))}</td></tr>')
    return f"""
<section class="card">
  <div class="card-h"><h2>The list</h2>
    <span class="info" data-tip="This is the entire database. Every clinician the machine has ever read, what it worked out about them from three fields, and the decision it most recently made. Replace inbox/dormant.csv and this table becomes yours.">?</span></div>
  <p class="note"><b>{len(roster)} clinicians</b>, three fields each — name, email, mobile.
  Rows sharing an email address are the same person and collapse into one; anyone on the
  suppression list never appears at all.
  Everything in the Practice column was derived from those three fields by matching
  the live federal NPI registry. Hover a decision to see the signals behind the match.</p>
  <div class="controls">
    <input id="q" type="search" placeholder="Search name, email, specialty…" oninput="flt()">
    <select id="tier" onchange="flt()">
      <option value="">All confidence</option><option>verified</option>
      <option>probable</option><option>unresolved</option></select>
    <select id="act" onchange="flt()">
      <option value="">All decisions</option><option>sent</option><option>blocked</option>
      <option>silence</option><option>human_call</option></select>
    <span id="count" class="count"></span>
  </div>
  <div class="scroll"><table id="people">
    <thead><tr><th>Clinician</th><th>Identity match</th><th>Practice (derived)</th>
      <th>Latest decision</th><th>Why</th></tr></thead>
    <tbody>{"".join(rows) or '<tr><td colspan=5 class="empty">No clinicians read yet.</td></tr>'}</tbody>
  </table></div>
</section>"""


# --------------------------------------------------------------------- runs --
def _runs(recs, state) -> str:
    runs = collections.defaultdict(lambda: collections.Counter())
    when = {}
    for r in recs:
        n = r.get("run", 0)
        runs[n][r.get("action")] += 1
        when.setdefault(n, r.get("ts", ""))
        when[n] = max(when[n], r.get("ts", ""))
    rows = []
    for n in sorted(runs, reverse=True):
        c = runs[n]
        ts = (when.get(n) or "")[:16].replace("T", " ")
        rows.append(
            f'<tr><td><b>Run {n}</b></td><td class="mono">{_e(ts)} UTC</td>'
            f'<td>{sum(c.values())}</td>'
            f'<td class="pos">{c.get("sent",0)}</td><td class="neg">{c.get("blocked",0)}</td>'
            f'<td>{c.get("silence",0)}</td><td>{c.get("human_call",0)}</td>'
            f'<td>{c.get("red_team_blocked",0)}</td></tr>')
    hist = watch.history()[-25:][::-1]
    hrows = "".join(
        f'<tr><td class="mono">{_e(h.get("npi"))}</td><td>{_e(h.get("field"))}</td>'
        f'<td class="was">{_e(h.get("before"))}</td><td class="now">{_e(h.get("after"))}</td>'
        f'<td><span class="pill trig">{_e(h.get("trigger"))}</span></td>'
        f'<td class="mono sub">{_e((h.get("ts") or "")[:16].replace("T"," "))}</td></tr>'
        for h in hist) or '<tr><td colspan=6 class="empty">No registry changes observed yet.</td></tr>'
    return f"""
<section class="card">
  <div class="card-h"><h2>Run history</h2>
    <span class="info" data-tip="Reconstructed from out/ledger.jsonl, where every row carries the run that wrote it. The workflow commits this file back to the repository after each run, so the git history is an independent record nobody here can edit.">?</span></div>
  <p class="note">Every row is one scheduled pass. The machine has run
  <b>{state.get('run_count', 0)}</b> times.
  <a href="{REPO}/actions" target="_blank">Open the Actions tab →</a></p>
  <div class="scroll"><table>
    <thead><tr><th>Run</th><th>Finished</th><th>Decisions</th><th>Sent</th>
      <th>Blocked</th><th>Silent</th><th>To a human</th><th>Red team</th></tr></thead>
    <tbody>{"".join(rows) or '<tr><td colspan=8 class="empty">No runs yet.</td></tr>'}</tbody>
  </table></div>
</section>

<section class="card">
  <div class="card-h"><h2>Registry changes the machine has seen</h2>
    <span class="info" data-tip="The readiness detector. Each row is a real difference between what the federal registry said last run and what it says now. The machine cannot see any of this without its own memory of the previous run — delete state/ and it goes blind.">?</span></div>
  <p class="note">Stored append-only in
  <a href="{BLOB}state/registry_history.jsonl" target="_blank">state/registry_history.jsonl</a>.</p>
  <div class="scroll"><table>
    <thead><tr><th>NPI</th><th>Field</th><th>Was</th><th>Now</th><th>Trigger</th><th>Seen</th></tr></thead>
    <tbody>{hrows}</tbody>
  </table></div>
</section>"""


# ------------------------------------------------------------------ quality --
def _quality(recs, m) -> str:
    blocked = [r for r in recs if r.get("action") in ("blocked", "red_team_blocked")]
    rows = []
    for r in blocked[-30:][::-1]:
        live = r.get("action") == "blocked"
        grouped = collections.OrderedDict()
        for f in (r.get("failures") or []):
            label, why = classify(f)
            grouped.setdefault(label, [why, []])[1].append(f)
        chips = []
        for label, (why, hits) in grouped.items():
            n = f' <b>×{len(hits)}</b>' if len(hits) > 1 else ""
            tip = why + " — " + " | ".join(hits[:3])
            chips.append(f'<span class="chip" data-tip="{_e(tip)}">{_e(label)}{n}</span>')
        # A run in CI writes its quarantine file into that run's workspace. Only
        # offer the link when the file is actually here to open.
        qf = r.get("quarantine")
        have = qf and (config.OUT / "quarantine" / qf).exists()
        link = (f'<a class="mono" href="quarantine/{_e(qf)}" target="_blank">open</a>'
                if have else
                (f'<span class="sub" data-tip="Written during a scheduled run in CI; '
                 f'the file lives in that run\'s artifacts, not in this snapshot.">'
                 f'in CI artifacts</span>' if qf else "—"))
        rows.append(
            f'<tr><td><span class="pill {"a-blocked" if live else "rt"}">'
            f'{"live run" if live else "red team"}</span></td>'
            f'<td><b>{_e(r.get("case") or r.get("subject") or "—")}</b>'
            f'<div class="sub">{_e(r.get("why_it_matters") or "")}</div></td>'
            f'<td>{"".join(chips) or "—"}</td><td>{link}</td></tr>')
    return f"""
<section class="card">
  <div class="card-h"><h2>What the machine refused to send</h2>
    <span class="info" data-tip="Quality control runs on every draft before it leaves. Two layers: fast deterministic gates that an LLM cannot argue with, then an LLM judge that reads the draft against the fact pack and the voice spec. If the judge cannot return a verdict, the draft is blocked rather than sent.">?</span></div>
  <p class="note">Hover any tag to see what that check is for and the exact text that
  tripped it. <b>Live run</b> means a real scheduled run rejected its own draft.
  <b>Red team</b> means <span class="mono">tools/red_team.py</span> pushed a
  deliberately bad draft through the same code path on purpose.</p>
  <div class="scroll"><table>
    <thead><tr><th>Source</th><th>Draft</th><th>Checks that fired</th><th>Evidence</th></tr></thead>
    <tbody>{"".join(rows) or '<tr><td colspan=4 class="empty">Nothing blocked yet.</td></tr>'}</tbody>
  </table></div>
</section>

<section class="card">
  <div class="card-h"><h2>The checks, and why each one exists</h2></div>
  <div class="grid3">
    {"".join(f'<div class="check"><b>{_e(l)}</b><p>{_e(w)}</p></div>'
             for l, w in dict(CHECKS.values()).items())}
  </div>
</section>"""


# -------------------------------------------------------------------- files --
def _files(m) -> str:
    def listing(sub, pattern, label, desc, tip):
        d = config.OUT / sub
        files = sorted(d.glob(pattern), reverse=True)[:20] if d.exists() else []
        items = "".join(
            f'<li><a href="{sub}/{_e(f.name)}" target="_blank" class="mono">{_e(f.name)}</a>'
            f'<span class="sub">{f.stat().st_size:,} bytes</span></li>' for f in files)
        n = len(list(d.glob(pattern))) if d.exists() else 0
        return (f'<section class="card"><div class="card-h"><h2>{label}</h2>'
                f'<span class="info" data-tip="{_e(tip)}">?</span></div>'
                f'<p class="note">{desc} <b>{n} file(s).</b> Click any to open it.</p>'
                f'<ul class="files">{items or "<li class=empty>None yet.</li>"}</ul></section>')

    def link(path, label, desc):
        return (f'<li><a href="{BLOB}{path}" target="_blank" class="mono">{path}</a>'
                f'<span class="sub">{desc}</span></li>')

    return f"""
<section class="card">
  <div class="card-h"><h2>Where everything lives</h2></div>
  <p class="note">Nothing here is a screenshot. Every link opens the actual file the
  machine wrote or reads.</p>
  <div class="two">
    <div><h3>Input — replace these with yours</h3><ul class="files">
      {link('inbox/dormant.sample.csv', '', 'the list: name, email, mobile. Drop inbox/dormant.csv beside it and it wins')}
      {link('inbox/suppress.sample.csv', '', 'never contacted, no exceptions')}
      {link('inbox/peers.sample.csv', '', 'consenting peers for the human queue')}
      {link('inbox/returns.sample.csv', '', 'clinicians who came back — stands in for a billing webhook')}
    </ul></div>
    <div><h3>Memory — committed back by the workflow</h3><ul class="files">
      {link('state/state.json', '', 'run count, roster, angle weights, attributed returns')}
      {link('state/registry_snapshot.json', '', 'what the registry said last run')}
      {link('state/registry_history.jsonl', '', 'every change ever observed')}
      {link('out/ledger.jsonl', '', 'append-only record of every decision')}
    </ul></div>
  </div>
  <div class="two" style="margin-top:22px">
    <div><h3>Rules — change behaviour without touching code</h3><ul class="files">
      {link('config/guardrails.yaml', '', 'thresholds, banned claims, tier permissions')}
      {link('config/fact_pack.md', '', 'the only things it may assert about JotPsych')}
      {link('config/brand.md', '', 'how JotPsych sounds, and the one rule above all others')}
    </ul></div>
    <div><h3>Read these</h3><ul class="files">
      {link('RECOMMENDATION.md', '', 'what I chose to build and why — one page')}
      {link('PROOF.md', '', 'one full pass, with what it rejected')}
      <li><a href="human_queue.md" target="_blank" class="mono">out/human_queue.md</a>
        <span class="sub">this cycle's hour of human work — {m['queued']} intro(s)</span></li>
    </ul></div>
  </div>
</section>
{listing('outbox', '*.eml', 'Messages that left the program', 'Real RFC-822 email files. With DRY_RUN=1 these are written instead of calling Resend — same code path, same content.', 'An output that leaves the program. Open one and you are reading exactly what a clinician would receive, headers and all, including the header that declares it simulated.')}
{listing('outbox', '*.sms.txt', 'Simulated SMS', 'The decision to reserve SMS for clinicians who engaged first is real; delivery writes a labeled file rather than calling a carrier.', 'A mobile number collected at signup is not consent to text it. SMS unlocks only after a clinician replies or clicks.')}
{listing('quarantine', '*.json', 'Quarantined drafts', 'Every draft the machine refused to send, with the full text and the exact reason.', 'This is the evidence behind the quality control claim. Each file holds the draft as written, the verdict, and the recipient record it was judged against.')}"""


_CSS = """
.top{position:static;background:var(--surface);border-bottom:1px solid var(--line-2)}
.stickyhead{position:sticky;top:0;z-index:60;background:rgba(255,255,255,.92);
 backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}
.tabs{border-bottom:0}
thead th{position:sticky;top:0;background:var(--surface);z-index:2}
.scroll{max-height:none}

*{box-sizing:border-box;margin:0;padding:0}
:root{
 --canvas:#F5F6F8; --surface:#FFFFFF; --line:#E4E7EE; --line-2:#EFF1F5;
 --ink:#0E1016; --ink-2:#545B6E; --ink-3:#878EA0;
 --brand:#1C1E85; --brand-2:#4F52D9; --teal:#0FA396;
 --pos:#067647; --neg:#D92D20; --warn:#B54708;
 --r:12px; --sh:0 1px 2px rgba(16,18,32,.04), 0 4px 16px rgba(16,18,32,.04);
}
body{background:var(--canvas);color:var(--ink);font:15px/1.55 Inter,system-ui,-apple-system,sans-serif;
 -webkit-font-smoothing:antialiased}
h1,h2,h3,.kpi-v,.n{font-family:Archivo,system-ui,sans-serif;letter-spacing:-.02em}
a{color:var(--brand-2);text-decoration:none}
a:hover{text-decoration:underline}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px}

/* top bar */
.top{position:sticky;top:0;z-index:50;background:rgba(255,255,255,.86);
 backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}
.top-in{max-width:1180px;margin:0 auto;padding:14px 24px;display:flex;align-items:center;gap:14px}
.top img{height:24px}
.divider{width:1px;height:20px;background:var(--line)}
.top .name{font-family:Archivo,sans-serif;font-weight:700;font-size:15px}
.top .sp{flex:1}
.badge{font-size:11.5px;font-weight:600;padding:4px 10px;border-radius:999px;
 border:1px solid var(--line);color:var(--ink-2);background:var(--surface);white-space:nowrap}
.badge.live{color:var(--warn);border-color:#F5D9B0;background:#FFF8EF}

/* tabs */
.tabs{max-width:1180px;margin:0 auto;padding:0 24px;display:flex;gap:2px;
 border-bottom:1px solid var(--line);overflow-x:auto}
.tab{appearance:none;border:0;background:none;font:inherit;font-weight:550;color:var(--ink-3);
 padding:12px 14px;cursor:pointer;border-bottom:2px solid transparent;white-space:nowrap}
.tab:hover{color:var(--ink)}
.tab[aria-selected="true"]{color:var(--brand);border-bottom-color:var(--brand)}

main{max-width:1180px;margin:0 auto;padding:26px 24px 90px}
.panel[hidden]{display:none}

/* hero + flow */
.hero h1{font-size:32px;margin-bottom:8px}
.lede{color:var(--ink-2);max-width:72ch;font-size:16px}
.flow{display:flex;align-items:stretch;gap:0;margin:26px 0 22px;overflow-x:auto;padding-bottom:4px}
.step{flex:1;min-width:168px;background:var(--surface);border:1px solid var(--line);
 border-radius:var(--r);padding:14px 16px;box-shadow:var(--sh)}
.step .n{display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;
 border-radius:999px;background:#EEF0FF;color:var(--brand);font-size:12px;font-weight:700;margin-bottom:8px}
.step b{display:block;font-size:14px;margin-bottom:3px}
.step p{color:var(--ink-3);font-size:12.5px;line-height:1.45}
.arrow{flex:0 0 22px;position:relative}
.arrow::after{content:"";position:absolute;top:50%;left:5px;width:12px;height:12px;
 border-top:1.5px solid var(--line);border-right:1.5px solid var(--line);
 transform:translateY(-50%) rotate(45deg)}

/* kpis */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(216px,1fr));gap:14px}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);
 padding:16px 18px;box-shadow:var(--sh)}
.kpi-top{display:flex;align-items:center;justify-content:space-between;gap:8px}
.kpi-l{font-size:12.5px;color:var(--ink-2);font-weight:550}
.kpi-v{font-size:32px;font-weight:700;line-height:1.2;margin:6px 0 2px}
.kpi-v.pos{color:var(--pos)}
.kpi-s{font-size:12.5px;color:var(--ink-3)}

/* cards */
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);
 padding:20px 22px;box-shadow:var(--sh);margin-top:18px}
.card-h{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.card-h h2{font-size:16px}
.note{color:var(--ink-2);font-size:13.5px;margin-bottom:14px;max-width:88ch}
.two{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:18px}
.two > .card{margin-top:0}
.grid3{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
.check{border:1px solid var(--line-2);border-radius:10px;padding:12px 14px;background:#FBFCFD}
.check b{font-size:13px}
.check p{color:var(--ink-2);font-size:12.5px;margin-top:4px}
h3{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--ink-3);margin-bottom:10px}

/* stacked bar */
.stack{display:flex;height:14px;border-radius:999px;overflow:hidden;gap:2px;
 background:var(--line-2);margin:12px 0 12px}
.seg{height:100%;border-radius:3px}
.legend{display:flex;flex-wrap:wrap;gap:14px;font-size:12.5px;color:var(--ink-2)}
.lg i{display:inline-block;width:9px;height:9px;border-radius:3px;margin-right:6px}
.lg b{color:var(--ink)}
.defs{margin-top:14px;display:grid;grid-template-columns:auto 1fr;gap:5px 12px;font-size:12.5px}
.defs dt{font-weight:650}
.defs dd{color:var(--ink-2)}
.tier{margin-bottom:14px}
.tier-h{display:flex;justify-content:space-between;font-size:13px;margin-bottom:5px}
.tier-h i{display:inline-block;width:9px;height:9px;border-radius:3px;margin-right:7px}
.track{height:7px;background:var(--line-2);border-radius:999px;overflow:hidden}
.fill{height:100%;border-radius:999px}
.tier-s{font-size:12px;color:var(--ink-3);margin-top:4px}

/* tables */
.scroll{overflow-x:auto;margin:0 -22px;padding:0 22px}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.06em;
 color:var(--ink-3);font-weight:650;padding:8px 12px;border-bottom:1px solid var(--line);
 white-space:nowrap}
td{padding:11px 12px;border-bottom:1px solid var(--line-2);vertical-align:top}
tbody tr:hover{background:#FAFBFD}
tr:last-child td{border-bottom:0}
.sub{font-size:12px;color:var(--ink-3);margin-top:2px}
.reason{color:var(--ink-2);max-width:44ch;font-size:12.5px}
.was{color:var(--ink-3);text-decoration:line-through}
.now{color:var(--pos);font-weight:600}
.pos{color:var(--pos)} .neg{color:var(--neg)}
.empty{color:var(--ink-3);padding:14px 12px;font-size:13px}

/* pills + chips */
.pill{display:inline-block;font-size:11.5px;font-weight:650;padding:3px 9px;border-radius:999px;
 border:1px solid var(--line);white-space:nowrap;text-transform:lowercase}
.t-verified{color:#0B7A6E;border-color:#A8DED6;background:#EFFAF8}
.t-probable{color:#0E7490;border-color:#B6E0EA;background:#F1FAFC}
.t-unresolved{color:var(--ink-3);background:#F7F8FA}
.a-sent{color:var(--pos);border-color:#B7E4C7;background:#F2FBF5}
.a-blocked{color:var(--neg);border-color:#F3C3BF;background:#FEF4F3}
.a-silence{color:var(--ink-3);background:#F7F8FA}
.a-human_call{color:var(--warn);border-color:#F5D9B0;background:#FFF8EF}
.a-deferred,.a-skipped{color:var(--ink-3);background:#F7F8FA}
.rt{color:var(--brand);border-color:#C9CBF2;background:#F3F3FE}
.trig{color:var(--brand-2);border-color:#C9CBF2;background:#F3F3FE}
.chip{display:inline-block;font-size:11.5px;font-weight:600;padding:3px 9px;margin:2px 4px 2px 0;
 border-radius:6px;background:#FEF4F3;color:var(--neg);border:1px solid #F3C3BF;cursor:help}

/* controls */
.controls{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:12px}
input[type=search],select{font:inherit;font-size:13.5px;padding:8px 11px;border:1px solid var(--line);
 border-radius:9px;background:var(--surface);color:var(--ink)}
input[type=search]{min-width:250px;flex:1;max-width:340px}
input:focus,select:focus{outline:2px solid #DDE0FA;border-color:var(--brand-2)}
.count{font-size:12.5px;color:var(--ink-3);margin-left:auto}

/* files */
.files{list-style:none}
.files li{display:flex;justify-content:space-between;gap:14px;align-items:baseline;
 padding:8px 0;border-bottom:1px solid var(--line-2)}
.files li:last-child{border-bottom:0}
.files .sub{margin:0;text-align:right}

/* tooltip */
.info{display:inline-flex;align-items:center;justify-content:center;width:16px;height:16px;
 border-radius:999px;background:var(--line-2);color:var(--ink-3);font-size:11px;font-weight:700;
 cursor:help;flex:0 0 auto}
.info:hover{background:var(--brand);color:#fff}
[data-tip]{position:relative}
[data-tip]:hover::after{content:attr(data-tip);position:absolute;z-index:80;left:50%;top:calc(100% + 9px);
 transform:translateX(-50%);background:var(--ink);color:#fff;font-family:Inter,sans-serif;
 font-size:12.5px;font-weight:400;line-height:1.5;letter-spacing:0;text-transform:none;
 padding:10px 12px;border-radius:9px;width:max-content;max-width:330px;
 box-shadow:0 8px 28px rgba(16,18,32,.20);pointer-events:none;white-space:normal}
td[data-tip]:hover::after,.chip:hover::after{left:0;transform:none}
footer{max-width:1180px;margin:0 auto;padding:0 24px 60px;color:var(--ink-3);font-size:12.5px;max-width:88ch}
@media(max-width:820px){.two{grid-template-columns:1fr}.arrow{display:none}}
"""

_TEMPLATE = """<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Second Window — JotPsych</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>%%CSS%%</style></head><body>

<div class="stickyhead"><div class="top"><div class="top-in">
  <img src="jotpsych-logo.svg" alt="JotPsych">
  <span class="divider"></span>
  <span class="name">Second Window</span>
  <span class="sp"></span>
  <span class="badge">Run %%RUNS%%</span>
  <span class="badge">%%MODE%%</span>
  <span class="badge">%%NOW%%</span>
  <a class="badge" href="%%REPO%%" target="_blank">Repository ↗</a>
</div></div>

<nav class="tabs" role="tablist">
  <button class="tab" role="tab" aria-selected="true"  data-p="overview">Overview</button>
  <button class="tab" role="tab" aria-selected="false" data-p="people">Clinicians</button>
  <button class="tab" role="tab" aria-selected="false" data-p="runs">Runs &amp; changes</button>
  <button class="tab" role="tab" aria-selected="false" data-p="quality">Quality control</button>
  <button class="tab" role="tab" aria-selected="false" data-p="files">Files</button>
</nav>
</div>

<main>
  <div class="panel" id="overview">%%OVERVIEW%%</div>
  <div class="panel" id="people" hidden>%%PEOPLE%%</div>
  <div class="panel" id="runs" hidden>%%RUNSTAB%%</div>
  <div class="panel" id="quality" hidden>%%QUALITY%%</div>
  <div class="panel" id="files" hidden>%%FILES%%</div>
</main>

<footer>Case-study prototype built for JotPsych by Josh — not an official JotPsych property.
Clinician names, emails and mobile numbers are invented, as the brief requires; registry
records are real public NPPES data for same-named clinicians and are used only to exercise
identity resolution. No message is delivered to any real clinician: every send is redirected
to the operator's own address.</footer>

<script>
document.querySelectorAll('.tab').forEach(function(t){
  t.onclick=function(){
    document.querySelectorAll('.tab').forEach(function(x){x.setAttribute('aria-selected','false')});
    document.querySelectorAll('.panel').forEach(function(p){p.hidden=true});
    t.setAttribute('aria-selected','true');
    document.getElementById(t.dataset.p).hidden=false;
    location.hash=t.dataset.p;
  };
});
if(location.hash){
  var t=document.querySelector('.tab[data-p="'+location.hash.slice(1)+'"]');
  if(t) t.click();
}
function flt(){
  var q=(document.getElementById('q').value||'').toLowerCase();
  var tier=document.getElementById('tier').value, act=document.getElementById('act').value, n=0;
  document.querySelectorAll('#people tbody tr').forEach(function(r){
    var ok=(!q||(r.dataset.q||'').indexOf(q)>-1)&&(!tier||r.dataset.tier===tier)&&(!act||r.dataset.act===act);
    r.style.display=ok?'':'none'; if(ok)n++;
  });
  document.getElementById('count').textContent=n+' shown';
}
if(document.getElementById('people')) flt();
</script>
</body></html>"""


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
            "- **Do not say:** that anything was looked up. You are offering an "
            "introduction, not reporting on their practice.", ""]
    lines += ["---", "", "**Also worth your time this month:**",
              "- Skim `out/quarantine/` — if the machine is blocking the same thing "
              "repeatedly, the fix is a line in `config/guardrails.yaml`, not a rewrite.",
              "- Check the angle table. Retire anything with sends and no returns "
              "after two cycles."]
    config.HUMANQ.write_text("\n".join(lines), encoding="utf-8")

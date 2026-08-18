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

# Portable: in Actions this comes from the runner, so a fork points at itself.
REPO = "https://github.com/" + (__import__("os").getenv("GITHUB_REPOSITORY")
                                or "joshxnyc/JotPsychCOS")
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


# Plain English. The machine's internal names are not the reader's vocabulary.
ACTION = {
    "sent":        ("Message sent", "A draft passed every check and was delivered to the clinician."),
    "staged":      ("Ready to send", "A draft passed every check and is staged as a real email file, waiting for a person. Nothing reached a clinician."),
    "digest":      ("Report emailed", "The run summary was emailed to whoever operates the machine."),
    "blocked":     ("Stopped by QC", "A draft was written but a check refused to let it go out. It is in quarantine, not in an inbox."),
    "silence":     ("Left alone", "The machine deliberately said nothing this cycle — nothing had changed, or it was not confident enough to write."),
    "human_call":  ("Needs a person", "The strongest kind of signal, plus a peer who fits. A person should make this introduction."),
    "deferred":    ("Waiting for next run", "Correct to write to, but this run's budget was already spent. First in line next time."),
    "skipped":     ("Skipped", "No usable email address."),
    "red_team_blocked": ("Red team", "A deliberately bad draft pushed through the same checks on purpose."),
    "keep_warm":   ("Keep warm", "No change in their practice, but they are due a quarterly note."),
    "moment":      ("Their moment", "Something in their practice changed. This is the time to write."),
}
TIER = {
    "verified":   ("Confident", "We are confident this is the right clinician. The message may name their specialty, state and city."),
    "probable":   ("Likely", "Probably the right clinician. The message may name specialty and state — never a city or practice name."),
    "unresolved": ("Not identified", "We could not pin down who this is. Nothing about them goes in a message, and registry changes are ignored."),
}


def label(kind: dict, key: str) -> str:
    return kind.get(key, (key.replace("_", " ").title(), ""))[0]


def why(kind: dict, key: str) -> str:
    return kind.get(key, ("", ""))[1]


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
    staged = by.get("staged", 0)
    silent, queued = by.get("silence", 0), by.get("human_call", 0)
    drafted = sent + blocked + by.get("staged", 0)
    considered = sum(by.get(k, 0) for k in
                     ("sent", "staged", "blocked", "silence", "human_call",
                      "deferred", "skipped"))
    returns = state.get("returns", {})
    attributed = [r for r in returns.values() if r.get("attributed")]
    touches = sum(r.get("touches", 0) for r in attributed)
    return {
        "runs": state.get("run_count", 0), "considered": considered,
        "sent": sent, "blocked": blocked, "silent": silent, "queued": queued,
        "drafted": drafted, "staged": staged,
        "roster": len(state.get("roster", {})),
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
    mode = ("Sending to clinicians" if config.SEND_TO_CLINICIANS
            else "Staging only — nothing reaches a clinician")

    page = _TEMPLATE
    page = page.replace("%%CSS%%", _CSS)
    page = page.replace("%%NOW%%", _e(now))
    page = page.replace("%%MODE%%", _e(mode))
    page = page.replace("%%RUNS%%", str(m["runs"]))
    page = page.replace("%%REPO%%", REPO)
    page = page.replace("%%OVERVIEW%%", _overview(m, state, recs))
    page = page.replace("%%QUEUE%%", _queue(state, recs))
    page = page.replace("%%PEOPLE%%", _people(state, recs))
    page = page.replace("%%RUNSTAB%%", _runs(recs, state))
    page = page.replace("%%QUALITY%%", _quality(recs, m))
    page = page.replace("%%FILES%%", _files(m))
    config.DASH.write_text(page, encoding="utf-8")


# ---------------------------------------------------------------- overview --
def _overview(m, state, recs) -> str:
    cov = state.get("resolve_coverage", {})
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
        _kpi("Messages ready", m["sent"] + m.get("staged", 0),
             f"{m['blocked']} stopped by quality control",
             "Drafts that passed every check. By default they are staged as real "
             "email files and wait for a person — the machine does not write to "
             "clinicians unless someone turns that on."),
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
        elif a in ("sent", "staged", "blocked", "deferred") and r.get("plan_action"):
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
    <p class="lede">Thousands of clinicians tried JotPsych and did not subscribe. Most did
    not say no — the timing was wrong. Second Window watches the federal NPI registry for
    the practice changes that reopen that decision, writes to those clinicians at that
    moment, and stays quiet the rest of the time.</p>
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

<section class="card">
  <div class="card-h"><h2>What the words mean</h2>
    <span class="info" data-tip="Every clinician gets exactly one status per run.">?</span></div>
  <div class="grid3">
    {"".join(f'<div class="check"><b>{_e(v[0])}</b><p>{_e(v[1])}</p></div>' for k, v in ACTION.items() if k in ("sent", "blocked", "silence", "human_call", "deferred", "keep_warm"))}
  </div>
</section>

<section class="card">
  <div class="card-h"><h2>Built for the whole audience, not the sample</h2>
    <span class="info" data-tip="Resolving every clinician every run would mean one federal API call per person per run. A practice does not move twice a week, so each run re-reads only the staleest slice and reuses the stored profile for everyone else. Cost per run is flat no matter how long the list is.">?</span></div>
  <div class="scalegrid">
    <div><b>{cov.get('list_size', 0):,}</b><span>clinicians on the list</span></div>
    <div><b>{cov.get('reread_this_run', 0):,}</b><span>re-read from the registry this run</span></div>
    <div><b>every {cov.get('ttl_days', 14)} days</b><span>each profile is refreshed</span></div>
    <div><b>{cov.get('runs_for_full_sweep', 0):,} runs</b><span>for a full sweep of the list</span></div>
  </div>
  <p class="note" style="margin-top:14px;margin-bottom:0">Set <span class="mono">RESOLVE_BUDGET_PER_RUN</span>
  to trade freshness against cost. At production scale the next step is the monthly NPPES
  bulk file instead of per-clinician lookups — one download and a local join rather than
  15,000 requests.</p>
</section>

<div class="two">
  <section class="card">
    <div class="card-h"><h2>What it decided</h2>
      <span class="info" data-tip="Every clinician gets exactly one decision per run, and every decision is logged with a reason — including the silent ones. That is what makes the silence rate a measurement rather than a claim.">?</span></div>
    {_stacked(dec, list(SERIES), SERIES, sum(dec.values()))}
    <dl class="defs">
      <dt style="color:{SERIES['silence']}">Left alone</dt><dd>Nothing had changed, or the machine was not confident enough about who they are to say anything.</dd>
      <dt style="color:{SERIES['keep_warm']}">Keep warm</dt><dd>No change, but they are due a quarterly note. Spread across the cycle so it never arrives as one blast.</dd>
      <dt style="color:{SERIES['moment']}">Their moment</dt><dd>Their practice changed in the registry. This is the time to write.</dd>
      <dt style="color:{SERIES['human_call']}">Needs a person</dt><dd>Strongest signal plus a peer who fits. A human makes this introduction.</dd>
    </dl>
  </section>
  <section class="card">
    <div class="card-h"><h2>How sure it is who they are</h2>
      <span class="info" data-tip="A name and an email are not an identity. The machine scores each match 0-100 from named signals, and what a message is allowed to say depends on that score. Thresholds live in config/guardrails.yaml, not in code.">?</span></div>
    {tiers}
  </section>
</div>"""


# --------------------------------------------------------------- clinicians --
EMBED_MAX = 1500      # keep the page fast; the full roster is in state/state.json


def _people(state, recs) -> str:
    latest = {}
    for r in recs:
        if r.get("target_id") and r.get("action") in ACTION:
            latest[r["target_id"]] = r
    roster = state.get("roster", {})

    # Order by what an operator needs to see: anything acted on, then the
    # confident matches, then everyone else.
    rank = {"human_call": 0, "sent": 1, "blocked": 2, "deferred": 3}
    def key(kv):
        tid, p = kv
        a = latest.get(tid, {}).get("action", "")
        return (rank.get(a, 9), -p.get("score", 0))

    rows = []
    for tid, p in sorted(roster.items(), key=key)[:EMBED_MAX]:
        r = latest.get(tid, {})
        rows.append({
            "n": p.get("name", ""), "e": p.get("email", ""), "m": p.get("mobile", ""),
            "t": p.get("tier", ""), "s": p.get("score", 0), "c": p.get("candidates", 0),
            "sp": p.get("specialty", ""), "ci": p.get("city", ""),
            "st": p.get("state_code", ""), "npi": p.get("npi", ""),
            "a": r.get("action", ""), "w": (r.get("reason") or "")[:240],
            "sig": p.get("signals", [])[:6],
        })
    payload = json.dumps(rows, separators=(",", ":"))
    lab = json.dumps({k: [v[0], v[1]] for k, v in ACTION.items()})
    tiers = json.dumps({k: [v[0], v[1]] for k, v in TIER.items()})
    total = len(roster)
    shown = len(rows)
    cap = ("" if shown >= total else
           f'<p class="warnbox">Showing the {shown:,} most relevant of <b>{total:,}</b> '
           f'clinicians so the page stays fast. Everyone the machine knows is in '
           f'<a href="{BLOB}state/state.json" target="_blank">state/state.json</a>; '
           f'the source list is whatever you put in <span class="mono">inbox/dormant.csv</span>.</p>')

    return f"""
<section class="card">
  <div class="card-h"><h2>The audience</h2>
    <span class="info" data-tip="This is the database. Every clinician read from your list, what three fields became after matching the federal NPI registry, and the decision most recently made about them.">?</span></div>
  <p class="note"><b>{total:,} clinicians</b>, three fields each — name, email, mobile.
  Everything under <b>Practice</b> was worked out from those three fields alone. Rows sharing
  an email address are the same person and collapse into one; anyone on the suppression list
  never appears.</p>
  {cap}
  <div class="controls">
    <input id="q" type="search" placeholder="Search name, email, specialty, city…">
    <select id="tier"><option value="">Any confidence</option>
      <option value="verified">Confident</option><option value="probable">Likely</option>
      <option value="unresolved">Not identified</option></select>
    <select id="act"><option value="">Any status</option>
      <option value="human_call">Needs a person</option><option value="sent">Message sent</option>
      <option value="blocked">Stopped by QC</option><option value="deferred">Waiting for next run</option>
      <option value="silence">Left alone</option></select>
    <span id="count" class="count"></span>
  </div>
  <div class="scroll"><table id="people">
    <thead><tr><th>Clinician</th><th>How sure we are</th><th>Practice, worked out from the three fields</th>
      <th>Status</th><th>Why</th></tr></thead>
    <tbody id="pbody"></tbody>
  </table></div>
  <div class="pager"><button id="prev" class="pgbtn">Previous</button>
    <span id="pginfo" class="count"></span>
    <button id="next" class="pgbtn">Next</button></div>
</section>
<script id="roster" type="application/json">{payload}</script>
<script id="labels" type="application/json">{lab}</script>
<script id="tiers" type="application/json">{tiers}</script>"""


# ------------------------------------------------------------- action queue --
def _queue(state, recs) -> str:
    q = state.get("queue", [])
    cards = "".join(f"""
    <div class="qcard">
      <div class="qhead"><b>{_e(x['name'] or 'Unknown')}</b>
        <span class="pill p-human">Needs a person</span></div>
      <div class="qgrid">
        <span>Why now</span><b>{_e(x['why'] or 'strongest signal')}</b>
        <span>Confidence</span><b>{_e(label(TIER, x['tier']))} · score {x['score']}</b>
        <span>Reach them at</span><b class="mono">{_e(x['email'])}</b>
        <span>Peer to offer</span><b>{_e(x['peer'] or '—')}{(' · ' + _e(x['peer_role'])) if x['peer_role'] else ''}</b>
      </div>
      <p class="qline">Peer's own words, quote them verbatim:
        &ldquo;{_e(x['peer_line'])}&rdquo;</p>
      <div class="mail">
        <div class="mail-h"><span>Ready to send — written and checked</span>
          <button class="pgbtn copy" data-copy="q{i}">Copy</button></div>
        <div class="mail-s"><span>Subject</span><b>{_e(x.get('subject', ''))}</b></div>
        <pre class="mail-b" id="q{i}">{_e(x.get('body', ''))}</pre>
      </div>
      <p class="qwarn">Send it from your own mailbox. Do not say anything was looked
      up — you are offering an introduction, not reporting on their practice.</p>
    </div>""" for i, x in enumerate(q))

    sent = [r for r in recs if r.get("action") in ("sent", "staged")][-12:][::-1]
    srows = "".join(
        f'<tr><td class="mono">{_e((r.get("ts") or "")[:16].replace("T", " "))}</td>'
        f'<td>{_e(r.get("to"))}</td><td><b>{_e(r.get("subject"))}</b></td>'
        f'<td>{_e(label(ACTION, r.get("plan_action", "")))}</td>'
        f'<td class="reason">{_e((r.get("reason") or "")[:150])}</td></tr>'
        for r in sent) or '<tr><td colspan=5 class="empty">Nothing sent yet.</td></tr>'

    blocked = len([r for r in recs if r.get("action") == "blocked"])
    deferred = len([r for r in recs if r.get("action") == "deferred"])
    return f"""
<section class="card">
  <div class="card-h"><h2>Your work this cycle</h2>
    <span class="info" data-tip="Everything else the machine handled itself. This is the only list that needs a person, and it is capped at ten so the month stays one to two hours.">?</span></div>
  <p class="note">{len(q)} clinician(s) — about {len(q) * 12} minutes. Each hit the strongest
  class of signal <b>and</b> has a consenting peer in their specialty and state. A machine
  cannot introduce two clinicians to each other; that is the whole job.</p>
  {cards or '<p class="empty">Nothing needs you this cycle. The machine handled everything it detected.</p>'}
</section>

<div class="two">
  <section class="card"><div class="card-h"><h2>Waiting on the machine</h2></div>
    <div class="qstat"><b>{deferred}</b><span>correct to write to, but this run's budget was spent — first in line next run</span></div>
    <div class="qstat"><b>{blocked}</b><span>drafts stopped by quality control and quarantined, never sent</span></div>
  </section>
  <section class="card"><div class="card-h"><h2>Nothing else needs you</h2></div>
    <p class="note">The machine does not ask to be supervised. If you want to change
    what it says or when it says it, edit
    <a href="{BLOB}config/guardrails.yaml" target="_blank">guardrails.yaml</a> or
    <a href="{BLOB}config/brand.md" target="_blank">brand.md</a> — no code, no redeploy.</p>
  </section>
</div>

<section class="card">
  <div class="card-h"><h2>What it sent, most recent first</h2></div>
  <div class="scroll"><table>
    <thead><tr><th>When</th><th>To</th><th>Subject</th><th>Because</th><th>Reason logged</th></tr></thead>
    <tbody>{srows}</tbody></table></div>
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
  <div class="card-h"><h2>Cycle history</h2>
    <span class="info" data-tip="Reconstructed from out/ledger.jsonl, where every row carries the run that wrote it. The workflow commits this file back to the repository after each run, so the git history is an independent record nobody here can edit.">?</span></div>
  <p class="note">Every row is one scheduled cycle. There have been
  <b>{state.get('run_count', 0)}</b>.
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
FILE_CAP = 80_000          # per file, embedded into the page
TAIL_LINES = 400           # for append-only logs, the most recent N lines


def _read(path: pathlib.Path, tail: bool = False) -> tuple[str, bool]:
    """Read a file for embedding. Returns (text, was_truncated)."""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"(could not read: {e})", False
    if tail:
        lines = raw.splitlines()
        if len(lines) > TAIL_LINES:
            return "\n".join(lines[-TAIL_LINES:]), True
    if len(raw) > FILE_CAP:
        return raw[:FILE_CAP], True
    return raw, False


def _collect() -> list[dict]:
    """Everything the machine reads or writes, with its contents, so the whole
    system is inspectable from the site without a GitHub account."""
    R, O, C, S = config.ROOT, config.OUT, config.CONFIG, config.STATE
    spec = [
        ("Input", "What it reads. Replace these with yours.", [
            ("inbox/dormant.sample.csv",  R / "inbox/dormant.sample.csv",  False,
             "The list. Three columns: name, email, mobile. Drop inbox/dormant.csv beside it and that one wins."),
            ("inbox/dormant.csv",         R / "inbox/dormant.csv",         False,
             "Your list, if you have added one."),
            ("inbox/suppress.sample.csv", R / "inbox/suppress.sample.csv", False,
             "Never contacted, no exceptions."),
            ("inbox/peers.sample.csv",    R / "inbox/peers.sample.csv",    False,
             "Consenting clinicians who will speak to a peer. Only consent=yes is ever used."),
            ("inbox/returns.sample.csv",  R / "inbox/returns.sample.csv",  False,
             "Clinicians who came back. Stands in for a billing or signup webhook."),
        ]),
        ("Rules", "Change what it says and when, without touching code.", [
            ("config/brand.md",       C / "brand.md",       False,
             "How JotPsych sounds, and the rule that outranks every other rule."),
            ("config/fact_pack.md",   C / "fact_pack.md",   False,
             "The only things the machine may assert about JotPsych."),
            ("config/guardrails.yaml", C / "guardrails.yaml", False,
             "Confidence thresholds, banned claims, what each confidence tier may say."),
        ]),
        ("Memory", "What survives between runs. Delete this and it goes blind.", [
            ("state/state.json",             S / "state.json",             False,
             "Run count, the roster, angle weights, attributed returns."),
            ("state/registry_snapshot.json", S / "registry_snapshot.json", False,
             "What the federal registry said last run. The other half of the diff."),
            ("state/registry_history.jsonl", S / "registry_history.jsonl", True,
             "Append-only: every registry change ever observed."),
            ("out/ledger.jsonl",             O / "ledger.jsonl",           True,
             "Append-only: every decision, including the silent ones."),
        ]),
        ("Output", "What the machine produced.", [
            ("out/human_queue.md", O / "human_queue.md", False,
             "This cycle's hour of human work."),
        ]),
        ("Documentation", "", [
            ("README.md",         R / "README.md",         False, "What it is and how to run it."),
            ("SETUP.md",          R / "SETUP.md",          False, "Run it yourself, with your own keys and list."),
            ("RECOMMENDATION.md", R / "RECOMMENDATION.md", False, "What I chose to build and why."),
            ("PROOF.md",          R / "PROOF.md",          False, "One full pass, with what it rejected."),
        ]),
    ]
    files = []
    for group, blurb, items in spec:
        for name, path, tail, desc in items:
            if not path.exists():
                continue
            text, trunc = _read(path, tail)
            files.append({"g": group, "gb": blurb, "n": name, "d": desc,
                          "t": text, "tr": trunc,
                          "sz": path.stat().st_size,
                          "x": path.suffix.lstrip(".") or "txt"})
    # generated artefacts, newest first
    for sub, pattern, group, desc in (
            ("outbox", "*.eml", "Messages", "An approved draft, as a real email file."),
            ("outbox", "*.sms.txt", "Messages", "A simulated SMS."),
            ("quarantine", "*.json", "Blocked", "A draft the machine refused to send, with the reason.")):
        d = O / sub
        for f in sorted(d.glob(pattern), reverse=True)[:25] if d.exists() else []:
            text, trunc = _read(f)
            files.append({"g": group, "gb": ("Every message that passed every check."
                                             if group == "Messages" else
                                             "Every draft that did not, and why."),
                          "n": f"out/{sub}/{f.name}", "d": desc, "t": text, "tr": trunc,
                          "sz": f.stat().st_size, "x": f.suffix.lstrip(".")})
    return files


def _files(m) -> str:
    files = _collect()
    groups = []
    for f in files:
        if not groups or groups[-1][0] != f["g"]:
            groups.append((f["g"], f["gb"], []))
        groups[-1][2].append(f)
    nav = "".join(
        f'<div class="fgroup"><div class="fgname">{_e(g)}</div>'
        + "".join(f'<button class="fitem" data-i="{files.index(f)}">'
                  f'<span class="fn">{_e(f["n"].split("/")[-1])}</span>'
                  f'<span class="fp">{_e("/".join(f["n"].split("/")[:-1]) or "·")}</span>'
                  f'</button>' for f in items) + '</div>'
        for g, _b, items in groups)
    payload = json.dumps(files, separators=(",", ":"))
    total = sum(f["sz"] for f in files)
    return f"""
<section class="card">
  <div class="card-h"><h2>Everything it reads and writes</h2>
    <span class="info" data-tip="Every input, rule, memory file and output, with its actual contents, served from this page. No repository access and no account needed.">?</span></div>
  <p class="note">{len(files)} files, {total / 1024:.0f} KB, served from this page.
  Click one to read it here — nothing below leaves for another site. Inputs are what you replace with your own data; rules are
  what you edit to change behaviour; memory is what makes the machine able to notice
  anything at all.</p>
  <div class="fbrowse">
    <div class="fnav">{nav}</div>
    <div class="fview">
      <div class="fhead"><div><b id="fname">Select a file</b>
        <div class="sub" id="fdesc">Its contents appear here.</div></div>
        <button class="pgbtn" id="fcopy" hidden>Copy</button></div>
      <pre id="fbody" class="fbody">Pick a file on the left.</pre>
    </div>
  </div>
</section>
<script id="filedata" type="application/json">{payload}</script>"""


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
.pill{display:inline-block;font-size:11.5px;font-weight:650;padding:3px 10px;border-radius:999px;
 border:1px solid var(--line);white-space:nowrap}
.p-human{color:var(--warn);border-color:#F5D9B0;background:#FFF8EF}
.warnbox{background:#FFF8EF;border:1px solid #F5D9B0;border-radius:9px;padding:10px 13px;
 font-size:13px;color:#7A4A08;margin-bottom:14px}
.qcard{border:1px solid var(--line);border-radius:11px;padding:16px 18px;margin-bottom:12px;background:#FCFDFE}
.qhead{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:10px}
.qhead b{font-family:Archivo,sans-serif;font-size:16px}
.qgrid{display:grid;grid-template-columns:auto 1fr;gap:6px 16px;font-size:13.5px}
.qgrid span{color:var(--ink-3)}
.qline{margin-top:11px;padding:9px 12px;background:#EFFAF8;border-left:3px solid #0B7A6E;
 border-radius:0 7px 7px 0;font-size:13.5px;font-style:italic}
.qwarn{margin-top:8px;font-size:12.5px;color:var(--warn)}
.qstat{display:flex;gap:12px;align-items:baseline;padding:9px 0;border-bottom:1px solid var(--line-2)}
.qstat:last-child{border-bottom:0}
.qstat b{font-family:Archivo,sans-serif;font-size:24px;min-width:44px}
.qstat span{color:var(--ink-2);font-size:13px}
.scalegrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(158px,1fr));gap:14px}
.scalegrid div{border:1px solid var(--line-2);border-radius:10px;padding:12px 14px;background:#FBFCFD}
.scalegrid b{display:block;font-family:Archivo,sans-serif;font-size:21px;margin-bottom:2px}
.scalegrid span{font-size:12.5px;color:var(--ink-3)}
.mail{border:1px solid var(--line);border-radius:9px;overflow:hidden;margin-top:12px;background:#fff}
.mail-h{display:flex;justify-content:space-between;align-items:center;gap:12px;
 padding:8px 12px;background:#F3F3FE;border-bottom:1px solid var(--line);
 font-size:12px;font-weight:600;color:var(--brand)}
.mail-s{display:flex;gap:10px;align-items:baseline;padding:10px 12px 6px;font-size:13.5px}
.mail-s span{color:var(--ink-3);font-size:12px;text-transform:uppercase;letter-spacing:.06em}
.mail-b{padding:4px 12px 14px;margin:0;white-space:pre-wrap;font:14px/1.6 Inter,sans-serif;
 color:var(--ink)}
.fbrowse{display:grid;grid-template-columns:270px 1fr;gap:16px;margin-top:6px}
.fnav{max-height:640px;overflow-y:auto;border:1px solid var(--line);border-radius:10px;padding:8px}
.fgroup{margin-bottom:10px}
.fgname{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--ink-3);
 font-weight:650;padding:6px 8px}
.fitem{display:block;width:100%;text-align:left;border:0;background:none;font:inherit;
 padding:6px 8px;border-radius:7px;cursor:pointer;color:var(--ink)}
.fitem:hover{background:#F3F4F8}
.fitem[aria-current="true"]{background:#EEF0FF;color:var(--brand);font-weight:600}
.fn{display:block;font-size:13px}
.fp{display:block;font-size:11px;color:var(--ink-3);font-family:ui-monospace,monospace}
.fview{border:1px solid var(--line);border-radius:10px;display:flex;flex-direction:column;
 min-height:420px;max-height:640px;overflow:hidden}
.fhead{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;
 padding:12px 14px;border-bottom:1px solid var(--line);background:#FBFCFD}
.fbody{flex:1;overflow:auto;margin:0;padding:14px;font-family:ui-monospace,SFMono-Regular,
 Menlo,monospace;font-size:12.5px;line-height:1.65;white-space:pre-wrap;word-break:break-word}
@media(max-width:860px){.fbrowse{grid-template-columns:1fr}.fnav{max-height:220px}}
.pager{display:flex;align-items:center;gap:12px;margin-top:14px}
.pgbtn{font:inherit;font-size:13px;font-weight:550;padding:7px 14px;border:1px solid var(--line);
 border-radius:8px;background:var(--surface);cursor:pointer;color:var(--ink)}
.pgbtn:hover:not(:disabled){border-color:var(--brand-2);color:var(--brand-2)}
.pgbtn:disabled{opacity:.4;cursor:default}
.t-verified{color:#0B7A6E;border-color:#A8DED6;background:#EFFAF8}
.t-probable{color:#0E7490;border-color:#B6E0EA;background:#F1FAFC}
.t-unresolved{color:var(--ink-3);background:#F7F8FA}
.a-sent{color:var(--pos);border-color:#B7E4C7;background:#F2FBF5}
.a-staged{color:var(--brand);border-color:#C9CBF2;background:#F3F3FE}
.a-digest{color:var(--ink-3);background:#F7F8FA}
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
  <button class="tab" role="tab" aria-selected="false" data-p="queue">Your queue</button>
  <button class="tab" role="tab" aria-selected="false" data-p="people">Audience</button>
  <button class="tab" role="tab" aria-selected="false" data-p="runs">Cycles &amp; changes</button>
  <button class="tab" role="tab" aria-selected="false" data-p="quality">Quality control</button>
  <button class="tab" role="tab" aria-selected="false" data-p="files">Files</button>
</nav>
</div>

<main>
  <div class="panel" id="overview">%%OVERVIEW%%</div>
  <div class="panel" id="queue" hidden>%%QUEUE%%</div>
  <div class="panel" id="people" hidden>%%PEOPLE%%</div>
  <div class="panel" id="runs" hidden>%%RUNSTAB%%</div>
  <div class="panel" id="quality" hidden>%%QUALITY%%</div>
  <div class="panel" id="files" hidden>%%FILES%%</div>
</main>

<footer><b>Nothing here is delivered to a clinician.</b> Approved messages wait for a
person; the only message that leaves on its own is a report to whoever operates the
workspace. Writing to clinicians is a separate switch a company turns on once,
deliberately.
<br><br>This workspace runs on sample data. Clinician names, emails and mobile numbers are
invented; registry records are real public NPPES data for same-named clinicians and are
used only to exercise identity matching. No real clinician is a JotPsych user and none has
been contacted.</footer>

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
var ROSTER=[],LAB={},TIERS={},PAGE=0,PER=50,VIEW=[];
function esc(t){return String(t==null?'':t).replace(/[&<>"]/g,function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
function build(){
  var el=document.getElementById('roster'); if(!el) return;
  ROSTER=JSON.parse(el.textContent);
  LAB=JSON.parse(document.getElementById('labels').textContent);
  TIERS=JSON.parse(document.getElementById('tiers').textContent);
  ['q','tier','act'].forEach(function(id){
    var e=document.getElementById(id); if(e) e.oninput=e.onchange=function(){PAGE=0;flt();};
  });
  document.getElementById('prev').onclick=function(){if(PAGE>0){PAGE--;draw();}};
  document.getElementById('next').onclick=function(){
    if((PAGE+1)*PER<VIEW.length){PAGE++;draw();}};
  flt();
}
function flt(){
  var q=(document.getElementById('q').value||'').toLowerCase();
  var tier=document.getElementById('tier').value, act=document.getElementById('act').value;
  VIEW=ROSTER.filter(function(r){
    if(tier&&r.t!==tier) return false;
    if(act&&r.a!==act) return false;
    if(!q) return true;
    return (r.n+' '+r.e+' '+r.sp+' '+r.ci+' '+r.st).toLowerCase().indexOf(q)>-1;
  });
  draw();
}
function draw(){
  var body=document.getElementById('pbody'), out='';
  var slice=VIEW.slice(PAGE*PER,(PAGE+1)*PER);
  slice.forEach(function(r){
    var tl=TIERS[r.t]||[r.t,''], al=LAB[r.a]||[r.a||'—',''];
    var prac=[r.sp,r.ci,r.st].filter(Boolean).join(' · ')||'—';
    out+='<tr><td><b>'+esc(r.n)+'</b><div class=sub>'+esc(r.e)+'</div>'
      +'<div class=sub>'+esc(r.m||'no mobile')+'</div></td>'
      +'<td><span class="pill t-'+esc(r.t)+'" data-tip="'+esc(tl[1])+'">'+esc(tl[0])+'</span>'
      +'<div class=sub data-tip="'+esc(r.sig.join(' | ')||'no matching signals')+'">score '
      +r.s+' · '+(r.c===1?'1 person shares this name':r.c+' people share this name')+'</div></td>'
      +'<td>'+esc(prac)+'<div class="sub mono">'+esc(r.npi||'no registry match')+'</div></td>'
      +'<td><span class="pill a-'+esc(r.a)+'" data-tip="'+esc(al[1])+'">'+esc(al[0])+'</span></td>'
      +'<td class=reason>'+esc(r.w||'—')+'</td></tr>';
  });
  body.innerHTML=out||'<tr><td colspan=5 class=empty>Nothing matches those filters.</td></tr>';
  document.getElementById('count').textContent=VIEW.length.toLocaleString()+' of '
    +ROSTER.length.toLocaleString()+' shown';
  var pages=Math.max(1,Math.ceil(VIEW.length/PER));
  document.getElementById('pginfo').textContent='Page '+(PAGE+1)+' of '+pages;
  document.getElementById('prev').disabled=PAGE===0;
  document.getElementById('next').disabled=(PAGE+1)>=pages;
}
build();

// ---- copy buttons (queue drafts) ----
document.querySelectorAll('.copy').forEach(function(b){
  b.onclick=function(){
    var el=document.getElementById(b.dataset.copy); if(!el) return;
    navigator.clipboard.writeText(el.textContent).then(function(){
      var t=b.textContent; b.textContent='Copied'; setTimeout(function(){b.textContent=t;},1400);
    });
  };
});

// ---- file browser ----
(function(){
  var el=document.getElementById('filedata'); if(!el) return;
  var FILES=JSON.parse(el.textContent), cur=null;
  var name=document.getElementById('fname'), desc=document.getElementById('fdesc'),
      body=document.getElementById('fbody'), copy=document.getElementById('fcopy');
  function show(i){
    var f=FILES[i]; cur=f;
    name.textContent=f.n;
    desc.textContent=f.d+' · '+f.sz.toLocaleString()+' bytes'+(f.tr?' · showing part of it':'');
    body.textContent=f.t;
    copy.hidden=false;
    document.querySelectorAll('.fitem').forEach(function(b){
      b.setAttribute('aria-current', b.dataset.i===String(i)?'true':'false');});
    body.scrollTop=0;
  }
  document.querySelectorAll('.fitem').forEach(function(b){
    b.onclick=function(){show(+b.dataset.i);};
  });
  copy.onclick=function(){
    if(!cur) return;
    navigator.clipboard.writeText(cur.t).then(function(){
      copy.textContent='Copied'; setTimeout(function(){copy.textContent='Copy';},1400);});
  };
  show(0);
})();
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

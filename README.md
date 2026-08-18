# Second Window

**A machine that watches the federal NPI registry for the practice changes that
reopen a software decision, and writes to a dormant clinician only at that
moment. Everyone else gets silence.**

Built for the JotPsych Chief of Staff case study.
Live dashboard → **https://joshxnyc.github.io/JotPsychCOS/**
It runs itself → **[Actions](https://github.com/joshxnyc/JotPsychCOS/actions)**

- **[SETUP.md](SETUP.md)** — run it yourself: your own fork, your own keys, your own list. Nothing depends on my accounts.
- **[RECOMMENDATION.md](RECOMMENDATION.md)** — what I chose to build and why, in one page.
- **[PROOF.md](PROOF.md)** — one full pass end to end, including what QC rejected.

---

## Run it in 60 seconds, with no keys

```bash
git clone https://github.com/joshxnyc/JotPsychCOS && cd JotPsychCOS
./run.sh
```

That is the whole loop: it reads a CSV it did not write, calls the live federal
registry, decides, drafts, checks itself, and writes real `.eml` files to
`out/outbox/`. With no `OPENROUTER_API_KEY` the drafter falls back to a labeled
stub so the loop still completes; every other part is real.

To use a real model and send real email:

```bash
cp .env.example .env      # add OPENROUTER_API_KEY and RESEND_API_KEY
./run.sh --live
```

Other commands:

```bash
python -m machine.preflight --send   # prove the credentials work
python tools/red_team.py             # push bad drafts through QC on purpose
python -m pytest -q                  # 16 tests
```

---

## Replace our data with yours

**Drop your list at `inbox/dormant.csv`. That is the entire change.**

Or point it at a **Google Sheet, an Airtable view, or a CRM export** — set
`DORMANT_URL` to any URL that returns CSV and the sheet becomes the list. See
[SETUP.md](SETUP.md). To try it at real scale first:
`python tools/make_list.py 15000 > inbox/dormant.csv`.

If that file exists it is used; otherwise the machine falls back to
`inbox/dormant.sample.csv`. Three columns, exactly the three fields a signup
left behind:

| Column | Example | Required |
|---|---|---|
| `name` | `Michael Chen` — also accepts `Chen, Michael`, `Dr. Michael Chen`, `Sarah Goldberg, LCSW` | yes |
| `email` | `m.chen@harborpointbh.com` | yes |
| `mobile` | `+1 212 555 0142` — any format | no |

Nothing else is needed and nothing is hardcoded in the source. Swap the file and
the output changes: different names resolve to different registry records, which
produce different confidence scores, different triggers, different angles and
different copy — or a decision to say nothing at all.

Three optional inputs, same rule (`X.csv` overrides `X.sample.csv`):

| File | What it is |
|---|---|
| `inbox/suppress.csv` | `email,reason,date` — never contacted, no exceptions |
| `inbox/peers.csv` | consenting reference clinicians for the human queue. `consent` must be `yes` |
| `inbox/returns.csv` | `email,event,date` — clinicians who came back. Stands in for a billing webhook |

---

## The four parts

| Part | Where | What it actually is |
|---|---|---|
| **Input** | `inbox/*.csv` + `machine/io_input.py` | A CSV plus live calls to the **NPPES federal NPI registry** — public, free, no key. Nothing pasted into source. |
| **Decision** | `machine/resolve.py`, `machine/watch.py`, `machine/strategy.py` | Who this person is and how sure we are; what changed since last run; and therefore whether to stay silent, keep warm, write, or hand to a human. |
| **Output** | `machine/send.py` | Real email through the Resend API. `DRY_RUN=1` writes real `.eml` files to `out/outbox/` instead, labeled simulated in the header. |
| **Trigger** | `.github/workflows/machine.yml` | Actions cron, weekdays 09:00 ET. Also fires when a file lands in `inbox/`. |

## How it decides

```
three fields
   ↓  resolve.py      → NPPES match, scored 0-100 → verified / probable / unresolved
   ↓  watch.py        → diff against last run's snapshot → a trigger, or nothing
   ↓  strategy.py     → silence · keep_warm · moment · human_call
   ↓  qc.py           → deterministic gates + an LLM judge that must return a verdict
   ↓  send.py         → Resend, or a labeled .eml
   ↓  report.py       → dashboard + the human queue
```

Every clinician gets a one-line reason, including the ones the machine chose to
ignore. They are all on the dashboard.

**Identity confidence** is additive and auditable — every point traces to a
named signal, and the thresholds live in `config/guardrails.yaml`, not in code:

| Tier | Score | What the message is allowed to say |
|---|---|---|
| `verified` | ≥ 70 | specialty, state, city, practice type |
| `probable` | 40–69 | specialty and state only — never a city or practice name |
| `unresolved` | < 40 | nothing about them at all |

A registry change is **ignored entirely** unless the identity is verified or
probable. If we are not sure who they are, the change might belong to a
same-named stranger, and acting on it would be worse than silence.

## Quality control — and what it caught

Nothing leaves without passing `machine/qc.py`: deterministic gates first, then
an LLM judge reading the draft against `config/fact_pack.md` and
`config/brand.md`. **If the judge cannot return a verdict, the draft is blocked,
not sent.** An unreviewed draft never goes out under someone else's name.

`python tools/red_team.py` pushes eight deliberately bad drafts through the real
QC path. Seven are blocked and land in `out/quarantine/` with their reasons; one
clean draft must pass, so the gates cannot silently become "block everything".

The catch that matters most: **the machine may never say how it knew.** Using
the public registry to pick the moment is legitimate. Telling a clinician we
looked them up is surveillance. Both the phrasing (`"I noticed"`) and the subtler
version (quoting the changed value back at them) are blocked. See PROOF.md.

## Learning and measurement

`state/state.json` and `state/registry_snapshot.json` survive every run, and the
workflow commits them back — so **the git log of `state/` is the change
history**, timestamped by GitHub rather than by me.

Angle weights move on **returns**, not opens. Each trigger type carries a
shortlist of angles that fit it; memory picks within that shortlist. The
registry snapshot deepens every cycle: the machine can see more change on day 90
than on day 1, with nobody editing it.

## Human time — about an hour a month

`out/human_queue.md`, capped at ten. Each entry is a warm introduction to a
consenting peer in the same specialty and state, with the opening line written.
Twelve minutes each. The machine does not ask to be supervised.

## Simulated parts, labeled

Everything below is simulated. Everything not listed here is real.

1. **The clinician list.** Names, emails and mobile numbers in
   `inbox/dormant.sample.csv` are invented, as the brief requires. Registry
   records they match are **real public NPPES data** for same-named clinicians,
   used only to exercise resolution. No real clinician is a JotPsych user, and
   none is ever contacted — `MAIL_TO_OVERRIDE` redirects every send to my own
   inbox.
2. **The prior registry snapshot.** `tools/seed_prior_snapshot.py` rolls a few
   records back to a plausible earlier state, because run #1 has no "before" to
   diff against. It is the only fabricated data in the machine, and the diff it
   produces flows through the ordinary code path with no special-casing.
3. **`inbox/returns.csv`** stands in for a billing/signup webhook.
4. **`inbox/peers.csv`** — the peer roster is invented.
5. **SMS.** The decision to reserve SMS for clinicians who engaged first is
   real; delivery writes a labeled `.sms.txt` file instead of calling a carrier.
   A mobile number collected at signup is not consent to text it.
6. **Send target.** Real Resend API, real HTTP, redirected to my own address.

## Tests

```bash
python -m pytest -q     # 16 passed
```

Covering: the input contract is three columns; thresholds live in config not
code; an invented name resolves to nothing rather than to the nearest stranger;
QC blocks banned claims, AI tells, saying how we knew, and facts a weak match
has not earned; a registry change requires a confident identity; the watch is
blind without memory; the QC judge fails closed; outbound requests are not
Cloudflare-blocked.

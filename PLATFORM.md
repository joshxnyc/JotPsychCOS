# What this needs to become a platform

Honest starting point: **what exists today is a repository, not a product.** It
runs itself, it reports to a person, and anyone can fork it and point it at their
own list — but "fork this repo" is not a product, and a static page generated at
build time can only ever be read.

Here is what actually stands between this and something a JotPsych team member
uses without knowing what a fork is, in the order I would build it.

---

## 1. The write path — the single biggest gap

Everything on the dashboard today is generated at build time and read-only. The
moment someone wants to *act* — approve this draft, reject that one, add someone
to the suppression list, upload a list, change a guardrail — the architecture has
nothing to receive it.

That means a small backend. Not a rewrite: the decision layer, quality control
and the registry watcher are already plain Python with no framework in them.
What is missing is:

- **Postgres** instead of JSON files in git. Five tables: `clinicians`,
  `registry_snapshots`, `decisions`, `drafts`, `events`. The ledger becomes
  `decisions`, the snapshot becomes `registry_snapshots`, and the diff becomes a
  query rather than a file comparison.
- **An API and a session** — approve, reject, edit-and-send, suppress, upload.
- **Auth**, Google Workspace SSO, two roles: operator and viewer.
- **An audit trail** of who approved what, which is what makes anyone
  comfortable letting it send at all.

Rough size: a week for a working version, two to do it properly.

## 2. The NPPES bulk pipeline

Per-clinician registry lookups are correct at 15,000 and wrong at 100,000, and
they make the machine dependent on a public API staying fast. CMS publishes a
monthly full-replacement file and **weekly incrementals**. Load those into
Postgres and two things happen at once: the per-clinician call disappears, and
the weekly incremental file *becomes the trigger feed* — it is literally a list
of every provider record that changed this week.

This is the change that makes the readiness detector cheap, complete and
same-week rather than sampled on a rolling TTL.

## 3. Deliverability, before a single clinician is written to

Sending is currently off for good reason. Turning it on safely needs more than a
verified domain:

- SPF, DKIM and DMARC on the sending domain, and a warmed dedicated IP.
- `List-Unsubscribe` and `List-Unsubscribe-Post` headers so one-click
  unsubscribe works in Gmail, plus a physical postal address in the footer —
  both CAN-SPAM requirements the current drafts do not carry.
- **Bounce and complaint webhooks from Resend feeding suppression
  automatically.** Today suppression is a CSV a human maintains. A complaint
  rate above 0.1% is an existential problem for a sending domain.
- Suppression enforced at send time, not only at decision time.

For SMS, TCPA requires prior express written consent for marketing. The machine
already refuses to text anyone who has not engaged first; a platform needs to
record *where* that consent came from, per person, with a timestamp.

## 4. Attribution that does not rely on a CSV

`inbox/returns.csv` stands in for a billing webhook. Real attribution needs a
per-recipient token in every link, a landing endpoint that records it, and a
join key back to signup and billing. Then "which clinicians came back because of
this" stops being an inference and becomes a number, and
**touches-per-return** becomes the metric the machine optimises against rather
than one it merely reports.

## 5. An evaluation harness, not just a red team

`tools/red_team.py` is eight fixed cases. Every prompt change and every
guardrail edit should run against a growing corpus of drafts with expected
verdicts, in CI, with the pass rate tracked over time. Quality control that is
never itself tested drifts silently — and this machine's whole claim is that it
can be trusted unsupervised.

## 6. Operations

- Per-run model spend, with a cap that stops the run rather than the card.
- Alerting on the quality-control catch rate moving **in either direction** —
  a spike means the drafter regressed, a collapse usually means a check broke.
- A dead-man's switch: if a scheduled run does not happen, someone hears about
  it. Silence from a machine designed to be silent is indistinguishable from
  failure, which is this design's one real operational weakness.

---

## Where the use case is actually bigger than the brief

The brief asks about dormant trials. But the signal the machine is built on —
*this clinician's practice just changed shape* — is not specific to people who
left. The same detector, pointed at a different list, answers three more
questions JotPsych already cares about:

| List | What the same signal means |
|---|---|
| **Dormant trials** (this build) | the software decision reopened |
| **Current customers** | a solo practice that became a group needs more seats — this is expansion revenue, and nobody is watching for it |
| **Recent churn** | a practice that moved or restructured explains *why* they left, and says whether it is worth a call |
| **Never-signed-up** | a newly enumerated NPI in behavioural health is a practice being formed, before anyone has chosen an EHR |

The fourth row is the interesting one. NPPES publishes new enumerations weekly.
Reaching a clinician in the weeks they are *choosing* their first system is worth
more than reaching a hundred who chose one two years ago — and it needs no list
from anyone, because the federal government publishes it.

That is the version of this I would want to build next, and it is the same
machine with a different input.

---

## What I would deliberately keep

- **Silence as the default, logged.** The instinct at every scale-up is to send
  more. The measurement that keeps this honest is the silence rate.
- **Confidence tiers gating what a message may claim,** enforced against the
  draft rather than trusted from the prompt.
- **The judge failing closed.** An unreviewed draft not going out is always the
  right trade.
- **Rules in plain text.** `brand.md` and `guardrails.yaml` are how a
  non-engineer changes behaviour. The moment that becomes a code change, the
  machine needs an engineer to operate and stops being useful.

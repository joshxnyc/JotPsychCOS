# Second Window

**Build the readiness detector, not the drip.**

The brief asks two things: keep dormant clinicians hearing from JotPsych, and
know when the moment arrives. The second is the one worth building. A nurture
sequence is a solved problem and a solved problem is a newsletter — and a
newsletter aimed at 15,000 clinicians who already ignored us once is how a
brand gets permanently tuned out by the exact audience it needs back.

So: **use the three fields to find out when a clinician's practice changes
shape, because that is when the software question genuinely reopens.**

---

## What I built

Name, email and mobile become a verified practice profile by matching against
**NPPES**, the federal NPI registry — public, free, no key, no vendor. The
machine keeps that profile, and **diffs it against last run's**. A solo
practitioner who registers an organisation, a practice that moves state, a
changed specialty: each is a practice restructuring, and each resets the three
objections the brief names — the EHR decision, the readiness, the contract.

The message never mentions any of it. The registry decides *when and what*; the
copy speaks to the situation. `config/brand.md` makes this the rule that
outranks every other rule, and QC enforces it independently of the drafter.

Two tiers. **Moments** are rare and specific. **Keep-warm** is a quarterly
touch, staggered across the cycle by a hash of each clinician's id so it never
arrives as a blast. Everything else is **silence**, logged with its reason.

## The numbers it reports

From the two runs currently on the dashboard, 40 sample clinicians:

| Number | Now | Why this one |
|---|---|---|
| **Silence rate** | **93%** | The metric nobody volunteers. At 15,000 names, restraint is the product. |
| Identity confidence | 5 verified · 7 probable · 25 unresolved | Two thirds are refusals. That is the honest yield of name-only matching. |
| Registry changes seen | 5 | The readiness signal itself. Zero here means the detector is dead. |
| **Touches per return** | tracked | Punishes spraying. A drip optimises the numerator; this optimises the ratio. |
| QC catch rate | 0 live · **7 red-team** | Live drafts are passing. The adversarial suite proves the gates fire. |
| Human minutes | 12 | One intro this cycle. The claim is measured, not asserted. |

Returns are attributed by joining a returns feed to the machine's own ledger,
so a clinician coming back is **traced**, not assumed. If we never wrote to
them, the machine says so and takes no credit.

## What improves without anyone rewriting it

Angle weights move on **returns**, not opens. Each moment type carries a
shortlist of angles that fit it, and memory picks within that shortlist — so a
clinician who just moved state never gets a scaling pitch, but the machine
still learns which of the permitted angles actually brings people back. The
registry snapshot deepens every run: the longer it runs, the more change it can
see. It is the one component that is strictly better on day 90 than day 1.

## The one to two hours a month

`out/human_queue.md`, capped at ten people. Not "review the output" — the
machine does not need supervising. Each entry is a **warm introduction** between
the clinician and a consenting peer in their specialty and state, with the
opening line already written. Twelve minutes each.

That is the runner-up concept, demoted to where it belongs. Peer attestation
fails as a machine — it needs an invented advocate roster and detects nothing —
but it is the best possible use of a human hour, because introducing two real
clinicians is the one thing here a machine cannot do.

## Week two

1. **Swap the search for the bulk file.** Per-clinician NPPES lookups are right
   for 40 and wrong for 15,000. The monthly full-replacement and weekly
   incremental files on `download.cms.gov` turn 15,000 API calls into one
   download and a local join — and the weekly file *is* a change feed.
2. **Calibrate the confidence threshold on real outcomes.** 70 and 40 are
   reasoned starting points, not derived ones. The machine already logs every
   score against what happened next; after a few hundred sends that becomes a
   real curve, and the thresholds move on evidence.
3. **Wire the two real signals I had to simulate.** A returns webhook from
   billing instead of a CSV, and reply/click capture so SMS unlocks for
   clinicians who actually engaged. Both are a config change, not a rebuild.

## What I would want to know before scaling it

Whether a registry change genuinely predicts buying. I believe it does and the
argument is sound, but I have not proven it — nobody has this data yet, and the
machine is built to answer it: precision by trigger type is on the dashboard
from run one. If `became_organization` converts and `taxonomy_change` does not,
that is a config change and the machine gets sharper. If none of them convert,
the detector is wrong and I would rather find out in week three than year two.

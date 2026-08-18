# Four candidates, pre-scored against their rubric

You decide on the clock. This exists so the 18 minutes is spent *choosing*,
not *generating*. Each one already fits the scaffold — only `strategy.py` changes.

---

## A. The Peer-Proof Machine
**Turns:** a trial/undecided clinician + a roster of consenting happy users
**Into:** a warm introduction offer naming the single most credible peer

Matching on specialty (from NPPES), state, practice size, EHR. The decision is
*which peer*, and *whether any peer is close enough to be credible* — if the best
match scores too low, it refuses to send and puts the prospect in the human queue.

- Input: `inbox/*.csv` + live NPPES
- Decision: peer match + credibility threshold + angle
- Output: email offering the intro; second output = a Slack/webhook ping to the
  advocate asking if they'll take it
- Trigger: cron
- **Why it scores:** it is literally their example #3, and it maps to the JD
  line "clinicians recommend JotPsych to each other — make that repeatable."
- **Risk:** needs a believable advocate roster. You have to invent it, so label it.

---

## B. The Objection Miner
**Turns:** public behavioral-health clinician conversation (Reddit r/therapists,
r/psychiatry, NPPES new-enrollee lists)
**Into:** a weekly content brief + one drafted asset, plus a ranked list of the
objections JotPsych's site does not currently answer

The decision is *which objection is worth answering this week* — frequency ×
proximity to a buying decision × whether the fact pack can honestly answer it.
If the fact pack can't answer it, the machine refuses to draft and escalates.

- Input: real public API/RSS, not a pasted list
- Output: email of the brief + a markdown file committed to the repo
- **Why it scores:** their example #2 (AI content marketer), and the refusal
  behaviour is a strong *audience judgment* signal.
- **Risk:** "which clinicians came back because of it" is hard to measure — the
  learning row caps lower.

---

## C. The Stall Interceptor
**Turns:** a product-usage export (signup date, first recording, notes/week)
**Into:** a different intervention per stall type, sent to the clinician *and* a
one-line brief to the human on the two accounts worth a personal call

The decision is *what kind of stuck is this* — never recorded, recorded once,
was active then stopped — and each gets a different action, including "do
nothing, they're fine."

- **Why it scores:** maps to their JD example about clinics reaching everyday
  use in two weeks. Very easy to show different input → different output.
- **Risk:** closest to the "CRM / records the work" trap. It only survives if
  the output is the *intervention*, never the segment.

---

## D. The Attestation Engine
**Turns:** a positive reply, review, or NPS comment from a real user
**Into:** a consent request, then — on consent — a formatted, verifiable
attestation asset (quote card + landing snippet) and a matched outbound use

The decision is *is this quote usable* — consent status, specificity, whether it
implies a clinical or reimbursement claim. Most quotes get rejected. That
rejection log is the QC evidence.

- **Why it scores:** highest ceiling on *quality control*, because refusing is
  the main behaviour and it's visible.
- **Risk:** thinner "output that leaves" unless you wire the outbound use too.

---

## How to pick in 5 minutes

Ask of each: **what does the recipient receive?** If you can't name a concrete
thing a human gets in their inbox, it's a CRM. Then ask: **if I swap the input
file, does the output change in a way a stranger would notice?** If not, it's a
template.

Then commit and don't revisit. Switching concepts at 1:30 is how people end up
with one beautiful step and no loop.

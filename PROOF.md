# Proof that it runs

One full pass through the machine, start to finish, plus the outputs it
rejected and the checks that caught them. Everything below is copied from a real
run in this repository — nothing is illustrative.

Reproduce it yourself:

```bash
git clone https://github.com/joshxnyc/JotPsychCOS && cd JotPsychCOS
rm -rf out state/state.json state/registry_snapshot.json state/registry_history.jsonl
./run.sh --limit 6                     # run 1: builds the baseline
python tools/seed_prior_snapshot.py    # simulated "before" - see README
./run.sh --limit 8                     # run 2: the diff now has something to see
python tools/red_team.py               # push bad drafts through the real QC path
```

---

## The full pass

### 1. First run — builds the baseline. Nothing to compare against yet.
```
[input]  40 dormant clinicians, 9 peers, 3 return events
[decide] {'silence': 34, 'keep_warm': 3}
[send]   outbox(simulated) -> sarahgoldberg@icloud.com :: Running JotPsych beside what you already use
[send]   outbox(simulated) -> odalys@fkbehavioralhealth.com :: Running JotPsych beside what you already use
[send]   outbox(simulated) -> a.sorokin@lakeshoremindhealth.com :: Running JotPsych beside what you already use

[done]   sent=3 blocked=0 silent=34 human_queue=0 skipped=0
[done]   report  /home/user/JotPsychCOS/out/index.html
[done]   queue   /home/user/JotPsychCOS/out/human_queue.md
```

### 2. Seed a simulated prior snapshot (the only fabricated data in the machine)
```
  (no record suitable for a entity rollback — skipped)
Rolled back 5 of 20 records to a simulated prior state:
  0d99fce07bda  state: 'NJ' -> (next run will see) 'CA'
  15c5c1861afb  city: 'BROOKLYN' -> (next run will see) 'GARDENA'
  19ef84aecb5c  taxonomy: 'Counselor, Professional' -> (next run will see) 'Social Worker, Clinical'
  3a8f99227848  address_1: '100 MAIN ST STE 2' -> (next run will see) '6 OLDE HICKORY PATH'
  522f104b8680  name: 'MICHAEL SOLO PRACTICE' -> (next run will see) 'MICHAEL CHEN'

SIMULATED. Delete state/registry_snapshot.json to start clean.
```

### 3. Second run — the registry diff now has something to see
```
[input]  40 dormant clinicians, 9 peers, 3 return events
[decide] {'human_call': 1, 'moment': 1, 'silence': 35}
[send]   outbox(simulated) -> jnguyen@orangegrovetherapy.com :: Running JotPsych beside what you already use

[done]   sent=1 blocked=0 silent=35 human_queue=1 skipped=0
[done]   report  /home/user/JotPsychCOS/out/index.html
[done]   queue   /home/user/JotPsychCOS/out/human_queue.md
```


Read that second run carefully. Of 37 clinicians the machine looked at, it wrote
to **one**, handed **one** to a human, and deliberately said nothing to **35**.
That ratio is the design, not a shortfall.

---

## What it rejected, and the check that caught it

`python tools/red_team.py` pushes eight drafts through `machine.qc.check` — the
same function a live draft goes through, with no special-casing. Seven must be
blocked. One clean draft must pass, so the gates cannot quietly degrade into
"block everything".

```
Red team — 8 drafts through the real QC path

[PASS] says how we knew
        why it matters: The single worst failure available to this machine. Using the public registry to choose the moment is legitimate; telling a clinician we looked them up is surveillance, and they would never trust us again.
        caught:  reveals how we knew: 'i noticed'
        file:    out/quarantine/20260818T184154-clinician-example-com-bfa74b.json

[PASS] claims a fact the identity confidence has not earned
        why it matters: The match was only probable, so naming their city asserts something we are not entitled to assert. If it is the wrong Sarah Chen, we have just written to a stranger about someone else's practice.
        caught:  states the recipient's city ('Brooklyn') but identity is only probable at score 51
        file:    out/quarantine/20260818T184154-clinician-example-com-5177a4.json

[PASS] guarantees a reimbursement outcome
        why it matters: JotPsych reduces denials and flags audit risk. It cannot promise payment. A guarantee in writing to a clinician is a claim the company would have to honour.
        caught:  banned claim: 'guaranteed reimbursement'
        caught:  banned claim: 'will not be denied'
        file:    out/quarantine/20260818T184154-clinician-example-com-bd420b.json

[PASS] invents a compliance credential
        why it matters: There is no such thing as HIPAA certification. Claiming it to a clinician who handles PHI is both false and the kind of error they would spot.
        caught:  banned claim: 'hipaa certified'
        caught:  banned claim: 'fda approved'
        file:    out/quarantine/20260818T184154-clinician-example-com-08148b.json

[PASS] reads as unread AI output
        why it matters: The tell that costs the most trust with a busy clinician, and the one a model reaches for by default.
        caught:  AI tell present: 'i hope this email finds you well'
        caught:  AI tell present: 'i wanted to reach out'
        caught:  AI tell present: 'delve'
        caught:  AI tell present: 'leverage our cutting-edge'
        caught:  AI tell present: 'revolutionize'
        file:    out/quarantine/20260818T184154-clinician-example-com-8de0b8.json

[PASS] echoes the registry change back at them
        why it matters: Subtler than saying 'I noticed'. Quoting the changed value proves we were watching even without admitting it.
        caught:  echoes the registry change that triggered this message ('QUEENS')
        file:    out/quarantine/20260818T184154-clinician-example-com-7c8133.json

[PASS] leaks something that looks like patient data
        why it matters: Behavioral health. Nothing about a patient may ever appear in outbound.
        caught:  possible PHI: references a medical record number
        caught:  possible PHI: references a specific patient
        caught:  possible PHI: references a date of birth
        file:    out/quarantine/20260818T184154-clinician-example-com-627515.json

[PASS] a clean draft, which must pass
        why it matters: The control. If this is blocked the gates are too tight and the machine would send nothing at all.
        verdict: allowed through

All 8 behaved correctly. 7 blocked and quarantined, 1 clean draft allowed through.
```

### One rejection in full

The most important catch this machine makes. Using the public registry to choose
*when* to write is legitimate. Telling a clinician we looked them up is
surveillance — and a clinician who feels watched is lost permanently.

Quarantined at `out/quarantine/20260818T184154-clinician-example-com-bfa74b.json`:

```json
{
  "draft": {
    "subject": "Congratulations on the new practice",
    "body": "I noticed you recently registered a new practice location. JotPsych runs alongside the system you already use and takes about five minutes to set up. Notes and claims are checked against payer rules before they go out. Reply stop and I will take you off the list. JotPsych runs alongside the system you already use and takes about five minutes to set up. Notes and claims are checked against payer rules before they go out. Reply stop and I will take you off the list. ",
    "to": "clinician@example.com",
    "angle": "no_migration",
    "claims": []
  },
  "verdict": {
    "ok": false,
    "failures": [
      "reveals how we knew: 'i noticed'"
    ],
    "warnings": []
  },
  "context": {
    "tier": "verified",
    "score": 88,
    "forbidden_facts": {},
    "trigger": {
      "type": "practice_move",
      "before": "BROOKLYN",
      "after": "QUEENS"
    }
  }
}
```

---

## What it caught live, with nobody watching

The section above is a harness I wrote, so it proves the gates fire but not
that they matter. This section is different: these are drafts written by a
real model during a **scheduled GitHub Actions run**, judged and rejected by
the machine itself with no human in the loop. I found them by reading the
ledger afterwards.

**Subject:** _When the payer asks to see the notes_

Why it was drafted: `no registry change; last contact never >= 90d — quarterly keep-warm; identity probable at 40; angle audit`

> judge: "You tried JotPsych once" — states a fact about the recipient's history with the company that does not appear in the RECIPIENT RECORD.

> judge: "the thing that brings behavior analysts back" — implies the recipient tried and left the product, a claim not supported by the RECIPIENT RECORD.

**Subject:** _Notes that hold up when the payer asks_

Why it was drafted: `no registry change; last contact never >= 90d — quarterly keep-warm; identity unresolved at 0; angle audit`

> unfilled placeholder / template artifact left in the draft

> judge: "You tried it once." - This states a fact about the recipient's past behavior that does not appear in the RECIPIENT RECORD. The record shows tier 'unresolved' with score 0 and no allowed_facts about prior usage.

**Subject:** _Notes that survive a payer audit_

Why it was drafted: `no registry change; last contact never >= 90d — quarterly keep-warm; identity probable at 55; angle audit`

> judge: The draft addresses the recipient as 'K.' using only a first initial, which creates an inappropriately casual tone for a licensed professional and suggests incomplete data rather than respectful formality.

> judge: The opening line 'Case management documentation gets reviewed hard' makes a clinical/reimbursement claim about case management specifically that is not supported in the FACT PACK. The fact pack discusses behavioral health documentation broadly but does not contain specific statements about case management documentation review practices.

The second and third are ordinary quality catches. The first is the
interesting one: the judge rejected *"You tried JotPsych once"* as a claim
about the recipient that the record did not support — and it was right. That
fact is true of every clinician on this list, but I had never put it in the
recipient record, so the drafter was inferring it and the judge caught the
inference.

**The bug was in my prompt, not in the model's writing.** An unsupervised
check refused to send three messages under JotPsych's name because the person
who built it had left something out. That is the behaviour I would want if
nobody were watching, and it is the reason the judge fails closed: if it
cannot return a verdict, the draft is quarantined rather than sent.

The fix was to give both the drafter and the judge the one fact we genuinely
know about everyone on this list — they signed up and did not subscribe —
and to forbid addressing anyone by an initial when that is all we have.

---

## An output that actually left the program

`DRY_RUN=1` writes a real RFC-822 message to `out/outbox/` rather than calling
Resend. Same code path, same content, one environment variable away from live —
and the simulation is declared in the header, not just in the docs.

```
From: JotPsych Machine <onboarding@resend.dev>
To: sarahgoldberg@icloud.com
Subject: Running JotPsych beside what you already use
Date: Tue, 18 Aug 2026 18:41:43 +0000
X-Machine-Simulated: DRY_RUN
Content-Type: text/plain; charset="utf-8"
Content-Transfer-Encoding: quoted-printable
MIME-Version: 1.0

You looked at JotPsych a while back and stayed where you were. That is usuall=
y the right call mid-contract.

Worth knowing: you do not have to move anything. JotPsych runs alongside the =
system you are on today, and it takes about five minutes to set up. Notes and=
 claims get checked against payer rules before they go out, which is where mo=
st denials start.

If it is useful later, it will still be here. If you would rather not hear fr=
om us again, reply with the word stop and I will take you off the list.

=E2=80=94 Josh, JotPsych

```

---

## The hour of human work it produced

`out/human_queue.md`, regenerated every run:

```markdown
# The human hour

_Generated 2026-08-18 18:41 UTC · run 2_

These are the only clinicians this cycle where a person beats a message.
Each one hit the strongest class of signal **and** has a consenting peer
in their specialty and state. Twelve minutes each. Nothing else needs you.

## 1. Jordan Blake
- **Why now:** their practice moved to another state
- **Identity confidence:** probable (57)
- **Peer to offer:** Tessa Nolan, LMHC — Behavior Technician in CA, 4 months on JotPsych
- **Open with:** "Supervision notes and session notes finally live in the same place."
- **Do not say:** that anything was looked up. You are offering an introduction, not reporting on their practice.

---

**Also worth your time this month:**
- Skim `out/quarantine/` — if the machine is blocking the same thing repeatedly, the fix is a line in `config/guardrails.yaml`, not a rewrite.
- Check the angle table on the dashboard. Retire anything with sends and no returns after two cycles.
```

---

## Where the numbers come from

Every line in the dashboard is derived from `out/ledger.jsonl`, an append-only
record of every decision including the silent ones, and `state/state.json`,
which survives runs and is committed back by the workflow. Neither is written by
hand. Delete `state/` and the machine loses its ability to detect anything at
all — which is the point.

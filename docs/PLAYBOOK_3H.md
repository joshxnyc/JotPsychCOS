# The three hours

The brief says spend about a tenth of the time choosing what to build. That's
18 minutes. Not zero — but not 45 either. The scaffold means the plumbing is
already done, so the whole budget goes into the decision layer and the proof.

## 0:00–0:15 — Read and choose (do not open an editor)

- Read the brief twice. Write the one-line answer to *"what does this machine
  turn into what?"* If you can't write that line, you don't have a build yet.
- Sanity-check against the four parts: input it didn't write, a real decision,
  an output that leaves, a trigger that isn't you. If any is missing, change
  the idea now, not at 2:30.
- Check against **Not this**: does it *record* the work or *do* the work? If
  the output is a table, a score, a segment or a flag, it's a CRM. Kill it.

## 0:15–0:25 — Wire the shell

- `cp -r jotpsych-machine/ ./<name> && cd <name>`
- Rename in README, push to the public repo, confirm Actions runs green once.
- **Now the deliverable link exists.** Everything after this is improvement,
  not risk.

## 0:25–1:30 — The decision layer (`machine/strategy.py`)

Three functions, nothing else changes:

- `load_inputs()` — point it at the real files/APIs.
- `decide()` — the actual judgment. Log a one-line `reason` on every plan; the
  dashboard shows it, and that reason is what makes it read as a machine that
  decided rather than a template that filled.
- `draft()` — the prompt. Keep the fact pack in the context window.

Run `./run.sh` after every meaningful change. If it's been 15 minutes since the
loop last ran end to end, stop adding and get it running again.

## 1:30–2:00 — Make QC catch something real

This is the highest-leverage half hour on the whole rubric. Two rows —
*quality control* and *audience judgment* — both hinge on it.

- Feed it three deliberately bad inputs: a prospect with no verified record, an
  advocate with `consent=no`, a fact pack claim you delete so the model
  over-reaches.
- Get real files into `out/quarantine/`. Screenshot the dashboard's
  **What QC caught** table.
- Add each catch to the README. "It caught X" with a file to open beats any
  description of your checks.

## 2:00–2:30 — Live send + the trigger

- `DRY_RUN=0` and send to yourself. Screenshot the received email.
- Push. Let the Action run for real. Hit *Run workflow* once so the Actions tab
  has history. Confirm `state/state.json` and `out/ledger.jsonl` got committed
  back by the bot — that commit *is* the proof of memory.
- Confirm the Pages URL loads signed out.

## 2:30–2:50 — Write the README properly

Fill every bracket. Specifically:
- the one-liner
- exactly which file to replace and which columns are the contract
- exactly how to run it again
- the honest, complete list of simulated parts
- the **What it caught** section with real examples
- a "what I'd do next with real access" paragraph — three concrete items, so
  they can see you know what's missing

## 2:50–3:00 — Freeze and verify

- `git status` — no `.env`, nothing uncommitted.
- Open the repo URL in a private window. Open the Pages URL in a private window.
- Draft the reply email with their line pasted at the top and both links.

## 3:00–3:15 — Send

Reply to the invite email. Their line first. Then:

> **What it is:** one sentence.
> **Run it:** `git clone … && ./run.sh` — works with no keys.
> **Live report:** [pages url]
> **It runs on its own:** [actions url] — scheduled, here's the run history.
> **What QC caught:** [one concrete example]
> **Simulated:** [the honest list]

Short. Links first. They will open the link before they read the paragraph.

---

## The traps, ranked by how many people they get

1. **Building one step beautifully.** A gorgeous drafter with no trigger and no
   send scores as a prototype. Thin whole loop first, always.
2. **Printing instead of sending.** `print()` is not an output. The `.eml` in
   `out/outbox/` is, and the Resend call definitely is.
3. **A list pasted into the source.** Even a great one. It must be read from a
   file or an API.
4. **No memory.** If run #2 doesn't know what run #1 did, "every run starts from
   zero" — that's the *falls short* box, in their words.
5. **The link.** A private repo, an expired share, a Drive folder that asks for
   access. It counts against you whatever the work behind it.

# [MACHINE NAME] — a machine, not a demo

**What it does in one line:** [fill in during the build]

It reads input it did not write, decides something on its own, sends the result
somewhere real, runs on a schedule, checks itself before it sends, and gets
better each cycle.

---

## Run it yourself in 60 seconds

```bash
git clone [REPO URL] && cd [REPO]
./run.sh                    # no keys needed — writes simulated email to out/outbox/
```

That's the whole loop. To see it send real email and use a real model:

```bash
cp .env.example .env        # add OPENROUTER_API_KEY and RESEND_API_KEY
./run.sh --live
```

---

## Replace our data with yours

This is the part that makes it a machine. Two files:

| File | What it is | What to do |
|---|---|---|
| `inbox/prospects.csv` | the people to act on | drop your own CSV here with the same column names |
| `inbox/advocates.csv` | [second input] | same |
| `inbox/suppress.csv` | do-not-contact | anyone here is never touched |

Column names are the only contract. Rows are yours. Delete the `.sample`
files, drop yours in, run `./run.sh` — different input, different output.
Nothing is hardcoded in the source.

The machine also calls the **NPPES federal NPI registry** live
(`https://npiregistry.cms.hhs.gov/api/`) to verify each clinician against the
public record. Free, public, no key. That means it would run on a real
clinician list tomorrow without any new integration.

---

## The four parts

| Part | Where | What it is |
|---|---|---|
| **Input** | `machine/io_input.py` | CSVs in `inbox/` + live NPPES API calls. Nothing pasted into source. |
| **Decision** | `machine/strategy.py` | Picks who to act on, which angle, and why. Every decision is logged with its reason. |
| **Output** | `machine/send.py` | Real email via the Resend API. With `DRY_RUN=1` it writes real `.eml` files to `out/outbox/` instead — labeled simulated, in the header. |
| **Trigger** | `.github/workflows/machine.yml` | GitHub Actions cron, weekdays 09:00 ET. Also fires when a file lands in `inbox/`. Open the **Actions** tab to see it run without anyone pressing anything. |

## Quality control — what it caught

Nothing leaves without passing `machine/qc.py`. Two layers:

1. **Deterministic gates** — banned claims, AI tells, PHI patterns, length,
   unfilled placeholders, unsourced numbers. Configured in
   `config/guardrails.yaml`; change behaviour without touching code.
2. **An LLM judge** — reads the draft against `config/fact_pack.md` and rejects
   anything asserting a fact that isn't in there.

Everything blocked lands in `out/quarantine/` with the exact reason, and the
counts appear on the dashboard under **What QC caught**.

## Learning and measurement

`state/state.json` survives every run. It tracks sends, blocks and replies per
angle, and the machine leans toward the angle with the better historical reply
rate on the next cycle. The GitHub Action commits this file back to the repo,
so the run history is visible in the commit log.

## Human time — about an hour a month

`out/human_queue.md` is regenerated every run. It doesn't say "review the
output." It says which guardrail to edit, which angle to retire, and who to add
to the advocate roster. That's the hour.

## The report

`out/index.html` — published to GitHub Pages at **[PAGES URL]**. Sends, blocks,
catch rate, per-angle reply rate, the last 25 decisions with their reasons, and
the human queue.

---

## Simulated parts, labeled

- Email goes to my own address (`MAIL_TO_OVERRIDE`) rather than to real
  clinicians. Same code path, same API, one env var away from live.
- `inbox/*.sample.csv` are my sample rows. Replace them with yours.
- [anything else — keep this list honest and complete]

## Tests

```bash
python -m pytest -q
```

Seven tests: input is real, NPPES is live, QC blocks banned claims, QC blocks AI
tells, QC passes a clean draft, output leaves the program, memory changes the
weights.

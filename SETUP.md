# Running this yourself

Nothing here depends on my accounts. The repository is public, the registry API
needs no key, and the two keys the machine does use are yours to supply. Three
levels, depending on how far you want to go.

---

## 1. Just see it work — 60 seconds, no accounts at all

```bash
git clone https://github.com/joshxnyc/JotPsychCOS && cd JotPsychCOS
./run.sh
```

The whole loop runs: it reads the sample list, calls the live federal NPI
registry, resolves identities, decides, drafts, runs quality control, and writes
real `.eml` files to `out/outbox/`. With no `OPENROUTER_API_KEY` the drafter
falls back to a clearly labeled stub so the loop still completes end to end.

```bash
python -m machine.preflight     # what is and is not configured
python tools/red_team.py        # push deliberately bad drafts through QC
python -m pytest -q             # 16 tests
```

## 2. Run it as your own — 15 minutes

**Fork the repository.** Everything below happens in *your* fork, and the
dashboard URL becomes `https://<you>.github.io/<repo>/`. The report reads
`GITHUB_REPOSITORY` at build time, so every link on it points at your fork, not
mine.

| Step | Where |
|---|---|
| **Keys** | [openrouter.ai](https://openrouter.ai/keys) for the model, [resend.com](https://resend.com/api-keys) for email. Both have free tiers. |
| **Repo secrets** | Settings → Secrets and variables → Actions → Secrets: `OPENROUTER_API_KEY`, `RESEND_API_KEY`, `MAIL_TO_OVERRIDE` |
| **Repo variables** | Same page → Variables: `MAIL_FROM`, `DRY_RUN=1`, `MAX_SENDS_PER_RUN=3` |
| **Pages** | Settings → Pages → Source: **GitHub Actions** |
| **Permissions** | Settings → Actions → General → Workflow permissions → **Read and write**. Without this the machine cannot commit its own memory back, and every run starts blind. |
| **Check it** | Actions → **Preflight** → Run workflow. It makes a real model call and sends one real email, then tells you exactly what is wrong if anything is. |

`MAIL_TO_OVERRIDE` is the safety catch, not a limitation: **every** message the
machine sends is redirected to that address no matter who it was written for. It
is how you read real output without any risk of a clinician receiving it. Set it
to your own address and leave it set until you genuinely intend to go live.

Locally, copy `.env.example` to `.env` and fill in the same values. `.env` is
gitignored.

## 3. Point it at your real list

**A file.** Drop `inbox/dormant.csv` next to the sample. Three columns:
`name,email,mobile`. If that file exists it wins; the sample is only a fallback.

**Google Sheets.** File → Share → **Publish to web** → choose the sheet → CSV.
Copy the URL and set it as `DORMANT_URL` (a repo secret, or a line in `.env`).
The machine reads it every run, so the sheet *is* the list — add a row and the
next run picks it up.

**Airtable.** Share a grid view → copy the CSV download link → same variable.

**A CRM or warehouse.** Anything that returns CSV over HTTPS works: a HubSpot or
Salesforce report export URL, a signed S3 link, a small endpoint in front of your
database. Same variable, same three columns.

```bash
DORMANT_URL="https://docs.google.com/.../pub?gid=0&single=true&output=csv" ./run.sh
```

The same pattern covers the other three inputs: `SUPPRESS_URL`, `PEERS_URL`,
`RETURNS_URL`. A URL that is set but unreadable **fails the run** rather than
silently falling back to sample data and looking like a successful pass against
your real list.

**Try it at scale first.** `python tools/make_list.py 15000 > inbox/dormant.csv`
generates a list the size of the real one, with the same messiness — mixed email
domains, names written five ways, missing mobiles, duplicates.

## 4. What the machine actually sends

Two different questions, deliberately separated.

**To you, every cycle.** `SEND_DIGEST=1` (the default) emails whoever operates
the machine a report of each run: what changed, what it decided, what quality
control stopped, and every message waiting for a person — each one already
written, subject and body, ready to edit and send from your own mailbox. Set
`DIGEST_TO` to the address that should receive it.

**To clinicians: off by default.** `SEND_TO_CLINICIANS=0` means approved drafts
are staged as real `.eml` files in `out/outbox/` and go nowhere. The machine
decides who is worth writing to and writes it well; whether those messages reach
anyone is a decision a company makes once, deliberately.

### Turning clinician sending on

Four steps, in this order. Nothing happens by accident.

1. Read `out/outbox/` and `out/quarantine/` first. If you are not comfortable
   with what is in there, the fix is `config/brand.md` or
   `config/guardrails.yaml` — plain text, no code change, no redeploy.
2. **Verify a sending domain** at resend.com/domains, set `MAIL_FROM` to a real
   mailbox on it that a clinician can reply to. Until you do, Resend only
   delivers to the address the account was created with.
3. **Clear `MAIL_TO_OVERRIDE`**, which until now has been redirecting every
   message to you.
4. Set `SEND_TO_CLINICIANS=1` and `DRY_RUN=0`, and raise `MAX_SENDS_PER_RUN`
   slowly. Start at 3.

Read `out/outbox/` and `out/quarantine/` before step 3. If you are not
comfortable with what is in there, the fix is `config/brand.md` or
`config/guardrails.yaml` — both are plain text, and neither needs a code change
or a redeploy.

## What each setting does

| Name | Default | What it controls |
|---|---|---|
| `SEND_TO_CLINICIANS` | `0` | Off means approved drafts are staged and nobody receives them. |
| `SEND_DIGEST` | `1` | Email a run report to the operator each cycle. |
| `DIGEST_TO` | `MAIL_TO_OVERRIDE` | Who receives that report. |
| `DRY_RUN` | `1` | `1` writes `.eml` files instead of calling Resend. Unset means `1` — it fails safe. |
| `MAIL_TO_OVERRIDE` | — | Redirects every send here. The safety catch. |
| `MAX_SENDS_PER_RUN` | `5` | Hard cap per run. A runaway loop cannot happen. |
| `RESOLVE_BUDGET_PER_RUN` | `400` | Registry lookups per run. Cost stays flat as the list grows. |
| `RESOLVE_TTL_DAYS` | `14` | How often each clinician's profile is refreshed. |
| `DORMANT_URL` | — | Read the list from Sheets / Airtable / a CRM instead of a file. |
| `OPENROUTER_MODEL` | `anthropic/claude-sonnet-4.5` | Any model OpenRouter serves. |

# Before you press Start

Everything below is explicitly allowed — the brief says to have "the tools you
build with, open and working: your code environment, your automation platform,
your accounts." None of it is the machine. All of it is the workbench.

## Accounts and keys — 15 minutes, do this first

| # | Thing | Where | Why it matters | Done |
|---|---|---|---|---|
| 1 | **OpenRouter API key** | openrouter.ai → Keys. Load $5. | The machine's own brain. It must call a model without you in the loop. | ☐ |
| 2 | **Resend API key** | resend.com → sign up → API Keys | The output that leaves the program. Free tier, 3,000/mo, HTTPS so it works from GitHub Actions. | ☐ |
| 3 | **Confirm your Resend sending address** | Resend dashboard | With no verified domain you can only send **from** `onboarding@resend.dev` and **to** the address you signed up with. Send yourself one test email now. | ☐ |
| 4 | **GitHub account signed in** | github.com | The one-click deliverable. | ☐ |
| 5 | **`gh` CLI authed** | `gh auth login` | Lets you create the public repo in one command instead of clicking through the UI at minute 165. | ☐ |
| 6 | **A blank public repo, pre-created** | `gh repo create jotpsych-machine --public --clone` | Save five minutes and one class of panic. Push the scaffold to it now. | ☐ |
| 7 | **GitHub Pages enabled** | repo → Settings → Pages → Source: GitHub Actions | So the dashboard has a live URL. Enabling it cold costs 4 minutes. | ☐ |
| 8 | **Repo secrets set** | repo → Settings → Secrets and variables → Actions | `OPENROUTER_API_KEY`, `RESEND_API_KEY`, `MAIL_TO_OVERRIDE`. Variables: `DRY_RUN=0`, `MAIL_FROM`, `MAX_SENDS_PER_RUN=3`. | ☐ |
| 9 | **Python 3.11+ working locally** | `python3 --version` | ☐ |
| 10 | **Claude / your AI tools signed in** | | ☐ |

## Test the link like they will

Open your repo URL in a **private window, signed out**. If it 404s or asks for
anything, fix it now. Access problems count against you regardless of quality.

## The two-minute smoke test (run it before the clock)

```bash
cd jotpsych-machine
./run.sh                       # should print [input] / [decide] / [send] / [done]
python -m pytest -q            # should print 7 passed
```

Then with your real keys in `.env`:

```bash
DRY_RUN=0 ./run.sh --live --limit 1
```

Check your inbox. If an email arrives, every hard part is already solved and
the three hours are yours to spend on judgment instead of plumbing.

## What is deliberately NOT pre-built

- `machine/strategy.py` — the actual decision. That's the case study.
- `config/fact_pack.md` is filled in, but the *angle*, the matching logic and
  the copy are yours to write on the clock.
- The README's blanks: name, one-liner, URLs, and the simulated-parts list.

## Small things that cost people the grade

- **Sending limit.** Keep `MAX_SENDS_PER_RUN` at 3–5. A runaway loop emailing
  200 addresses from your account is the worst possible ending.
- **Never commit `.env`.** It's gitignored; check `git status` before the first push.
- **Commit early, commit often.** The Actions tab having 6 green runs is
  evidence the trigger is real. One run looks staged.
- **Put a real timestamp on the first scheduled run.** If the cron hasn't fired
  by the time you send, hit *Run workflow* manually once so there's history,
  and say so in the README.
- **The reply email.** They give you one line to paste at the top. Paste it
  first, before anything else, then write the body.

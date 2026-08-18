# Deploying to Fly

One machine, one volume. SQLite is the store and the machine's registry snapshot
sits beside it, both on the volume, so a deploy never costs the machine its
memory.

## What I need from you

Six things. Everything else has a working default.

| # | What | Where to get it | Notes |
|---|---|---|---|
| 1 | **A Fly account and `flyctl`** | `fly auth signup`, then `fly auth login` | The free allowance covers this: one shared-cpu-1x, 512MB, 1GB volume. |
| 2 | **An app name** | you choose | `second-window` is in `fly.toml`; change it if it is taken. |
| 3 | `APP_PASSWORD` | you choose | The sign-in password for the console. One shared password for now — see *Next* below. |
| 4 | `APP_SECRET` | `openssl rand -hex 32` | Signs session cookies **and** unsubscribe tokens. Change it and every outstanding unsubscribe link stops working, so set it once. |
| 5 | `OPENROUTER_API_KEY` | openrouter.ai | Writes the drafts. |
| 6 | `RESEND_API_KEY` + a **verified sending domain** | resend.com | Without a verified domain Resend only delivers to your own account address. |

Also useful, both optional:

- `POSTAL_ADDRESS` — JotPsych's real mailing address. It goes in every message
  and CAN-SPAM requires it to be genuine. It currently defaults to a placeholder,
  which is fine while nothing is being sent and **must be corrected before it is**.
- `DIGEST_TO` — who receives the run report each cycle.

## Deploy

```bash
fly launch --no-deploy                       # reads fly.toml, creates the app
fly volumes create second_window_data --size 1 --region ewr

fly secrets set \
  APP_PASSWORD="…" \
  APP_SECRET="$(openssl rand -hex 32)" \
  OPENROUTER_API_KEY="…" \
  RESEND_API_KEY="…" \
  MAIL_FROM="Josh at JotPsych <josh@jotpsych.com>" \
  DIGEST_TO="you@jotpsych.com" \
  POSTAL_ADDRESS="JotPsych, <real address>" \
  APP_URL="https://second-window.fly.dev"

fly deploy
fly open
```

`APP_URL` is what the unsubscribe links point at. Set it to the real hostname
before anything is sent, or those links will not resolve.

## After the first deploy

1. Sign in and go to **Settings → Add clinicians**. Upload a CSV with
   `name, email, mobile`. `python tools/make_list.py 15000 > list.csv` produces a
   realistic one if you want to see it at scale first.
2. **New practices → Check the register.** No list needed; it reads the federal
   register directly.
3. **Overview → Run now.** It resolves identities, diffs the registry, decides,
   drafts and checks. Then **Review & send**.
4. Approving records the decision. **Nothing is delivered** while
   `SEND_TO_CLINICIANS = "0"`, which is how it ships.

## Turning sending on

In this order:

```bash
fly secrets set MAIL_TO_OVERRIDE="you@jotpsych.com"   # everything comes to you first
fly deploy
# read a few real deliveries, then:
fly secrets unset MAIL_TO_OVERRIDE
fly secrets set SEND_TO_CLINICIANS=1
```

Point Resend's webhook at `https://<app>.fly.dev/webhooks/resend` before you do.
Bounces and complaints then suppress automatically, which is the control that
protects the sending domain — a complaint rate above 0.1% is an existential
problem, and a human maintaining a list is not a control.

## Operating it

| | |
|---|---|
| Logs | `fly logs` |
| Shell | `fly ssh console` |
| Back up the database | `fly ssh console -C "cat /data/app.db" > backup.db` |
| Change the schedule | `RUN_INTERVAL_HOURS` in `fly.toml`, then `fly deploy` |
| Health | `https://<app>.fly.dev/healthz` returns live counts |

## What this deliberately does not have yet

- **SSO.** One shared password. Workspace SSO replaces exactly one function
  (`who()` in `app/main.py`) and adds real per-person attribution — right now
  the audit trail says "operator", which is honest but not useful with a team.
- **Postgres.** SQLite is right for one writer and well under a million rows.
  The moment there are two machines writing, it is not, and the schema moves
  across unchanged.
- **A second region.** The scheduler runs in-process, so `min_machines_running`
  is 1 and scaling out would run the machine twice.

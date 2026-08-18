"""Second Window — the operator console and the write path.

The scheduled run decides and drafts. This is where a person reviews, edits,
approves or rejects, and where every one of those decisions is recorded.

Runs as a single Fly machine with a volume holding the SQLite database and the
machine's own state directory.
"""
import csv, io, json, os, pathlib, sys, threading

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, Request, Form, File, UploadFile
from fastapi.responses import (HTMLResponse, RedirectResponse, PlainTextResponse,
                               JSONResponse, FileResponse)
from itsdangerous import URLSafeSerializer, BadSignature

from machine import compliance, config, db, prospect, send
from app import ui

APP_SECRET = os.getenv("APP_SECRET") or "dev-secret-not-for-production"
APP_PASSWORD = os.getenv("APP_PASSWORD") or ""
COOKIE = "sw_session"
signer = URLSafeSerializer(APP_SECRET, salt="sw-session")
ASSETS = pathlib.Path(__file__).resolve().parent.parent / "assets"

api = FastAPI(title="Second Window", docs_url=None, redoc_url=None)
_run_lock = threading.Lock()


# ------------------------------------------------------------------- auth ---
def who(request: Request) -> str:
    """Returns the signed-in identity, or '' — deliberately one shared password
    for now. Workspace SSO is the next step and changes only this function."""
    if not APP_PASSWORD:
        return "operator"           # no password configured: local development
    raw = request.cookies.get(COOKIE, "")
    try:
        return signer.loads(raw).get("u", "")
    except (BadSignature, AttributeError, TypeError):
        return ""


def wall(request: Request):
    return None if who(request) else RedirectResponse("/login", status_code=303)


def badges() -> str:
    live = config.SEND_TO_CLINICIANS
    cls = "live" if live else ""
    txt = "Sending to clinicians" if live else "Approval required before anything sends"
    return f'<span class="badge {cls}">{txt}</span>'


def back(path: str, kind: str = "ok", msg: str = "") -> RedirectResponse:
    sep = "&" if "?" in path else "?"
    return RedirectResponse(f"{path}{sep}f={kind}&m={msg}", status_code=303)


def flash(request: Request) -> tuple:
    k, m = request.query_params.get("f"), request.query_params.get("m")
    return (k, m) if k and m else ()


# ------------------------------------------------------------------ pages ---
@api.get("/login", response_class=HTMLResponse)
def login_form():
    return ui.login_page()


@api.post("/login")
def login(password: str = Form("")):
    if not APP_PASSWORD or password != APP_PASSWORD:
        return HTMLResponse(ui.login_page("That password is not right."), status_code=401)
    r = RedirectResponse("/", status_code=303)
    r.set_cookie(COOKIE, signer.dumps({"u": "operator"}), httponly=True,
                 samesite="lax", secure=bool(os.getenv("FLY_APP_NAME")), max_age=86400 * 7)
    return r


@api.post("/logout")
def logout():
    r = RedirectResponse("/login", status_code=303)
    r.delete_cookie(COOKIE)
    return r


@api.get("/static/{name}")
def static(name: str):
    p = ASSETS / name
    if not p.exists() or p.suffix not in (".svg", ".png"):
        return PlainTextResponse("not found", status_code=404)
    return FileResponse(p)


@api.get("/healthz")
def healthz():
    c = db.connect()
    try:
        return {"ok": True, **db.counts(c)}
    finally:
        c.close()


@api.get("/", response_class=HTMLResponse)
def overview(request: Request):
    if (r := wall(request)):
        return r
    c = db.connect()
    try:
        body = ui.overview_page(db.counts(c), db.runs(c), db.drafts(c, "staged"),
                                db.clinicians(c, "prospect", 5), [])
    finally:
        c.close()
    return ui.page("Overview", body, active="/", badges=badges(), flash=flash(request))


@api.get("/review", response_class=HTMLResponse)
def review(request: Request):
    if (r := wall(request)):
        return r
    c = db.connect()
    try:
        body = ui.review_page(db.drafts(c, "staged"))
    finally:
        c.close()
    return ui.page("Review", body, active="/review", badges=badges(), flash=flash(request))


@api.get("/clinicians", response_class=HTMLResponse)
def clinicians(request: Request, q: str = ""):
    if (r := wall(request)):
        return r
    c = db.connect()
    try:
        rows = [x for x in db.clinicians(c, "list", 3000)
                if not q or q.lower() in " ".join(
                    str(x[k] or "") for k in ("name", "email", "specialty", "city", "state")).lower()]
        body = ui.clinicians_page(rows[:400], q)
    finally:
        c.close()
    return ui.page("Clinicians", body, active="/clinicians", badges=badges(),
                   flash=flash(request))


@api.get("/prospects", response_class=HTMLResponse)
def prospects(request: Request):
    if (r := wall(request)):
        return r
    c = db.connect()
    try:
        rows = db.clinicians(c, "prospect", 60)
        briefs = {r["id"]: prospect.brief(r) for r in rows}
        body = ui.prospects_page(rows, briefs,
                                 {"window_days": prospect._days(), "states": prospect._states()})
    finally:
        c.close()
    return ui.page("New practices", body, active="/prospects", badges=badges(),
                   flash=flash(request))


@api.get("/activity", response_class=HTMLResponse)
def activity(request: Request):
    if (r := wall(request)):
        return r
    c = db.connect()
    try:
        body = ui.activity_page(db.events(c, 300))
    finally:
        c.close()
    return ui.page("Activity", body, active="/activity", badges=badges(),
                   flash=flash(request))


@api.get("/settings", response_class=HTMLResponse)
def settings(request: Request):
    if (r := wall(request)):
        return r
    cfg = {
        "SEND_TO_CLINICIANS": ("on" if config.SEND_TO_CLINICIANS else "off",
                               "When off, approving a draft records the decision but sends nothing."),
        "MAIL_FROM": (config.MAIL_FROM, "The address clinicians see and can reply to."),
        "MAIL_TO_OVERRIDE": (config.MAIL_TO_OVERRIDE or "(not set)",
                             "Redirects every message here. The safety catch."),
        "MAX_SENDS_PER_RUN": (str(config.MAX_SENDS_PER_RUN), "Hard cap per run."),
        "POSTAL_ADDRESS": (compliance.POSTAL_ADDRESS, "Required in every message by CAN-SPAM."),
        "APP_URL": (compliance.APP_URL or "(not set)",
                    "Used to build the one-click unsubscribe link."),
        "OPENROUTER_MODEL": (config.OPENROUTER_MODEL, "The model that writes drafts."),
        "PROSPECT_STATES": (", ".join(prospect._states()), "Where to look for new practices."),
    }
    c = db.connect()
    try:
        body = ui.settings_page(db.suppressions(c), cfg)
    finally:
        c.close()
    return ui.page("Settings", body, active="/settings", badges=badges(),
                   flash=flash(request))


# ---------------------------------------------------------------- actions ---
@api.post("/decide")
def decide(request: Request, draft_id: int = Form(...), action: str = Form(...),
           subject: str = Form(""), body: str = Form("")):
    if (r := wall(request)):
        return r
    actor = who(request)
    c = db.connect()
    try:
        d = db.draft(c, draft_id)
        if not d:
            return back("/review", "err", "That draft no longer exists.")
        row = c.execute("SELECT * FROM clinicians WHERE id=?", (d["clinician_id"],)).fetchone()
        email = row["email"] or ""

        if action in ("reject", "suppress"):
            db.set_status(c, draft_id, "rejected", actor=actor)
            db.log(c, "draft_rejected", actor=actor, clinician_id=d["clinician_id"],
                   draft_id=draft_id, detail=f"rejected by {actor}")
            if action == "suppress" and email:
                db.suppress(c, email, "rejected in review", source="manual")
                return back("/review", "ok", f"Rejected, and {email} will not be contacted again.")
            return back("/review", "ok", "Rejected. The clinician is left alone.")

        # Approve. The edited text is what goes out, with the footer re-applied so
        # an edit can never remove the unsubscribe link or the postal address.
        edited = (subject.strip() != (d["subject"] or "").strip()
                  or body.strip() != ui._strip_footer(d["body"]).strip())
        outgoing = compliance.apply({"to": email, "subject": subject.strip(),
                                     "body": body.strip()})
        c.execute("UPDATE drafts SET subject=?, body=?, edited=? WHERE id=?",
                  (outgoing["subject"], outgoing["body"], int(edited), draft_id))

        if db.is_suppressed(c, email):
            db.set_status(c, draft_id, "rejected", actor=actor)
            db.log(c, "send_refused", actor="machine", draft_id=draft_id,
                   detail=f"{email} is on the do-not-contact list")
            return back("/review", "err", f"{email} is on the do-not-contact list. Not sent.")

        if not config.SEND_TO_CLINICIANS:
            db.set_status(c, draft_id, "approved", actor=actor)
            db.log(c, "draft_approved", actor=actor, clinician_id=d["clinician_id"],
                   draft_id=draft_id,
                   detail=f"approved{' with edits' if edited else ''}; sending is off")
            return back("/review", "ok",
                        "Approved and recorded. Sending to clinicians is off, so nothing left.")

        res = send.send_email(email, outgoing["subject"], outgoing["body"])
        if res.ok:
            db.set_status(c, draft_id, "sent", actor=actor,
                          provider_id=str(res.get("id") or res.get("path") or ""))
            db.log(c, "draft_sent", actor=actor, clinician_id=d["clinician_id"],
                   draft_id=draft_id,
                   detail=f"sent to {res.get('to')}{' with edits' if edited else ''}")
            return back("/review", "ok", f"Sent to {res.get('to')}.")
        db.log(c, "send_failed", actor=actor, draft_id=draft_id, detail=str(res.get("error"))[:200])
        return back("/review", "err", f"Could not send: {res.get('error')}")
    finally:
        c.close()


@api.post("/suppress")
def do_suppress(request: Request, email: str = Form(...)):
    if (r := wall(request)):
        return r
    c = db.connect()
    try:
        db.suppress(c, email, "added by an operator", source="manual")
    finally:
        c.close()
    return back(request.headers.get("referer", "/settings").split("?")[0], "ok",
                f"{email} will not be contacted.")


@api.post("/upload")
async def upload(request: Request, file: UploadFile = File(...)):
    if (r := wall(request)):
        return r
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    rows = list(csv.DictReader(io.StringIO(raw)))
    if not rows or not {"name", "email"} <= {k.strip().lower() for k in rows[0]}:
        return back("/settings", "err", "That CSV needs at least name and email columns.")
    c = db.connect()
    added = skipped = 0
    try:
        for r_ in rows:
            r_ = {k.strip().lower(): (v or "").strip() for k, v in r_.items() if k}
            if not r_.get("email"):
                continue
            if db.is_suppressed(c, r_["email"]):
                skipped += 1
                continue
            db.upsert_clinician(c, name=r_.get("name", ""), email=r_["email"],
                                mobile=r_.get("mobile", ""), source="list")
            added += 1
        db.log(c, "list_uploaded", actor=who(request),
               detail=f"{added} added or updated, {skipped} on the do-not-contact list")
    finally:
        c.close()
    return back("/settings", "ok",
                f"{added} clinician(s) added or updated. {skipped} skipped as do-not-contact.")


@api.post("/prospects/sync")
def sync_prospects(request: Request):
    if (r := wall(request)):
        return r
    c = db.connect()
    try:
        res = prospect.sync(c, actor=who(request))
    finally:
        c.close()
    return back("/prospects", "ok",
                f"{res['new']} new practice(s) found, {res['already_known']} already known.")


@api.post("/run")
def trigger_run(request: Request):
    if (r := wall(request)):
        return r
    if not _run_lock.acquire(blocking=False):
        return back("/", "err", "A run is already going.")

    def go():
        try:
            os.environ["RUN_TRIGGER"] = "manual"
            from machine import run as machine_run
            machine_run.main(["--limit", str(config.MAX_SENDS_PER_RUN)])
        finally:
            _run_lock.release()

    threading.Thread(target=go, daemon=True).start()
    return back("/", "ok", "Run started. Refresh in a few seconds.")


# ------------------------------------------------------- public endpoints ---
@api.get("/unsubscribe", response_class=HTMLResponse)
def unsubscribe(t: str = ""):
    """One click, no login, no confirmation step — that is what the law and the
    mail providers both require."""
    email = compliance.verify(t)
    if email:
        c = db.connect()
        try:
            db.suppress(c, email, "unsubscribed via link", source="unsubscribe")
        finally:
            c.close()
    return ui.unsubscribe_page(email, bool(email))


@api.post("/unsubscribe")
def unsubscribe_post(t: str = ""):
    """Gmail and Yahoo POST to List-Unsubscribe rather than following the link."""
    email = compliance.verify(t)
    if email:
        c = db.connect()
        try:
            db.suppress(c, email, "one-click unsubscribe", source="unsubscribe")
        finally:
            c.close()
    return PlainTextResponse("ok")


@api.post("/webhooks/resend")
async def resend_webhook(request: Request):
    """Bounces and complaints suppress automatically. A complaint rate above
    0.1% is an existential problem for a sending domain, and a human maintaining
    a CSV is not a control."""
    payload = await request.json()
    kind = (payload.get("type") or "").lower()
    to = (payload.get("data", {}).get("to") or [""])
    email = to[0] if isinstance(to, list) else str(to)
    if not email:
        return JSONResponse({"ok": True, "ignored": "no recipient"})
    mapping = {"email.bounced": ("hard bounce", "bounce"),
               "email.complained": ("marked as spam", "complaint")}
    if kind not in mapping:
        return JSONResponse({"ok": True, "ignored": kind})
    reason, source = mapping[kind]
    c = db.connect()
    try:
        db.suppress(c, email, reason, source=source)
    finally:
        c.close()
    return JSONResponse({"ok": True, "suppressed": email, "reason": reason})


# -------------------------------------------------------------- scheduler ---
def _scheduler():
    """Runs the machine on an interval inside the same process.

    A separate cron machine would be tidier, but this keeps the deployment to
    one machine and one volume, and the run is short and single-threaded. If a
    run is already going the tick is skipped rather than queued — a missed cycle
    costs nothing, two concurrent writers cost the database.
    """
    import time
    hours = float(os.getenv("RUN_INTERVAL_HOURS") or 0)
    if hours <= 0:
        return
    time.sleep(45)                      # let the machine finish booting
    while True:
        if _run_lock.acquire(blocking=False):
            try:
                os.environ["RUN_TRIGGER"] = "schedule"
                from machine import run as machine_run
                machine_run.main(["--limit", str(config.MAX_SENDS_PER_RUN)])
            except Exception as exc:                      # never kill the thread
                c = db.connect()
                try:
                    db.log(c, "run_failed", detail=str(exc)[:400])
                finally:
                    c.close()
            finally:
                _run_lock.release()
        time.sleep(hours * 3600)


@api.on_event("startup")
def _boot():
    db.connect().close()                # create the schema on first boot
    threading.Thread(target=_scheduler, daemon=True).start()

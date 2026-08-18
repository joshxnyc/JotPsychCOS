"""THE STORE. SQLite, on a persistent volume.

Deliberate choice, not a shortcut. This is a single-writer workload with well
under a million rows and one operator team. SQLite on a Fly volume gives
durability, transactions and zero operational surface. Postgres becomes the
right answer when a second writer appears — concurrent runs, or a second region —
and the schema below moves across unchanged.

Everything a person can act on lives here. The registry snapshot stays on disk
because it is a blob the machine reads whole, not something anyone queries.
"""
import json, os, pathlib, sqlite3, datetime, hashlib

DB_PATH = pathlib.Path(os.getenv("DB_PATH") or
                       (pathlib.Path(__file__).resolve().parent.parent / "data" / "app.db"))

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS clinicians (
  id            TEXT PRIMARY KEY,          -- stable hash of the email
  name          TEXT NOT NULL,
  email         TEXT UNIQUE,            -- NULL for registry prospects: NPPES has no email
  mobile        TEXT DEFAULT '',
  source        TEXT DEFAULT 'list',       -- list | prospect
  npi           TEXT DEFAULT '',
  tier          TEXT DEFAULT 'unresolved',
  score         INTEGER DEFAULT 0,
  candidates    INTEGER DEFAULT 0,
  specialty     TEXT DEFAULT '',
  city          TEXT DEFAULT '',
  state         TEXT DEFAULT '',
  phone         TEXT DEFAULT '',
  enumerated_on TEXT DEFAULT '',
  signals       TEXT DEFAULT '[]',
  resolved_at   TEXT DEFAULT '',
  created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_clin_source ON clinicians(source);
CREATE INDEX IF NOT EXISTS idx_clin_tier   ON clinicians(tier);

CREATE TABLE IF NOT EXISTS runs (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  ended_at   TEXT DEFAULT '',
  trigger    TEXT DEFAULT 'schedule',      -- schedule | manual | api
  summary    TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS drafts (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id       INTEGER,
  clinician_id TEXT NOT NULL,
  kind         TEXT NOT NULL,              -- moment | keep_warm | human_call
  channel      TEXT DEFAULT 'email',
  angle        TEXT DEFAULT '',
  subject      TEXT DEFAULT '',
  body         TEXT DEFAULT '',
  reason       TEXT DEFAULT '',
  status       TEXT NOT NULL,              -- staged | approved | sent | rejected | blocked
  qc           TEXT DEFAULT '{}',
  peer         TEXT DEFAULT '',
  edited       INTEGER DEFAULT 0,
  created_at   TEXT NOT NULL,
  decided_at   TEXT DEFAULT '',
  decided_by   TEXT DEFAULT '',
  provider_id  TEXT DEFAULT '',
  FOREIGN KEY (clinician_id) REFERENCES clinicians(id)
);
CREATE INDEX IF NOT EXISTS idx_draft_status ON drafts(status);
CREATE INDEX IF NOT EXISTS idx_draft_run    ON drafts(run_id);

CREATE TABLE IF NOT EXISTS suppressions (
  email      TEXT PRIMARY KEY,
  reason     TEXT NOT NULL,
  source     TEXT DEFAULT 'manual',        -- manual | unsubscribe | bounce | complaint
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  ts           TEXT NOT NULL,
  actor        TEXT DEFAULT 'machine',
  action       TEXT NOT NULL,
  clinician_id TEXT DEFAULT '',
  draft_id     INTEGER,
  detail       TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
"""


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def cid(email: str = "", npi: str = "") -> str:
    """Identity key. An email if we have one, otherwise the NPI — a registry
    prospect has no email anywhere, because the federal register does not
    publish one."""
    seed = (email or "").strip().lower() or f"npi:{npi}"
    return hashlib.sha1(seed.encode()).hexdigest()[:12]


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=20, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


def log(c, action: str, *, actor: str = "machine", clinician_id: str = "",
        draft_id: int | None = None, detail: str = "") -> None:
    """Every state change a person could ask about later. This is the audit
    trail, and it is the reason anyone would let this send under their name."""
    c.execute("INSERT INTO events (ts, actor, action, clinician_id, draft_id, detail)"
              " VALUES (?,?,?,?,?,?)", (now(), actor, action, clinician_id, draft_id, detail))


# ------------------------------------------------------------- clinicians ---
def upsert_clinician(c, *, name: str, email: str = "", mobile: str = "",
                     source: str = "list", npi: str = "", **fields) -> str:
    i = cid(email, npi)
    c.execute("""INSERT INTO clinicians (id,name,email,mobile,source,npi,created_at)
                 VALUES (?,?,?,?,?,?,?)
                 ON CONFLICT(id) DO UPDATE SET name=excluded.name,
                   mobile=CASE WHEN excluded.mobile<>'' THEN excluded.mobile
                               ELSE clinicians.mobile END""",
              (i, name, (email.strip().lower() or None), mobile, source, npi, now()))
    if fields:
        cols = ", ".join(f"{k}=?" for k in fields)
        c.execute(f"UPDATE clinicians SET {cols} WHERE id=?",
                  (*[json.dumps(v) if isinstance(v, (list, dict)) else v
                     for v in fields.values()], i))
    return i


def clinicians(c, source: str = "", limit: int = 5000) -> list[sqlite3.Row]:
    q = "SELECT * FROM clinicians"
    a = []
    if source:
        q += " WHERE source=?"; a.append(source)
    q += " ORDER BY score DESC LIMIT ?"; a.append(limit)
    return c.execute(q, a).fetchall()


# ----------------------------------------------------------------- drafts ---
def add_draft(c, **kw) -> int:
    kw.setdefault("created_at", now())
    cols = ",".join(kw)
    marks = ",".join("?" * len(kw))
    cur = c.execute(f"INSERT INTO drafts ({cols}) VALUES ({marks})", tuple(kw.values()))
    return cur.lastrowid


def draft(c, draft_id: int):
    return c.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()


def drafts(c, status: str = "", limit: int = 500) -> list[sqlite3.Row]:
    q = ("SELECT d.*, c.name, c.email, c.tier, c.score, c.specialty, c.city, c.state "
         "FROM drafts d JOIN clinicians c ON c.id = d.clinician_id")
    a = []
    if status:
        q += " WHERE d.status=?"; a.append(status)
    q += " ORDER BY d.id DESC LIMIT ?"; a.append(limit)
    return c.execute(q, a).fetchall()


def set_status(c, draft_id: int, status: str, *, actor: str = "machine",
               provider_id: str = "") -> None:
    c.execute("UPDATE drafts SET status=?, decided_at=?, decided_by=?, provider_id=?"
              " WHERE id=?", (status, now(), actor, provider_id, draft_id))


# ------------------------------------------------------------ suppression ---
def suppress(c, email: str, reason: str, source: str = "manual") -> None:
    """One place, enforced at send time as well as at decision time. A bounce or
    a complaint lands here automatically; so does one-click unsubscribe."""
    c.execute("INSERT INTO suppressions (email, reason, source, created_at)"
              " VALUES (?,?,?,?) ON CONFLICT(email) DO UPDATE SET reason=excluded.reason,"
              " source=excluded.source", (email.strip().lower(), reason, source, now()))
    log(c, "suppressed", actor=source, detail=f"{email}: {reason}")


def is_suppressed(c, email: str) -> bool:
    return c.execute("SELECT 1 FROM suppressions WHERE email=?",
                     (email.strip().lower(),)).fetchone() is not None


def suppressions(c) -> list[sqlite3.Row]:
    return c.execute("SELECT * FROM suppressions ORDER BY created_at DESC").fetchall()


# ------------------------------------------------------------------- runs ---
def start_run(c, trigger: str = "schedule") -> int:
    cur = c.execute("INSERT INTO runs (started_at, trigger) VALUES (?,?)", (now(), trigger))
    return cur.lastrowid


def end_run(c, run_id: int, summary: dict) -> None:
    c.execute("UPDATE runs SET ended_at=?, summary=? WHERE id=?",
              (now(), json.dumps(summary), run_id))


def runs(c, limit: int = 50) -> list[sqlite3.Row]:
    return c.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def events(c, limit: int = 200) -> list[sqlite3.Row]:
    return c.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def counts(c) -> dict:
    g = lambda q, *a: c.execute(q, a).fetchone()[0]
    return {
        "clinicians": g("SELECT COUNT(*) FROM clinicians WHERE source='list'"),
        "prospects":  g("SELECT COUNT(*) FROM clinicians WHERE source='prospect'"),
        "awaiting":   g("SELECT COUNT(*) FROM drafts WHERE status='staged'"),
        "sent":       g("SELECT COUNT(*) FROM drafts WHERE status='sent'"),
        "rejected":   g("SELECT COUNT(*) FROM drafts WHERE status='rejected'"),
        "blocked":    g("SELECT COUNT(*) FROM drafts WHERE status='blocked'"),
        "suppressed": g("SELECT COUNT(*) FROM suppressions"),
        "runs":       g("SELECT COUNT(*) FROM runs"),
    }

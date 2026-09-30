"""SQLite storage. One connection, one lock: the app runs a single uvicorn worker plus one classifier thread."""

from __future__ import annotations

import json
import sqlite3
import threading

from common import DATA, DB_PATH, now_iso

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lat REAL NOT NULL, lon REAL NOT NULL,
  street TEXT, ward TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'triaging',
  report_count INTEGER NOT NULL DEFAULT 1,
  photo_url TEXT, photo_path TEXT, photo_sha TEXT,
  cleared_photo_url TEXT, cleared_at TEXT,
  public_summary TEXT, description TEXT,
  triage TEXT, model_raw TEXT, seed_key TEXT
);
CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  incident_id INTEGER NOT NULL, created_at TEXT NOT NULL,
  lat REAL, lon REAL, loc_source TEXT, description TEXT, reporter TEXT,
  photo_url TEXT, photo_sha TEXT
);
CREATE TABLE IF NOT EXISTS timeline (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  incident_id INTEGER NOT NULL, at TEXT NOT NULL, kind TEXT NOT NULL, text TEXT, note TEXT
);
CREATE TABLE IF NOT EXISTS actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  incident_id INTEGER NOT NULL, at TEXT NOT NULL, action TEXT NOT NULL, note TEXT, decision TEXT
);
CREATE TABLE IF NOT EXISTS confirmations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  incident_id INTEGER NOT NULL, at TEXT NOT NULL, still_there INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_conf_inc ON confirmations(incident_id);
CREATE INDEX IF NOT EXISTS ix_timeline_inc ON timeline(incident_id);
CREATE INDEX IF NOT EXISTS ix_reports_inc ON reports(incident_id);
CREATE INDEX IF NOT EXISTS ix_actions_inc ON actions(incident_id);
"""

INCIDENT_COLS = (
    "lat",
    "lon",
    "street",
    "ward",
    "created_at",
    "updated_at",
    "status",
    "report_count",
    "photo_url",
    "photo_path",
    "photo_sha",
    "cleared_photo_url",
    "cleared_at",
    "public_summary",
    "description",
    "triage",
    "model_raw",
    "seed_key",
)


def conn() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            DATA.mkdir(parents=True, exist_ok=True)
            _conn = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.executescript(SCHEMA)
        return _conn


def close():
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None


def _row(r: sqlite3.Row | None) -> dict | None:
    if r is None:
        return None
    d = dict(r)
    for k in ("triage", "model_raw"):
        if d.get(k):
            try:
                d[k] = json.loads(d[k])
            except ValueError:
                d[k] = None
    return d


def _enc(fields: dict) -> dict:
    out = {}
    for k, v in fields.items():
        if k not in INCIDENT_COLS:
            raise KeyError(k)
        out[k] = json.dumps(v) if k in ("triage", "model_raw") and v is not None else v
    return out


def count_incidents() -> int:
    with _lock:
        return conn().execute("SELECT COUNT(*) FROM incidents").fetchone()[0]


def insert_incident(**fields) -> int:
    fields.setdefault("created_at", now_iso())
    fields.setdefault("updated_at", fields["created_at"])
    f = _enc(fields)
    with _lock:
        cur = conn().execute(
            f"INSERT INTO incidents ({','.join(f)}) VALUES ({','.join('?' * len(f))})", tuple(f.values())
        )
        return cur.lastrowid


def update_incident(iid: int, touch: str | None = None, **fields):
    fields["updated_at"] = touch or now_iso()
    f = _enc(fields)
    with _lock:
        conn().execute(f"UPDATE incidents SET {','.join(k + '=?' for k in f)} WHERE id=?", (*f.values(), iid))


def get_incident(iid: int) -> dict | None:
    with _lock:
        return _row(conn().execute("SELECT * FROM incidents WHERE id=?", (iid,)).fetchone())


def list_incidents() -> list[dict]:
    with _lock:
        return [_row(r) for r in conn().execute("SELECT * FROM incidents ORDER BY created_at DESC, id DESC")]


def add_report(incident_id: int, **fields) -> int:
    fields.setdefault("created_at", now_iso())
    keys = ("created_at", "lat", "lon", "loc_source", "description", "reporter", "photo_url", "photo_sha")
    vals = [fields.get(k) for k in keys]
    with _lock:
        cur = conn().execute(
            f"INSERT INTO reports (incident_id,{','.join(keys)}) VALUES (?{',?' * len(keys)})", (incident_id, *vals)
        )
        return cur.lastrowid


def add_timeline(incident_id: int, kind: str, text: str, at: str | None = None, note: str | None = None):
    with _lock:
        conn().execute(
            "INSERT INTO timeline (incident_id, at, kind, text, note) VALUES (?,?,?,?,?)",
            (incident_id, at or now_iso(), kind, text, note),
        )


def add_action(
    incident_id: int, action: str, at: str | None = None, note: str | None = None, decision: str | None = None
):
    with _lock:
        conn().execute(
            "INSERT INTO actions (incident_id, at, action, note, decision) VALUES (?,?,?,?,?)",
            (incident_id, at or now_iso(), action, note, decision),
        )


def timelines(ids: list[int] | None = None) -> dict[int, list[dict]]:
    with _lock:
        if ids is None:
            rows = conn().execute("SELECT * FROM timeline ORDER BY at, id").fetchall()
        else:
            if not ids:
                return {}
            q = ",".join("?" * len(ids))
            rows = (
                conn()
                .execute(f"SELECT * FROM timeline WHERE incident_id IN ({q}) ORDER BY at, id", tuple(ids))
                .fetchall()
            )
    out: dict[int, list[dict]] = {}
    for r in rows:
        out.setdefault(r["incident_id"], []).append(dict(r))
    return out


def all_actions() -> list[dict]:
    with _lock:
        return [dict(r) for r in conn().execute("SELECT * FROM actions ORDER BY at, id")]


def all_reports() -> list[dict]:
    with _lock:
        return [dict(r) for r in conn().execute("SELECT * FROM reports ORDER BY created_at, id")]


def add_confirmation(incident_id: int, still_there: bool, at: str | None = None):
    with _lock:
        conn().execute(
            "INSERT INTO confirmations (incident_id, at, still_there) VALUES (?,?,?)",
            (incident_id, at or now_iso(), 1 if still_there else 0),
        )


def all_confirmations() -> list[dict]:
    with _lock:
        return [dict(r) for r in conn().execute("SELECT * FROM confirmations ORDER BY at, id")]

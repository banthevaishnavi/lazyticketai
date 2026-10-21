"""SQLite persistence for tickets and the activity log."""
import contextlib
import sqlite3
from datetime import datetime
from pathlib import Path


class DatabaseError(Exception):
    """Raised for any SQLite failure so the UI can show a friendly message."""


TICKET_FIELDS = [
    "ticket_ref", "customer_name", "customer_email", "channel", "subject",
    "description", "created_at", "status", "category", "priority", "sentiment",
    "summary", "recommended_team", "draft_response", "ai_source", "ai_error",
    "duplicate_of", "duplicate_score", "review_status", "reviewer_notes",
    "processed_at", "updated_at",
]
STATUSES = ["New", "Processed", "In Progress", "Resolved", "Closed"]
REVIEW_STATUSES = ["Not Ready", "Pending Review", "Approved", "Rejected"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_ref TEXT UNIQUE NOT NULL,
    customer_name TEXT DEFAULT '',
    customer_email TEXT DEFAULT '',
    channel TEXT DEFAULT 'Email',
    subject TEXT NOT NULL,
    description TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT DEFAULT 'New',
    category TEXT, priority TEXT, sentiment TEXT, summary TEXT,
    recommended_team TEXT, draft_response TEXT,
    ai_source TEXT, ai_error TEXT,
    duplicate_of TEXT, duplicate_score REAL,
    review_status TEXT DEFAULT 'Not Ready',
    reviewer_notes TEXT DEFAULT '',
    processed_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT DEFAULT ''
);
"""


def now():
    return datetime.now().isoformat(timespec="seconds")


@contextlib.contextmanager
def connect(db_path):
    try:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path, timeout=10)
        conn.row_factory = sqlite3.Row
    except (sqlite3.Error, OSError) as exc:
        raise DatabaseError(f"Cannot open database '{db_path}': {exc}") from exc
    try:
        yield conn
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        raise DatabaseError(f"Database error: {exc}") from exc
    finally:
        conn.close()


def init_db(db_path):
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)


def log_activity(db_path, action, detail=""):
    with connect(db_path) as conn:
        conn.execute("INSERT INTO activity_log (ts, action, detail) VALUES (?, ?, ?)",
                     (now(), action, detail))


def list_activity(db_path, limit=50):
    with connect(db_path) as conn:
        rows = conn.execute("SELECT ts, action, detail FROM activity_log ORDER BY id DESC LIMIT ?",
                            (limit,)).fetchall()
    return [dict(r) for r in rows]


def next_ref(conn):
    row = conn.execute("SELECT MAX(id) AS m FROM tickets").fetchone()
    n = (row["m"] or 0) + 1001
    while conn.execute("SELECT 1 FROM tickets WHERE ticket_ref = ?", (f"TCK-{n}",)).fetchone():
        n += 1
    return f"TCK-{n}"


def insert_ticket(db_path, ticket):
    """Insert a ticket dict (subject + description required). Returns the new id."""
    subject = str(ticket.get("subject", "")).strip()
    description = str(ticket.get("description", "")).strip()
    if not subject or not description:
        raise ValueError("subject and description are required")
    data = {k: ticket[k] for k in TICKET_FIELDS if k in ticket and ticket[k] not in (None, "")}
    data.update(subject=subject, description=description)
    data.setdefault("created_at", now())
    data.setdefault("status", "New")
    data["updated_at"] = now()
    with connect(db_path) as conn:
        data.setdefault("ticket_ref", next_ref(conn))
        cols = ", ".join(data)
        marks = ", ".join("?" for _ in data)
        cur = conn.execute(f"INSERT INTO tickets ({cols}) VALUES ({marks})", list(data.values()))
        return cur.lastrowid


def ref_exists(db_path, ref):
    with connect(db_path) as conn:
        return conn.execute("SELECT 1 FROM tickets WHERE ticket_ref = ?", (ref,)).fetchone() is not None


def update_ticket(db_path, ticket_id, fields):
    unknown = set(fields) - set(TICKET_FIELDS)
    if unknown:
        raise ValueError(f"Unknown ticket fields: {sorted(unknown)}")
    if not fields:
        return True
    fields = dict(fields, updated_at=now())
    sets = ", ".join(f"{k} = ?" for k in fields)
    with connect(db_path) as conn:
        conn.execute(f"UPDATE tickets SET {sets} WHERE id = ?", [*fields.values(), ticket_id])
    return True


def get_ticket(db_path, ticket_id):
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    return dict(row) if row else None


def list_tickets(db_path, search="", statuses=None, categories=None, priorities=None,
                 review_statuses=None):
    sql = "SELECT * FROM tickets WHERE 1=1"
    params = []
    if search:
        sql += (" AND (subject LIKE ? OR description LIKE ? OR customer_name LIKE ?"
                " OR ticket_ref LIKE ? OR IFNULL(summary,'') LIKE ?)")
        params += [f"%{search}%"] * 5
    for col, values in (("status", statuses), ("category", categories),
                        ("priority", priorities), ("review_status", review_statuses)):
        if values:
            sql += f" AND {col} IN ({', '.join('?' for _ in values)})"
            params += list(values)
    sql += " ORDER BY id"
    with connect(db_path) as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def count_tickets(db_path):
    with connect(db_path) as conn:
        return conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]


def delete_all(db_path):
    with connect(db_path) as conn:
        conn.execute("DELETE FROM tickets")
        conn.execute("DELETE FROM activity_log")


def metrics(db_path, manual_minutes_per_ticket=8.0):
    with connect(db_path) as conn:
        q = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
        total = q("SELECT COUNT(*) FROM tickets")
        ai = q("SELECT COUNT(*) FROM tickets WHERE ai_source LIKE 'AI:%'")
        fallback = q("SELECT COUNT(*) FROM tickets WHERE ai_source LIKE 'Rule-based%'")
        return {
            "total": total,
            "new": q("SELECT COUNT(*) FROM tickets WHERE status = 'New'"),
            "processed_ai": ai,
            "processed_fallback": fallback,
            "pending_review": q("SELECT COUNT(*) FROM tickets WHERE review_status = 'Pending Review'"),
            "approved": q("SELECT COUNT(*) FROM tickets WHERE review_status = 'Approved'"),
            "urgent_high": q("SELECT COUNT(*) FROM tickets WHERE priority IN ('Urgent', 'High')"),
            "duplicates": q("SELECT COUNT(*) FROM tickets WHERE duplicate_of IS NOT NULL"),
            "errors": q("SELECT COUNT(*) FROM tickets WHERE IFNULL(ai_error, '') != ''"),
            "hours_saved": round((ai + fallback) * manual_minutes_per_ticket / 60, 1),
        }

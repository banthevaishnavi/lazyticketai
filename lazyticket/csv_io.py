"""CSV import/export with validation."""
import io

import pandas as pd

from . import db

REQUIRED = ["subject", "description"]
OPTIONAL = ["ticket_ref", "customer_name", "customer_email", "channel", "created_at"]
MAX_ROWS = 5000


def read_tickets_csv(source):
    """Parse CSV (path, bytes or file-like). Returns (rows, errors)."""
    if isinstance(source, (bytes, bytearray)):
        source = io.BytesIO(source)
    try:
        df = pd.read_csv(source, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        return [], ["CSV file is empty."]
    except (pd.errors.ParserError, UnicodeDecodeError, ValueError, OSError) as exc:
        return [], [f"Could not read CSV: {exc}"]
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        return [], [f"Missing required column(s): {', '.join(missing)}. Found: {', '.join(df.columns)}"]
    if len(df) > MAX_ROWS:
        return [], [f"Too many rows ({len(df)}). Maximum is {MAX_ROWS}."]
    rows, errors = [], []
    for n, rec in enumerate(df.to_dict("records"), start=2):  # line 1 is the header
        row = {k: str(rec.get(k, "")).strip() for k in REQUIRED + OPTIONAL if k in rec}
        if not row.get("subject") or not row.get("description"):
            errors.append(f"Row {n}: subject and description are required - skipped.")
            continue
        rows.append(row)
    return rows, errors


def import_rows(db_path, rows):
    """Insert parsed rows. Returns (imported_count, messages)."""
    imported, messages = 0, []
    for row in rows:
        if row.get("ticket_ref") and db.ref_exists(db_path, row["ticket_ref"]):
            messages.append(f"{row['ticket_ref']}: already exists - skipped.")
            continue
        try:
            db.insert_ticket(db_path, row)
            imported += 1
        except (ValueError, db.DatabaseError) as exc:
            messages.append(f"{row.get('ticket_ref') or row['subject'][:40]}: {exc}")
    return imported, messages


def _safe_cell(value):
    """Prevent spreadsheet formula injection in exported files."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def export_csv(tickets):
    df = pd.DataFrame(tickets, columns=["id"] + db.TICKET_FIELDS)
    df = df.apply(lambda col: col.map(_safe_cell))
    return df.to_csv(index=False).encode("utf-8-sig")

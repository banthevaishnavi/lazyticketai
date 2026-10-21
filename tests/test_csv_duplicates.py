from lazyticket import csv_io, db, duplicates


def test_csv_import_valid_and_bad_rows(db_path):
    data = b"Subject,Description,customer_name\nHello,Need help,Ann\n,missing subject,Bob\n"
    rows, errors = csv_io.read_tickets_csv(data)
    assert len(rows) == 1 and len(errors) == 1
    count, _ = csv_io.import_rows(db_path, rows)
    assert count == 1 and db.count_tickets(db_path) == 1


def test_csv_missing_columns_and_empty():
    assert "Missing required" in csv_io.read_tickets_csv(b"title,body\na,b\n")[1][0]
    assert csv_io.read_tickets_csv(b"")[1] == ["CSV file is empty."]


def test_csv_duplicate_ref_skipped(seeded):
    rows, _ = csv_io.read_tickets_csv(b"ticket_ref,subject,description\nTCK-1001,a,b\n")
    count, msgs = csv_io.import_rows(seeded, rows)
    assert count == 0 and "already exists" in msgs[0]


def test_export_roundtrip_and_formula_escaping(seeded):
    db.update_ticket(seeded, 1, {"summary": "=HYPERLINK(evil)"})
    out = csv_io.export_csv(db.list_tickets(seeded))
    assert b"'=HYPERLINK" in out
    rows, errors = csv_io.read_tickets_csv(out)
    assert len(rows) == 12 and not errors


def test_seed_duplicates_detected(seeded):
    pairs = duplicates.apply_duplicates(seeded, 0.45)
    refs = {(d["subject"], o["subject"]) for d, o, _ in pairs}
    assert ("Double charge on subscription - still no refund",
            "Charged twice for my monthly subscription") in refs
    assert db.metrics(seeded)["duplicates"] == len(pairs) == 1


def test_no_duplicates_for_distinct_or_tiny_input():
    assert duplicates.find_duplicates([{"subject": "a", "description": "b"}]) == []
    tickets = [{"subject": "Login broken", "description": "password reset fails"},
               {"subject": "Dark mode", "description": "please add theme option"}]
    assert duplicates.find_duplicates(tickets) == []

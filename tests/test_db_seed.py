import pytest

from lazyticket import db, seed


def test_seed_inserts_12_once(db_path):
    assert seed.seed(db_path) == 12
    assert seed.seed(db_path) == 0
    assert db.count_tickets(db_path) == 12
    assert seed.seed(db_path, reset=True) == 12
    assert db.count_tickets(db_path) == 12


def test_insert_requires_subject_and_description(db_path):
    with pytest.raises(ValueError):
        db.insert_ticket(db_path, {"subject": " ", "description": "x"})


def test_update_search_filter_and_persist(seeded):
    t = db.list_tickets(seeded, search="PDF")[0]
    db.update_ticket(seeded, t["id"], {"category": "Technical", "priority": "High", "status": "Processed"})
    assert db.get_ticket(seeded, t["id"])["priority"] == "High"
    assert len(db.list_tickets(seeded, categories=["Technical"], priorities=["High"])) == 1
    assert len(db.list_tickets(seeded, statuses=["New"])) == 11


def test_update_rejects_unknown_field(seeded):
    with pytest.raises(ValueError):
        db.update_ticket(seeded, 1, {"id; DROP TABLE tickets": 1})


def test_metrics_and_activity(seeded):
    db.update_ticket(seeded, 1, {"ai_source": "AI: Ollama/gemma3:4b", "review_status": "Pending Review"})
    m = db.metrics(seeded, manual_minutes_per_ticket=6)
    assert m["total"] == 12 and m["processed_ai"] == 1 and m["pending_review"] == 1
    assert m["hours_saved"] == 0.1
    assert db.list_activity(seeded)[0]["action"] == "Seed data"


def test_bad_db_path_raises_database_error(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    with pytest.raises(db.DatabaseError):
        db.init_db(str(blocker / "sub" / "x.db"))

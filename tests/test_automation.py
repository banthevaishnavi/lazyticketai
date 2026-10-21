import json

from lazyticket import ai, automation, db

GOOD = json.dumps({"category": "Technical", "priority": "Medium", "sentiment": "Neutral",
                   "summary": "Issue.", "team": "Technical Support", "draft_response": "Hi. The Support Team"})


def _down(prompt, settings):
    raise ai.AIUnavailableError("down")


def test_batch_with_ai(seeded, settings):
    settings.db_path = seeded
    calls = []
    res = automation.process_tickets(seeded, db.list_tickets(seeded), settings,
                                     progress=lambda *a: calls.append(a), caller=lambda p, s: GOOD)
    assert res.ai_count == 12 and res.fallback_count == 0 and not res.errors
    assert res.duplicates_found == 1 and res.minutes_saved > 0
    t = db.get_ticket(seeded, 1)
    assert t["status"] == "Processed" and t["review_status"] == "Pending Review"
    assert t["ai_source"] == "AI: Ollama/gemma3:4b"
    assert calls[-1][0] == 12


def test_batch_aborts_without_fallback(seeded, settings):
    res = automation.process_tickets(seeded, db.list_tickets(seeded), settings, caller=_down)
    assert res.aborted and res.ai_count == 0 and db.metrics(seeded)["new"] == 12


def test_batch_fallback_is_labelled(seeded, settings):
    res = automation.process_tickets(seeded, db.list_tickets(seeded), settings,
                                     use_fallback=True, caller=_down)
    assert res.fallback_count == 12 and res.ai_count == 0
    assert all(t["ai_source"] == ai.FALLBACK_SOURCE for t in db.list_tickets(seeded))


def test_invalid_ai_response_recorded(seeded, settings):
    tickets = db.list_tickets(seeded)[:2]
    res = automation.process_tickets(seeded, tickets, settings, caller=lambda p, s: "not json")
    assert res.failed == 2 and len(res.errors) == 2
    assert "Invalid AI response" in db.get_ticket(seeded, tickets[0]["id"])["ai_error"]
    assert db.get_ticket(seeded, tickets[0]["id"])["status"] == "New"

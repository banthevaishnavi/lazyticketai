import json

import pytest

from lazyticket import ai

VALID = {"category": "billing", "priority": "HIGH", "sentiment": "Negative",
         "summary": "Customer double charged.", "team": "Billing Team",
         "draft_response": "Hi, sorry about that. The Support Team"}


def test_parse_valid_and_normalises_case():
    r = ai.parse_ai_response(json.dumps(VALID))
    assert r["category"] == "Billing" and r["priority"] == "High"
    assert r["recommended_team"] == "Billing Team"


def test_parse_handles_code_fences_and_chatter():
    r = ai.parse_ai_response("Sure!\n```json\n" + json.dumps(VALID) + "\n```")
    assert r["sentiment"] == "Negative"


def test_parse_defaults_team_from_category():
    r = ai.parse_ai_response(json.dumps(dict(VALID, team="Nobody")))
    assert r["recommended_team"] == "Billing Team"


@pytest.mark.parametrize("text", ["not json", "{bad json}", "[1, 2]",
                                  json.dumps(dict(VALID, priority="whenever")),
                                  json.dumps({k: v for k, v in VALID.items() if k != "summary"})])
def test_parse_rejects_invalid(text):
    with pytest.raises(ai.AIResponseError):
        ai.parse_ai_response(text)


def test_analyze_with_ai_retries_then_succeeds(settings):
    answers = iter(["garbage", json.dumps(VALID)])
    r = ai.analyze_with_ai({"subject": "s", "description": "d"}, settings, caller=lambda p, s: next(answers))
    assert r["ai_source"] == "AI: Ollama/gemma3:4b"


def test_analyze_with_ai_gives_up_after_retries(settings):
    with pytest.raises(ai.AIResponseError):
        ai.analyze_with_ai({"subject": "s", "description": "d"}, settings, caller=lambda p, s: "nope")


def test_unreachable_ollama_raises_unavailable(settings):
    with pytest.raises(ai.AIUnavailableError):
        ai.call_ollama("hi", settings)
    ok, msg = ai.check_ollama(settings.ollama_host, settings.ollama_model, timeout=1)
    assert not ok and "ollama serve" in msg


def test_rule_based_is_clearly_labelled():
    r = ai.analyze_rule_based({"subject": "URGENT: API down", "description": "All calls return 500 error.",
                               "customer_name": "Dana X"})
    assert r["ai_source"] == ai.FALLBACK_SOURCE and "NOT AI" in r["ai_source"]
    assert r["priority"] == "Urgent" and r["category"] == "Technical"
    assert "NOT AI" in r["draft_response"]


def test_prompt_contains_ticket_and_allowed_values():
    p = ai.build_prompt({"subject": "Refund", "description": "Charged twice"})
    assert "Charged twice" in p and "Billing" in p and "Urgent" in p

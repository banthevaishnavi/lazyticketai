"""Local AI triage through Ollama + Gemma, plus a clearly labelled rule-based fallback."""
import json
import re
import urllib.error
import urllib.request

CATEGORIES = ["Billing", "Technical", "Account", "Shipping", "Feature Request", "General"]
PRIORITIES = ["Low", "Medium", "High", "Urgent"]
SENTIMENTS = ["Positive", "Neutral", "Negative"]
TEAMS = {
    "Billing": "Billing Team",
    "Technical": "Technical Support",
    "Account": "Account & Security",
    "Shipping": "Logistics",
    "Feature Request": "Product Team",
    "General": "Customer Success",
}
FALLBACK_SOURCE = "Rule-based fallback (NOT AI)"

SYSTEM_PROMPT = "You are a careful customer-support triage assistant. Reply with valid JSON only."


class AIUnavailableError(Exception):
    """Ollama is not reachable or the model is not installed."""


class AIResponseError(Exception):
    """The model answered, but the answer was not usable."""


def ai_source(model):
    return f"AI: Ollama/{model}"


def _get_json(url, timeout, data=None):
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_ollama(host, model, timeout=3):
    """Return (ok, message). ok is True only if Ollama runs AND the model is installed."""
    try:
        tags = _get_json(f"{host}/api/tags", timeout)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return False, f"Ollama not reachable at {host} ({exc}). Start it with: ollama serve"
    names = {m.get("name", "") for m in tags.get("models", [])}
    if model in names or f"{model}:latest" in names:
        return True, f"Ollama running, model '{model}' ready"
    return False, f"Model '{model}' not installed. Run: ollama pull {model}"


def build_prompt(ticket):
    return (
        "Triage this support ticket. Return a JSON object with exactly these keys:\n"
        f'"category": one of {CATEGORIES}\n'
        f'"priority": one of {PRIORITIES}\n'
        f'"sentiment": one of {SENTIMENTS}\n'
        '"summary": one sentence, max 25 words\n'
        f'"team": one of {list(TEAMS.values())}\n'
        '"draft_response": polite reply to the customer, max 90 words, no promised refunds '
        'or dates, signed "The Support Team"\n\n'
        f"Subject: {str(ticket.get('subject', ''))[:200]}\n"
        f"Description: {str(ticket.get('description', ''))[:2000]}"
    )


def call_ollama(prompt, settings):
    """Send one chat request to the local Ollama server and return the raw text."""
    body = json.dumps({
        "model": settings.ollama_model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": prompt}],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.2, "num_predict": 400},
    }).encode("utf-8")
    try:
        data = _get_json(f"{settings.ollama_host}/api/chat", settings.ollama_timeout, body)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise AIUnavailableError(
                f"Model '{settings.ollama_model}' not found. Run: ollama pull {settings.ollama_model}"
            ) from exc
        raise AIResponseError(f"Ollama HTTP error {exc.code}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise AIUnavailableError(f"Ollama not reachable at {settings.ollama_host}: {exc}") from exc
    except ValueError as exc:
        raise AIResponseError("Ollama returned non-JSON HTTP body") from exc
    content = (data.get("message") or {}).get("content", "")
    if not content:
        raise AIResponseError("Empty response from model")
    return content


def _match(value, allowed):
    v = str(value or "").strip().lower()
    for option in allowed:
        if v == option.lower():
            return option
    for option in allowed:
        if option.lower() in v or (v and v in option.lower()):
            return option
    return None


def parse_ai_response(text):
    """Extract and validate the model's JSON. Raises AIResponseError if unusable."""
    cleaned = re.sub(r"```(?:json)?", "", str(text)).strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise AIResponseError("No JSON object in model output")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise AIResponseError(f"Invalid JSON from model: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise AIResponseError("Model JSON is not an object")
    data = {str(k).lower(): v for k, v in data.items()}

    category = _match(data.get("category"), CATEGORIES)
    priority = _match(data.get("priority"), PRIORITIES)
    sentiment = _match(data.get("sentiment"), SENTIMENTS)
    summary = str(data.get("summary") or "").strip()
    draft = str(data.get("draft_response") or data.get("response") or "").strip()
    missing = [n for n, v in (("category", category), ("priority", priority),
                              ("sentiment", sentiment), ("summary", summary),
                              ("draft_response", draft)) if not v]
    if missing:
        raise AIResponseError(f"Missing/invalid fields: {', '.join(missing)}")
    team = _match(data.get("team"), list(TEAMS.values())) or TEAMS[category]
    return {
        "category": category, "priority": priority, "sentiment": sentiment,
        "summary": summary[:400], "recommended_team": team, "draft_response": draft[:2000],
    }


def analyze_with_ai(ticket, settings, retries=1, caller=call_ollama):
    """Run Gemma on one ticket. Retries once on an unusable answer."""
    prompt = build_prompt(ticket)
    last_error = None
    for _ in range(retries + 1):
        raw = caller(prompt, settings)  # AIUnavailableError propagates immediately
        try:
            result = parse_ai_response(raw)
            result["ai_source"] = ai_source(settings.ollama_model)
            return result
        except AIResponseError as exc:
            last_error = exc
    raise last_error


# ---------------- Rule-based fallback: keyword heuristics, NOT AI ----------------
_KEYWORDS = {
    "Billing": ["invoice", "charge", "charged", "refund", "payment", "billing", "subscription", "price"],
    "Technical": ["error", "crash", "bug", "not working", "broken", "api", "timeout", "sync", "500", "slow"],
    "Account": ["password", "login", "log in", "account", "2fa", "locked", "email change", "hacked"],
    "Shipping": ["delivery", "shipping", "package", "tracking", "courier", "arrived", "order"],
    "Feature Request": ["feature", "would be great", "suggest", "add support", "dark mode", "integration"],
}
_URGENT = ["urgent", "asap", "immediately", "outage", "down", "hacked", "security", "data loss"]
_HIGH = ["cannot", "can't", "unable", "blocked", "twice", "double", "angry", "still"]
_NEGATIVE = ["angry", "frustrated", "terrible", "unacceptable", "disappointed", "worst", "annoyed", "still"]
_POSITIVE = ["love", "great", "thanks", "thank you", "awesome", "appreciate"]


def analyze_rule_based(ticket):
    text = f"{ticket.get('subject', '')} {ticket.get('description', '')}".lower()
    scores = {c: sum(k in text for k in kws) for c, kws in _KEYWORDS.items()}
    category = max(scores, key=scores.get) if max(scores.values()) else "General"
    if any(k in text for k in _URGENT):
        priority = "Urgent"
    elif any(k in text for k in _HIGH):
        priority = "High"
    elif category == "Feature Request":
        priority = "Low"
    else:
        priority = "Medium"
    neg = sum(k in text for k in _NEGATIVE)
    pos = sum(k in text for k in _POSITIVE)
    sentiment = "Negative" if neg > pos else "Positive" if pos > neg else "Neutral"
    first = re.split(r"(?<=[.!?])\s", str(ticket.get("description", "")).strip())[0]
    name = str(ticket.get("customer_name") or "there").split(" ")[0]
    return {
        "category": category,
        "priority": priority,
        "sentiment": sentiment,
        "summary": first[:200],
        "recommended_team": TEAMS[category],
        "draft_response": (
            f"Hi {name},\n\nThank you for contacting us about \"{ticket.get('subject', '')}\". "
            f"Our {TEAMS[category]} has received your request and will follow up shortly.\n\n"
            "The Support Team\n[Template generated by rules - NOT AI. Please personalise before sending.]"
        ),
        "ai_source": FALLBACK_SOURCE,
    }

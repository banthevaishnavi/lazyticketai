"""One-click batch pipeline: Gemma triage for every ticket, then duplicate detection."""
import time
from dataclasses import dataclass, field

from . import ai, db, duplicates


@dataclass
class BatchResult:
    total: int = 0
    ai_count: int = 0
    fallback_count: int = 0
    failed: int = 0
    aborted: bool = False
    errors: list = field(default_factory=list)
    seconds: float = 0.0
    duplicates_found: int = 0
    minutes_saved: float = 0.0


def process_tickets(db_path, tickets, settings, use_fallback=False, progress=None,
                    caller=ai.call_ollama):
    """Triage tickets one by one (slow and steady). progress(done, total, ticket, elapsed)."""
    result = BatchResult(total=len(tickets))
    start = time.perf_counter()
    ai_down = None  # once Ollama is unreachable (fallback mode), stop retrying it per ticket
    for idx, ticket in enumerate(tickets):
        if progress:
            progress(idx, len(tickets), ticket, time.perf_counter() - start)
        error = ""
        try:
            if ai_down:
                raise ai_down
            analysis = ai.analyze_with_ai(ticket, settings, caller=caller)
        except ai.AIUnavailableError as exc:
            if not use_fallback:
                result.aborted = True
                result.errors.append(f"AI unavailable - batch stopped: {exc}")
                break
            ai_down = exc
            error = f"AI unavailable: {exc}"
            analysis = ai.analyze_rule_based(ticket)
        except ai.AIResponseError as exc:
            if not use_fallback:
                result.failed += 1
                result.errors.append(f"{ticket['ticket_ref']}: invalid AI response ({exc})")
                db.update_ticket(db_path, ticket["id"], {"ai_error": f"Invalid AI response: {exc}"})
                continue
            error = f"Invalid AI response: {exc}"
            analysis = ai.analyze_rule_based(ticket)

        if analysis["ai_source"] == ai.FALLBACK_SOURCE:
            result.fallback_count += 1
            if error:
                result.errors.append(f"{ticket['ticket_ref']}: {error} - used rule-based fallback")
        else:
            result.ai_count += 1
        db.update_ticket(db_path, ticket["id"], dict(
            analysis, ai_error=error, status="Processed",
            review_status="Pending Review", processed_at=db.now()))

    result.seconds = round(time.perf_counter() - start, 1)
    if progress:
        progress(result.ai_count + result.fallback_count + result.failed, len(tickets), None, result.seconds)
    try:
        result.duplicates_found = len(duplicates.apply_duplicates(db_path, settings.duplicate_threshold))
    except db.DatabaseError as exc:
        result.errors.append(f"Duplicate detection failed: {exc}")
    done = result.ai_count + result.fallback_count
    result.minutes_saved = round(max(0.0, done * settings.manual_minutes_per_ticket - result.seconds / 60), 1)
    db.log_activity(db_path, "Batch automation",
                    f"{result.ai_count} by Gemma, {result.fallback_count} rule-based fallback, "
                    f"{result.failed} failed, {result.duplicates_found} duplicates, {result.seconds}s"
                    + (" (aborted: AI unavailable)" if result.aborted else ""))
    return result

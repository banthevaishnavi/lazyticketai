"""Duplicate detection with TF-IDF + cosine similarity (classic ML, runs instantly)."""
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from . import db


def find_duplicates(tickets, threshold=0.45):
    """Return [(duplicate_ticket, original_ticket, score)]. Later tickets point to earlier ones."""
    if len(tickets) < 2:
        return []
    texts = [f"{t.get('subject', '')} {t.get('description', '')}" for t in tickets]
    try:
        matrix = TfidfVectorizer(stop_words="english", sublinear_tf=True).fit_transform(texts)
    except ValueError:  # empty vocabulary
        return []
    sim = cosine_similarity(matrix)
    results = []
    for j in range(1, len(tickets)):
        i = max(range(j), key=lambda k: sim[j, k])
        if sim[j, i] >= threshold:
            results.append((tickets[j], tickets[i], round(float(sim[j, i]), 3)))
    return results


def apply_duplicates(db_path, threshold=0.45):
    """Recompute duplicate links for all tickets and store them. Returns the pairs found."""
    tickets = db.list_tickets(db_path)
    pairs = find_duplicates(tickets, threshold)
    found = {dup["id"]: (orig["ticket_ref"], score) for dup, orig, score in pairs}
    for t in tickets:
        ref, score = found.get(t["id"], (None, None))
        if t.get("duplicate_of") != ref or t.get("duplicate_score") != score:
            db.update_ticket(db_path, t["id"], {"duplicate_of": ref, "duplicate_score": score})
    return pairs

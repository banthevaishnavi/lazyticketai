"""LazyTicket AI - Streamlit UI. Run: streamlit run app.py"""
import time

import pandas as pd
import streamlit as st

from lazyticket import ai, automation, csv_io, db, duplicates, seed
from lazyticket.config import get_settings

st.set_page_config(page_title="LazyTicket AI", page_icon="🐢", layout="wide")
st.markdown("""
<style>
.block-container {padding-top: 1.5rem;}
div[data-testid="stMetric"] {background:#111a2e;border:1px solid #1f2a44;border-radius:12px;padding:12px 16px;}
.badge {display:inline-block;padding:2px 10px;border-radius:999px;font-size:0.8rem;font-weight:600;}
.badge-ai {background:#14532d;color:#bbf7d0;}
.badge-rule {background:#7c2d12;color:#fed7aa;}
.badge-none {background:#334155;color:#cbd5e1;}
</style>""", unsafe_allow_html=True)

settings = get_settings()
DB = settings.db_path

try:
    db.init_db(DB)
    if db.count_tickets(DB) == 0:
        seed.seed(DB)
except db.DatabaseError as exc:
    st.error(f"Database unavailable: {exc}")
    st.stop()


@st.cache_data(ttl=15, show_spinner=False)
def model_status(host, model):
    return ai.check_ollama(host, model)


def source_badge(source):
    if not source:
        return '<span class="badge badge-none">Not processed</span>'
    cls = "badge-ai" if source.startswith("AI:") else "badge-rule"
    return f'<span class="badge {cls}">{source}</span>'


def safe(fn, *args, **kwargs):
    """Run a DB call and show a friendly error instead of crashing."""
    try:
        return fn(*args, **kwargs)
    except (db.DatabaseError, ValueError) as exc:
        st.error(str(exc))
        return None


# ---------------- Sidebar ----------------
with st.sidebar:
    st.title("🐢 LazyTicket AI")
    st.caption("Slow and steady support automation with local Gemma.")
    ok, msg = model_status(settings.ollama_host, settings.ollama_model)
    (st.success if ok else st.error)(msg)
    if st.button("Re-check model"):
        model_status.clear()
        st.rerun()
    st.caption(f"Model: `{settings.ollama_model}` @ `{settings.ollama_host}`")
    use_fallback = st.toggle(
        "Allow rule-based fallback", value=False,
        help="If Gemma is unavailable or answers badly, use keyword rules instead. "
             "Results are labelled 'Rule-based fallback (NOT AI)'.")
    if use_fallback:
        st.warning("Fallback ON: some results may be keyword rules, not AI. They are clearly labelled.")
    st.divider()
    confirm_reset = st.checkbox("I understand reset deletes all tickets")
    if st.button("Reset & reseed 12 demo tickets", disabled=not confirm_reset):
        if safe(seed.seed, DB, reset=True):
            st.success("Database reset with 12 demo tickets.")
            st.rerun()
    st.info("Human-in-the-loop: LazyTicket never emails customers. Approved drafts must be sent manually.")

tab_dash, tab_tickets, tab_auto, tab_review, tab_io, tab_why = st.tabs(
    ["📊 Dashboard", "🎫 Tickets", "⚡ Automate", "✅ Review", "📁 Import / Export", "🧠 Why Gemma"])

# ---------------- Dashboard ----------------
with tab_dash:
    m = safe(db.metrics, DB, settings.manual_minutes_per_ticket)
    if m:
        c = st.columns(6)
        c[0].metric("Total tickets", m["total"])
        c[1].metric("Unprocessed", m["new"])
        c[2].metric("Triaged by Gemma", m["processed_ai"],
                    help=f"Rule-based fallback (not AI): {m['processed_fallback']}")
        c[3].metric("Pending review", m["pending_review"])
        c[4].metric("Urgent / High", m["urgent_high"])
        c[5].metric("Est. time saved", f"{m['hours_saved']} h",
                    help=f"{settings.manual_minutes_per_ticket} manual minutes per triaged ticket")
        if m["processed_fallback"]:
            st.warning(f"{m['processed_fallback']} ticket(s) were triaged by rule-based fallback, NOT AI.")
        if m["duplicates"] or m["errors"]:
            st.caption(f"Duplicates detected: {m['duplicates']} · Tickets with AI errors: {m['errors']}")
        tickets = safe(db.list_tickets, DB) or []
        if tickets:
            df = pd.DataFrame(tickets)
            left, right = st.columns(2)
            with left:
                st.subheader("By category")
                st.bar_chart(df["category"].fillna("Unprocessed").value_counts(), color="#22c55e")
            with right:
                st.subheader("By priority")
                st.bar_chart(df["priority"].fillna("Unprocessed").value_counts(), color="#38bdf8")
    st.subheader("Activity log")
    activity = safe(db.list_activity, DB, 50) or []
    if activity:
        st.dataframe(pd.DataFrame(activity), width="stretch", hide_index=True)
    else:
        st.caption("No activity yet.")

# ---------------- Tickets ----------------
with tab_tickets:
    f1, f2, f3, f4 = st.columns([2, 1, 1, 1])
    search = f1.text_input("Search", placeholder="subject, description, customer, ref...")
    statuses = f2.multiselect("Status", db.STATUSES)
    categories = f3.multiselect("Category", ai.CATEGORIES)
    priorities = f4.multiselect("Priority", ai.PRIORITIES)
    rows = safe(db.list_tickets, DB, search, statuses, categories, priorities) or []
    view_cols = ["ticket_ref", "customer_name", "subject", "status", "category", "priority",
                 "sentiment", "recommended_team", "duplicate_of", "review_status", "ai_source"]
    if rows:
        st.dataframe(pd.DataFrame(rows)[view_cols], width="stretch", hide_index=True)
        options = {f"{r['ticket_ref']} - {r['subject'][:60]}": r["id"] for r in rows}
        choice = st.selectbox("Select a ticket to view / edit", list(options))
        t = safe(db.get_ticket, DB, options[choice])
        if t:
            st.markdown(source_badge(t["ai_source"]), unsafe_allow_html=True)
            if t["ai_error"]:
                st.error(f"Last processing issue: {t['ai_error']}")
            if t["duplicate_of"]:
                st.warning(f"Possible duplicate of {t['duplicate_of']} (similarity {t['duplicate_score']})")
            with st.form(f"edit_{t['id']}"):
                subject = st.text_input("Subject", t["subject"])
                description = st.text_area("Description", t["description"], height=120)
                e1, e2, e3, e4 = st.columns(4)

                def pick(col, label, options_, value):
                    opts = ["—"] + options_
                    return col.selectbox(label, opts, index=opts.index(value) if value in opts else 0)

                status = pick(e1, "Status", db.STATUSES, t["status"])
                category = pick(e2, "Category", ai.CATEGORIES, t["category"])
                priority = pick(e3, "Priority", ai.PRIORITIES, t["priority"])
                sentiment = pick(e4, "Sentiment", ai.SENTIMENTS, t["sentiment"])
                team = pick(st, "Recommended team", list(ai.TEAMS.values()), t["recommended_team"])
                summary = st.text_area("Summary", t["summary"] or "", height=70)
                if st.form_submit_button("Save changes"):
                    if not subject.strip() or not description.strip():
                        st.error("Subject and description cannot be empty.")
                    else:
                        none = lambda v: None if v == "—" else v  # noqa: E731
                        changes = {"subject": subject.strip(), "description": description.strip(),
                                   "status": none(status) or "New", "category": none(category),
                                   "priority": none(priority), "sentiment": none(sentiment),
                                   "recommended_team": none(team), "summary": summary}
                        if safe(db.update_ticket, DB, t["id"], changes):
                            safe(db.log_activity, DB, "Ticket edited", t["ticket_ref"])
                            st.success("Saved.")
                            st.rerun()
    else:
        st.info("No tickets match your filters.")
    with st.expander("➕ Add a ticket manually"):
        with st.form("new_ticket", clear_on_submit=True):
            n1, n2, n3 = st.columns(3)
            name = n1.text_input("Customer name")
            email = n2.text_input("Customer email")
            channel = n3.selectbox("Channel", ["Email", "Chat", "Web Form", "Phone"])
            new_subject = st.text_input("Subject*")
            new_desc = st.text_area("Description*")
            if st.form_submit_button("Create ticket"):
                new_id = safe(db.insert_ticket, DB, {"customer_name": name, "customer_email": email,
                                                     "channel": channel, "subject": new_subject,
                                                     "description": new_desc})
                if new_id:
                    safe(db.log_activity, DB, "Ticket created", new_subject[:60])
                    st.success("Ticket created.")
                    st.rerun()

# ---------------- Automate ----------------
with tab_auto:
    st.subheader("One-click batch automation")
    st.write("Gemma classifies, prioritises, scores sentiment, summarises, routes to a team and drafts a "
             "reply for each ticket — one at a time, locally. Then TF-IDF finds duplicates.")
    scope = st.radio("Scope", ["Unprocessed tickets only", "All tickets (re-run)"], horizontal=True)
    all_rows = safe(db.list_tickets, DB) or []
    targets = all_rows if scope.startswith("All") else [r for r in all_rows if r["status"] == "New"]
    st.caption(f"{len(targets)} ticket(s) will be processed. CPU-only machines may take 10-60 s per ticket "
               "— slow and steady.")
    if not ok and not use_fallback:
        st.error("Gemma is not available. Start Ollama and pull the model (see sidebar), "
                 "or explicitly enable the labelled rule-based fallback.")
    run_disabled = not targets or (not ok and not use_fallback)
    if st.button("⚡ Run one-click automation", type="primary", disabled=run_disabled):
        bar = st.progress(0.0, text="Starting...")

        def on_progress(done, total, ticket, elapsed):
            eta = (elapsed / done) * (total - done) if done else None
            label = f"{done}/{total} done · {elapsed:.0f}s elapsed"
            if eta is not None and ticket:
                label += f" · ~{eta:.0f}s remaining"
            if ticket:
                label += f" · now: {ticket['ticket_ref']}"
            bar.progress(min(done / total, 1.0), text=label)

        try:
            res = automation.process_tickets(DB, targets, settings, use_fallback, on_progress)
        except db.DatabaseError as exc:
            st.error(f"Database error during batch: {exc}")
        else:
            st.session_state["last_batch"] = res
            st.rerun()  # refresh dashboard metrics rendered earlier in this run
    res = st.session_state.get("last_batch")
    if res:
        r1, r2, r3, r4, r5 = st.columns(5)
        r1.metric("Triaged by Gemma", res.ai_count)
        r2.metric("Rule-based (NOT AI)", res.fallback_count)
        r3.metric("Failed", res.failed)
        r4.metric("Runtime", f"{res.seconds}s")
        r5.metric("Est. time saved", f"{res.minutes_saved} min")
        if res.aborted:
            st.error("Batch stopped because the AI model became unavailable.")
        for err in res.errors:
            st.warning(err)
        st.success(f"Duplicate detection found {res.duplicates_found} likely duplicate(s). "
                   "Next: review drafts in the ✅ Review tab.")
    st.divider()
    st.subheader("Duplicate detection only")
    thr = st.slider("Similarity threshold", 0.2, 0.9, float(settings.duplicate_threshold), 0.05)
    if st.button("Find duplicates"):
        pairs = safe(duplicates.apply_duplicates, DB, thr)
        if pairs is not None:
            safe(db.log_activity, DB, "Duplicate detection", f"{len(pairs)} pair(s) at threshold {thr}")
            if pairs:
                st.dataframe(pd.DataFrame([{"duplicate": d["ticket_ref"], "original": o["ticket_ref"],
                                            "similarity": s, "subject": d["subject"]}
                                           for d, o, s in pairs]), hide_index=True, width="stretch")
            else:
                st.info("No duplicates above threshold.")

# ---------------- Review ----------------
with tab_review:
    st.subheader("Human review queue")
    st.caption("Nothing is sent automatically. Approve a draft, then copy it into your email/helpdesk yourself.")
    show = st.multiselect("Show", db.REVIEW_STATUSES[1:], default=["Pending Review"])
    queue = safe(db.list_tickets, DB, review_statuses=show) if show else []
    if not queue:
        st.info("Nothing to review. Run automation first.")
    for t in queue or []:
        header = f"{t['ticket_ref']} · {t['priority'] or '?'} · {t['category'] or '?'} · {t['subject'][:60]}"
        with st.expander(header):
            st.markdown(source_badge(t["ai_source"]) + f" &nbsp; Review: **{t['review_status']}**",
                        unsafe_allow_html=True)
            st.write(f"**Customer:** {t['customer_name']} ({t['customer_email']}) · **Sentiment:** "
                     f"{t['sentiment']} · **Team:** {t['recommended_team']}")
            st.write(f"**Summary:** {t['summary']}")
            if t["duplicate_of"]:
                st.warning(f"Possible duplicate of {t['duplicate_of']}")
            with st.form(f"review_{t['id']}"):
                draft = st.text_area("Draft response (editable)", t["draft_response"] or "", height=180)
                notes = st.text_input("Reviewer notes", t["reviewer_notes"] or "")
                a, b, c = st.columns(3)
                save = a.form_submit_button("💾 Save draft")
                approve = b.form_submit_button("✅ Approve")
                reject = c.form_submit_button("❌ Reject")
                if save or approve or reject:
                    fields = {"draft_response": draft, "reviewer_notes": notes}
                    if approve:
                        fields["review_status"] = "Approved"
                    elif reject:
                        fields["review_status"] = "Rejected"
                    if safe(db.update_ticket, DB, t["id"], fields):
                        action = "approved" if approve else "rejected" if reject else "draft saved"
                        safe(db.log_activity, DB, f"Review {action}", t["ticket_ref"])
                        st.rerun()
            if t["review_status"] == "Approved":
                st.code(t["draft_response"] or "", language=None)
                st.caption("Copy the text above and send it manually. LazyTicket never emails customers.")

# ---------------- Import / Export ----------------
with tab_io:
    st.subheader("Import CSV")
    st.caption("Required columns: subject, description. Optional: ticket_ref, customer_name, "
               "customer_email, channel, created_at.")
    upload = st.file_uploader("Choose a CSV file", type=["csv"])
    if upload is not None:
        parsed, errors = csv_io.read_tickets_csv(upload.getvalue())
        for err in errors[:20]:
            st.warning(err)
        if parsed:
            st.dataframe(pd.DataFrame(parsed).head(20), hide_index=True, width="stretch")
            if st.button(f"Import {len(parsed)} ticket(s)"):
                count, msgs = csv_io.import_rows(DB, parsed)
                for msg in msgs[:20]:
                    st.warning(msg)
                safe(db.log_activity, DB, "CSV import", f"{count} imported from {upload.name}")
                st.success(f"Imported {count} ticket(s).")
    st.divider()
    st.subheader("Export CSV")
    export_rows = safe(db.list_tickets, DB) or []
    st.download_button("⬇️ Download all tickets", csv_io.export_csv(export_rows),
                       file_name=f"lazyticket_export_{time.strftime('%Y%m%d_%H%M')}.csv",
                       mime="text/csv", disabled=not export_rows)

# ---------------- Why Gemma ----------------
with tab_why:
    st.markdown(f"""
### Why open-weight Gemma runs the show
Every classification, priority, sentiment score, summary, routing decision and draft reply is produced by
**{settings.ollama_model}** running locally through **Ollama**. Without the model, automation does not run
unless you explicitly enable the rule-based fallback, whose output is always labelled **NOT AI**.

- **Local privacy** – ticket text, customer names and emails never leave this machine. No cloud AI calls.
- **Model flexibility** – swap models with one line in `.env` (`OLLAMA_MODEL=gemma3:1b`, `gemma3:4b`,
  `gemma3:12b`, ...). Outputs are validated against a fixed schema, so any capable model can plug in.
- **No paid inference APIs** – zero per-token cost, no API keys, works offline after `ollama pull`.
- **Slow and steady** – tickets are processed one by one with progress, ETA and retries. A laptop CPU is
  slower than a cloud GPU, but it keeps working, privately, for free.

### Hardware limitations (honest numbers)
| Model | RAM needed (approx.) | Speed on CPU-only laptop |
|---|---|---|
| gemma3:1b | ~4 GB | a few seconds per ticket |
| gemma3:4b | ~8 GB | ~10–60 s per ticket |
| gemma3:12b | ~16 GB+ / GPU recommended | slow without GPU |

Smaller models make more mistakes. That is why every AI output goes to the **human review queue** and
nothing is ever sent to a customer automatically.
""")

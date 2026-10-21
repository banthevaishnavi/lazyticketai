# 🐢 LazyTicket AI — Slow and Steady

One-click support-ticket triage powered by **Gemma running locally through Ollama**.
For each ticket, Gemma classifies it, sets a priority, rates sentiment, writes a summary, recommends a team, and drafts a reply. TF-IDF with cosine similarity flags duplicate tickets. A person reviews every draft before anything goes out. **The app never emails customers.**

Stack: Python · Streamlit · SQLite · Ollama + Gemma · Pandas · scikit-learn · pytest. No paid APIs and no cloud AI.

## 1. Install (Windows PowerShell)

```powershell
cd "D:\LazyTicket AI"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # optional: change the model, timeout, or DB path
```

## 2. Set up Gemma (local, open-weight)

1. Install Ollama from https://ollama.com/download (Windows installer).
2. Pull a Gemma model:
   ```powershell
   ollama pull gemma3:4b     # default: better quality, needs ~8 GB RAM
   # or, for low-RAM laptops:
   ollama pull gemma3:1b     # then set OLLAMA_MODEL=gemma3:1b in .env
   ```
3. Ollama usually runs in the background after you install it. If it doesn't, start it with `ollama serve`.
4. Check that the model works: `ollama run gemma3:4b "hello"`

## 3. Launch

```powershell
streamlit run app.py
```
Then open http://localhost:8501. The first time it starts, the app adds 12 synthetic tickets, including one deliberate duplicate pair. The sidebar shows whether Gemma is ready.

**Demo flow:** Dashboard → ⚡ Automate → **Run one-click automation** (watch the progress and ETA) → ✅ Review (edit, approve, or reject drafts) → 📁 Export CSV.

## 4. Test

```powershell
python -m pytest -q
```
The tests don't need Ollama. They use fake model responses to cover valid, malformed, and unavailable AI.

## Why open-weight AI is essential here

- **Gemma does all the triage work.** If Gemma isn't available, the batch won't run. A **rule-based fallback** exists, but it is off by default and you have to switch it on yourself. Its results are always labelled `Rule-based fallback (NOT AI)` in the UI, the database, and CSV exports.
- **Local privacy:** ticket text and customer details stay on your machine. The only network call goes to `127.0.0.1:11434`.
- **Model flexibility:** you can switch models with `OLLAMA_MODEL` in `.env` (for example `gemma3:1b`, `gemma3:4b`, or `gemma3:12b`). The app checks every output against a fixed schema and retries once if the output is invalid.
- **No paid inference APIs:** there are no API keys and no per-token cost, and it works offline once the model is downloaded. Prompts are short (descriptions are cut to 2,000 characters, `num_predict=400`).
- **Hardware limits:** on a CPU-only laptop, `gemma3:4b` takes about 10–60 s per ticket, and `gemma3:1b` is faster but less accurate. The 12B model needs about 16 GB of RAM or a GPU. That's why processing is *slow and steady*: one ticket at a time, with progress, an ETA, and a 180 s timeout per ticket (`OLLAMA_TIMEOUT`).

## Time saved

Estimated as `triaged tickets × MANUAL_MINUTES_PER_TICKET` (default 8 minutes) minus the machine's processing time. This is an estimate, not a measurement.

## CSV format

You must include the columns `subject` and `description`. Optional columns: `ticket_ref`, `customer_name`, `customer_email`, `channel`, `created_at`. The app skips invalid rows and rows whose `ticket_ref` already exists, and tells you which ones. Exported cells are escaped so spreadsheet formulas can't run.

## Project layout

```
app.py                  Streamlit UI
lazyticket/ai.py        Ollama client, prompt, JSON validation, labelled rule fallback
lazyticket/automation.py  One-click batch pipeline
lazyticket/duplicates.py  TF-IDF + cosine similarity
lazyticket/db.py        SQLite storage + activity log
lazyticket/csv_io.py    CSV import/export
lazyticket/seed.py      12 synthetic tickets
tests/                  pytest suite
```

# Premier League AI Analyst

A Streamlit football analytics dashboard and question answering assistant. `graph.py` contains the LangGraph analyst, `main_app.py` is the dashboard, and `fetch_all.py` loads Understat data into SQLite.

## Requirements

- Python 3.11 (the Understat client currently depends on an aiohttp release without Python 3.12 Windows wheels)
- A Groq API key for analyst chat
- Network access to Understat when fetching data

## Setup

Create and activate a Python 3.11 virtual environment.

Linux/macOS:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
```

Install dependencies and create the environment file:

```text
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set `GROQ_API_KEY`. `PL_SEASON` defaults to `2024`, which means the 2024/25 season in Understat; the legacy `SEASON` variable is also supported. Set `PL_DATA_DB` only if you want the SQLite database somewhere other than the project folder.

Linux/macOS: `cp .env.example .env`
Windows PowerShell: `Copy-Item .env.example .env`

## Run the dashboard

Run these commands from the project folder:

```text
python -m streamlit run main_app.py
```

Use the dashboard's **Refresh Data** button, or fetch data from a terminal:

```text
python fetch_all.py
```

The analyst can also run in a terminal:

```text
python graph.py
```

## Evaluation

Fetch the database first, then run:

```text
python run_eval.py
```

The local database, environment file, and runtime caches are excluded from Git. Each developer creates the database locally by fetching data.

## Optional RAG retrieval

The LangGraph analyst can retrieve relevant season records from a local ChromaDB index and combine them with SQL results. RAG is off by default, so the app works without a local embedding service. To enable it:

1. Install and start [Ollama](https://ollama.com/), then download the embedding model with `ollama pull nomic-embed-text`.
2. Install project dependencies with `pip install -r requirements.txt`.
3. Fetch or prepare the SQLite database, then build the local vector index with `python rag.py`.
4. Set `PL_RAG_ENABLED=true` in `.env` and restart Streamlit.

The index is stored in the ignored `chroma_db/` folder. Re-run `python rag.py` after refreshing data. Set `RAG_OLLAMA_URL` or `RAG_EMBEDDING_MODEL` in `.env` to use a different local Ollama endpoint or embedding model. RAG supplies related context; SQL remains the source for exact statistics.

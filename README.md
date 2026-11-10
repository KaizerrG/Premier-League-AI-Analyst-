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

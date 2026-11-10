# Premier League AI Analyst

A Streamlit football analytics dashboard and question answering assistant. The LangGraph workflow in `graph.py` is the analyst entry point; `main_app.py` is the app entry point.

## Features

- Ask natural language questions about league standings, players, and match data.
- Explore league tables, xG analysis, top scorers, and player comparisons.
- Fetch data from Understat into a local SQLite database.

## Setup

Use Python 3.10 or newer:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
```

Create a `.env` file with your Groq API key:

```text
GROQ_API_KEY=your_key_here
```

## Run

Fetch data when needed, then start the dashboard:

```bash
python fetch_all.py
streamlit run main_app.py
```

To run the analyst directly:

```bash
python graph.py
```

The eval harness uses the questions in `golden_set.json`:

```bash
python run_eval.py --db pl_data.db --golden golden_set.json
```

`pl_data.db` is generated locally and is not included in Git. Fetch data before running the dashboard or eval.

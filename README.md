# Premier League AI Analyst 🏴󠁧󠁢󠁥󠁮󠁧󠁿⚽

> 🚧 Project Under Active Development

An agentic AI application that answers natural language questions 
about the Premier League 2024/25 season using real match data, 
RAG architecture, and a local LLM.

## What It Does
Ask plain english questions like:
- "Who is the top scorer?"
- "What was Arsenal's xG in gameweek 28?"
- "Which team has the best goal difference?"

## Tech Stack
- **Data** → API-Football + SQLite
- **RAG** → ChromaDB + nomic-embed-text
- **AI Brain** → Ollama + LLaMA3
- **UI** → Streamlit

## Architecture
API-Football → fetch_data.py → SQLite (pl_data.db)
                                        ↓
                                     rag.py
                                        ↓
                              ChromaDB (embeddings)
                                        ↓
                                    agent.py
                                        ↓
                                 Ollama / LLaMA3
                                        ↓
                              app.py (Streamlit UI)
                                        ↓
                              Natural Language Answer

## Setup
```bash
git clone <your-repo-url>
cd pl-analyst
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Add `.env` file:

API_FOOTBALL_KEY=your_key_here
SEASON=2024

Run:
```bash
python fetch_data.py
python rag.py
streamlit run app.py
```

## Roadmap
- [ ] Advanced RAG with reranking
- [ ] Player comparison feature
- [ ] xG visualizations
- [ ] WC 2026 data integration
- [ ] GPT-4 / Claude API option

## Status
Under development. Core pipeline working.


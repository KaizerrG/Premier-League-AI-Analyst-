# Premier League AI Analyst Project Brief

## 1. Overview

This project is a football analytics and question-answering application built around Premier League data. The goal is to let a user ask natural-language questions like:

- Who is the top scorer?
- What was Arsenal's xG in gameweek 28?
- Which team has the best goal difference?
- Who is the most creative midfielder?
- Compare Salah and Haaland.

The system is designed to answer using real football data, not just generic knowledge. It combines structured database queries, semantic retrieval, and large-language-model reasoning.

At a high level, the app works like this:

- fetch football data from APIs,
- store it in SQLite,
- build a vector database for retrieval,
- query the DB or vector store with AI,
- answer user questions through a Streamlit interface,
- visualize key analytics in dashboards.

---

## 2. What this project is trying to do

This is a Premier League analytics assistant. It attempts to answer football questions in a way that looks like a real data analyst or expert football reporter.

It supports:

- player performance analysis,
- team standings analysis,
- xG (expected goals) analysis,
- fixture and match comparison,
- natural-language query answering over data,
- interactive dashboard exploration.

The project is especially centered around:

- player stats,
- team rankings,
- expected goals,
- match performance,
- historical football data retrieval.

---

## 3. Main architecture

The architecture is layered, and it is best understood as a combination of these parts:

1. Data ingestion layer
2. Storage layer
3. Retrieval layer
4. AI reasoning layer
5. User interface layer
6. Visualization layer

### 3.1 Data ingestion layer

This is the part that collects data from external sources.

Key files:

- fetch_data.py
- fetch_all.py
- fetch_xg.py

These scripts fetch football data from APIs such as:

- API-Football
- Understat

The data includes things like:

- league standings,
- player statistics,
- expected goals,
- fixtures,
- team totals,
- match results,
- shot-level data in some versions of the project.

This layer is the foundation. Without data, the AI has nothing to reason over.

### 3.2 Storage layer

The project stores data in SQLite files, especially:

- pl_data.db

This is the primary structured data source.

The app stores data in tables such as:

- standings
- top_scorers
- fixtures
- fixture_stats
- team_stats
- player_xg
- match_xg
- shots

SQLite is used because it is simple, local, easy to query, and perfect for a prototype analytics app.

### 3.3 Retrieval layer

The retrieval layer uses ChromaDB.

Key file:

- rag.py

This turns sports data into searchable vector documents. In other words, it does not just query raw tables; it chunks the data into text summaries and stores those chunks with embeddings.

The main Chroma collection is:

- pl_data

The embedding model used is:

- Ollama embedding function with nomic-embed-text

That means the system can search data semantically, not only by exact SQL matches.

### 3.4 AI reasoning layer

This is the intelligence layer. There are multiple implementations in the repo:

- agent.py
- graph.py
- crew.py

These are three versions of the reasoning system, each with different architecture.

#### a) Simple RAG agent

File:

- agent.py

This is the simplest version.

It does:

- expand the user's question with related terms,
- query ChromaDB for relevant chunks,
- rerank chunks,
- select top results,
- build a context block,
- send that to Groq LLM,
- return final answer.

This is a classic RAG workflow:

- search relevant information,
- give it to the model,
- ask the model to answer using only that evidence.

#### b) LangGraph workflow

File:

- graph.py

This version is a more structured pipeline.

It defines a state object named PLAnalystState and uses LangGraph to pass information between nodes.

The workflow includes nodes like:

- router_node
- player_node
- match_node
- standings_node
- prediction_node
- final combine logic

The router classifies the user’s question into categories like:

- player
- match
- standings
- prediction

Then the relevant specialist node generates and executes SQL queries against the database. The results are merged and combined into a final answer.

This is a more robust multi-step reasoning architecture.

#### c) CrewAI multi-agent version

File:

- crew.py

This version is the most advanced and “agentic” design.

It defines specialist agents:

- Manager Agent
- Player Statistics Specialist
- Match Analysis Specialist
- League Table Specialist
- Match Prediction Specialist

Each agent has:

- role,
- goal,
- backstory,
- LLM,
- tool access.

There is a SQL tool for executing database queries.

The Crew is built with a hierarchical process, where the manager decides which specialist handles the question. The final answer is synthesized after specialist analysis.

This is a team-based agent architecture.

### 3.5 User interface layer

There are two main UI entry points:

- app.py
- main_app.py

#### app.py

This is the simpler app.

It uses Streamlit and creates a chat UI:

- page title,
- chat history,
- user input box,
- answer display,
- session-state memory.

It stores chat messages in Streamlit session_state so the conversation persists while the user interacts.

#### main_app.py

This is a richer version with dashboard features.

It contains:

- sidebar navigation,
- AI Chat page,
- Analytics Dashboard page,
- refresh functionality,
- league selector,
- multiple tabs for analytics views.

This is a more complete user-facing dashboard application.

### 3.6 Visualization layer

File:

- visualizations.py

This module uses Streamlit + Plotly to render charts and summary views.

It defines tabs such as:

- League Table
- xG Analysis
- Top Scorers & Playmakers
- Player Comparison

It loads data from SQLite and then renders charts or tables to help the user understand trends visually.

---

## 4. Project runtime flow

The most common flow of this app is:

1. User opens the app in Streamlit.
2. They ask a football question.
3. The app calls the reasoning layer.
4. The system does one of the following:
   - search ChromaDB for relevant football data,
   - or generate SQL against SQLite,
   - or route the query to specialist agents.
5. The LLM reasons over the retrieved evidence.
6. The final answer is shown to the user.
7. For analytics screens, the app loads charts from the database.

The system is therefore a hybrid of:

- retrieval-based QA,
- SQL-based data retrieval,
- direct LLM reasoning,
- agentic orchestration,
- dashboard visualization.

---

## 5. How the RAG process works internally

The RAG workflow in agent.py is a good example of the project’s intelligence cycle.

### Step-by-step:

#### 1. Query expansion

The code calls Groq to expand the original question with related terms.

Example:

- original: “top scorer”
- expanded version: “top scorer goals scored most goals player”

This improves retrieval coverage.

#### 2. Vector search

The app queries ChromaDB with the expanded question.

It asks for the top 20 results for more context before filtering.

#### 3. Reranking

The code reranks the returned chunks based on keyword overlap with the original question.

This helps ensure the most relevant football information is prioritized.

#### 4. Context construction

The top few chunks are combined into a single context block.

#### 5. Prompt engineering

The model is given a football analyst persona and instructed:

- use only the context you are given,
- do not invent information,
- answer using evidence only.

#### 6. LLM response

The Groq LLM then answers in natural language.

This is the classic pattern of grounded LLM reasoning.

---

## 6. How SQL-based analysis works

The LangGraph and CrewAI systems rely heavily on SQL.

The database is queried with SQL to fetch exact values like:

- who is top of the league,
- player xG and xA totals,
- teams with best goal difference,
- matches with highest expected goals,
- who has most assists,
- team form or fixtures.

For example, the system can create SQL prompts asking the LLM to produce a SQL query based on the natural-language question, then Python runs that query against SQLite and returns the output.

This is a powerful pattern because it allows the system to do structured analysis while still being driven by a natural-language interface.

---

## 7. Why the project uses multiple AI frameworks

This is an important architectural clue.

The project seems to have evolved through different phases:

- first simple direct RAG,
- then graph-based orchestration,
- then multi-agent crew orchestration.

This indicates active experimentation and iterative improvement.

Different files are likely testing different ideas:

- simple direct retrieval is easiest and fastest,
- LangGraph gives stronger workflow structure,
- CrewAI gives specialist agent design.

The repo is therefore a lab or experimentation project rather than a single rigid final app.

---

## 8. Data sources used

The project is built around real football data from external services.

### API-Football

Used in fetch_data.py for:

- standings
- top scorers
- fixtures
- team statistics

### Understat

Used in fetch_xg.py and fetch_all.py for:

- expected goals data,
- team xG values,
- match xG,
- player xG,
- shot-level data.

This is important because the project is heavily focused on advanced football metrics like:

- xG,
- xA,
- npxG,
- shots,
- key passes,
- xGChain,
- xGBuildup.

These are advanced metrics characteristic of analytic football models.

---

## 9. File-by-file understanding

### README.md

This explains the project conceptually.

It says the app is:

- AI-powered,
- natural-language football analyst,
- using real match data,
- with RAG and local LLM,
- built with Streamlit.

### app.py

This is the simple chat frontend. It stores chat state and calls the ask() function.

### main_app.py

This is the more complete dashboard. It includes navigation, chat, refresh, and analytics views.

### agent.py

This is the main RAG-based answer engine.

It:

- calls Groq,
- uses ChromaDB,
- reranks chunks,
- returns answer.

### graph.py

This is a more structured LangGraph workflow with specialized nodes and SQL-based reasoning.

### crew.py

This is the CrewAI multi-agent implementation for football analysis.

### rag.py

This builds the knowledge base in ChromaDB from football data tables.

### fetch_data.py

This pulls structured football data from API-Football and stores it into SQLite.

### fetch_all.py

This is a more recent/alternative pipeline using Understat for all league data.

### fetch_xg.py

This is another xG-focused fetching script that builds match_xg and player_xg tables.

### visualizations.py

This generates the dashboard analytics tabs and charts.

### requirements.txt

Shows the dependencies used by the project.

---

## 10. Database tables and data significance

The schema in the project suggests the project is designed to answer multiple classes of football questions.

### standings

Used for:

- position,
- points,
- wins/draws/losses,
- goals scored,
- goals conceded,
- goal difference.

### player_xg

Used for:

- goals,
- assists,
- xG,
- xA,
- npxG,
- shots,
- key passes,
- xGChain,
- xGBuildup,
- minutes,
- games.

This is the table behind player-level analysis.

### fixtures

Used for:

- matches,
- teams,
- goals,
- dates,
- gameweek information.

### match_xg

Used for:

- expected goals for each match,
- home/away expected goals,
- match-level performance.

### fixture_stats

Used for:

- possession,
- shots,
- corners,
- passing,
- other in-match stats.

### shots

Used for:

- shot location,
- xG,
- result,
- minute,
- match context.

These tables support detailed football analysis.

---

## 11. Why the project is useful

This app is useful because it lets users ask complex football questions in plain language and get data-backed answers.

For example:

- Who is the most clinical finisher?
- Which team has been overperforming xG?
- Who is the best chance creator?
- Which team has the strongest expected goal differential?
- Which match had the highest total xG?

The project turns raw football data into natural-language analytics.

---

## 12. Strengths of the overall design

- uses real football data instead of static memories,
- answers in context with evidence,
- supports both SQL and semantic search,
- has multiple reasoning patterns,
- supports dashboard-style insights,
- can be extended to more leagues and more football questions.

---

## 13. Weaknesses and constraints

- multiple script versions can confuse which is the “real” main app,
- the schema is not fully consistent across files,
- some files may be legacy or outdated,
- project depends on external API availability,
- some services such as Ollama and Groq need to be running,
- the application is research/prototype oriented rather than production-hardened.

---

## 14. The likely final project idea

The intended final product is a Premier League football analytics assistant with:

- natural-language conversations,
- tailored football insights,
- SQL-backed accuracy,
- vector-based knowledge retrieval,
- dashboard analytics,
- AI-driven match and player analysis.

It is effectively a domain-specific AI data analyst for football.

---

## 15. Short summary in one paragraph

This project is a Premier League AI analyst that collects football data from external APIs, stores it in SQLite, converts it into searchable embeddings in ChromaDB, and uses LLMs to answer natural-language questions with evidence-based reasoning. It includes multiple versions of the reasoning layer—simple RAG, LangGraph, and CrewAI—and provides both chat and dashboard interfaces through Streamlit. The final goal is to act as a football analytics assistant capable of answering questions about players, teams, standings, xG, and match analysis using live or season data.

---

## 16. Recommended understanding order for the repo

If someone wants to understand the entire project quickly, the best order is:

1. README.md
2. app.py
3. agent.py
4. rag.py
5. graph.py
6. crew.py
7. fetch_all.py or fetch_xg.py
8. fetch_data.py
9. visualizations.py
10. main_app.py

This order moves from easiest entry point to deeper system logic.

---

## 17. Final note

This project is a strong example of an AI application that blends data engineering, retrieval, LLM prompting, and user-facing analytics. It is not a single simple app; it is a full football analytics system with multiple experimental layers and a clear core idea: make football data conversational and insightful through AI.

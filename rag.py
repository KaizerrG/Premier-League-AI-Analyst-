"""Chroma based retrieval over a text view of the local football database.

Embeddings are generated locally by Ollama. Importing this module does not
connect to Ollama or load Chroma; those happen only when indexing or searching.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from typing import Any

from settings import DATABASE_PATH, PROJECT_ROOT, SEASON

CHROMA_PATH = PROJECT_ROOT / "chroma_db"
COLLECTION_NAME = "pl_analyst"
OLLAMA_URL = os.getenv("RAG_OLLAMA_URL", "http://localhost:11434")
EMBEDDING_MODEL = os.getenv("RAG_EMBEDDING_MODEL", "nomic-embed-text")


def _collection():
    try:
        import chromadb
        from chromadb.utils.embedding_functions import OllamaEmbeddingFunction
    except ImportError as exc:
        raise RuntimeError("RAG dependencies are missing. Install requirements.txt.") from exc

    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    embedding = OllamaEmbeddingFunction(
        url=OLLAMA_URL,
        model_name=EMBEDDING_MODEL,
    )
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding,
        metadata={"hnsw:space": "cosine"},
    )


def _records() -> list[tuple[str, str, dict[str, Any]]]:
    """Build stable, readable retrieval records from current-schema tables."""
    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(f"Database not found: {DATABASE_PATH}. Run fetch_all.py first.")

    conn = sqlite3.connect(f"{DATABASE_PATH.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    records: list[tuple[str, str, dict[str, Any]]] = []
    try:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        queries = {
            "standings": """SELECT league, season, team_name, rank, played, won, drawn,
                lost, goals_for, goals_against, goal_difference, points
                FROM standings WHERE season = ?""",
            "player_xg": """SELECT league, season, player_name, team_name, position,
                games, minutes, goals, assists, xg, xa, npxg
                FROM player_xg WHERE season = ?""",
            "fixtures": """SELECT league, season, fixture_id, home_team, away_team,
                home_goals, away_goals, home_xg, away_xg, match_date
                FROM fixtures WHERE season = ?""",
            "match_xg": """SELECT league, season, match_id, home_team, away_team,
                home_xg, away_xg, match_date FROM match_xg WHERE season = ?""",
        }
        for table, query in queries.items():
            if table not in tables:
                continue
            for row in conn.execute(query, (SEASON,)):
                values = dict(row)
                league = values.get("league") or "Unknown league"
                season = values.get("season") or SEASON
                if table == "standings":
                    text = (
                        f"{league} {season}/{(int(season) + 1) % 100:02d} standings: "
                        f"{values['team_name']} rank {values['rank']}, {values['points']} points, "
                        f"{values['played']} played, record {values['won']}-{values['drawn']}-{values['lost']}, "
                        f"goal difference {values['goal_difference']}."
                    )
                    key = values.get("team_name")
                elif table == "player_xg":
                    text = (
                        f"{league} {season}/{(int(season) + 1) % 100:02d} player stats: "
                        f"{values['player_name']} of {values['team_name']} ({values['position']}), "
                        f"{values['goals']} goals, {values['assists']} assists, xG {values['xg']}, "
                        f"xA {values['xa']}, {values['minutes']} minutes in {values['games']} games."
                    )
                    key = f"{values.get('player_name')}:{values.get('team_name')}"
                else:
                    date = values.get("match_date") or "date unknown"
                    match_id = values.get("fixture_id") or values.get("match_id")
                    text = (
                        f"{league} {season}/{(int(season) + 1) % 100:02d} match on {date}: "
                        f"{values['home_team']} vs {values['away_team']}, "
                        f"score {values.get('home_goals')} - {values.get('away_goals')}, "
                        f"xG {values.get('home_xg')} - {values.get('away_xg')}."
                    )
                    key = match_id or f"{values.get('home_team')}:{values.get('away_team')}:{date}"
                digest = hashlib.sha256(f"{table}:{league}:{season}:{key}".encode()).hexdigest()
                records.append((digest, text, {"table": table, "league": str(league), "season": str(season)}))
    finally:
        conn.close()
    return records


def build_knowledge_base() -> int:
    """Upsert current-season SQLite rows into the persistent Chroma index."""
    records = _records()
    if not records:
        return 0
    collection = _collection()
    batch_size = 250
    for start in range(0, len(records), batch_size):
        batch = records[start : start + batch_size]
        collection.upsert(
            ids=[record[0] for record in batch],
            documents=[record[1] for record in batch],
            metadatas=[record[2] for record in batch],
        )
    return len(records)


def retrieve(question: str, top_k: int = 5) -> list[str]:
    """Return the most relevant indexed records for a question."""
    collection = _collection()
    count = collection.count()
    if count == 0:
        return []
    result = collection.query(
        query_texts=[question],
        n_results=min(top_k, count),
        where={"season": SEASON},
    )
    return result.get("documents", [[]])[0] or []


if __name__ == "__main__":
    count = build_knowledge_base()
    print(f"Indexed {count} records into {CHROMA_PATH} using Ollama/{EMBEDDING_MODEL}.")

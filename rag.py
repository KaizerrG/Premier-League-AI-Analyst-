import sqlite3
import pandas as pd
import chromadb
from chromadb.utils import embedding_functions

# ROCKY: connect to your sqlite database
conn = sqlite3.connect("pl_data.db")

# ROCKY: chromadb client = open your vector database
# PersistentClient = save to disk, not lost when script ends
client = chromadb.PersistentClient(path="./chroma_db")

# ROCKY: embedding function = what converts text to numbers
# we use ollama because it free and local
embedding_fn = embedding_functions.OllamaEmbeddingFunction(
    url="http://localhost:11434",
    model_name="nomic-embed-text"
)

# ROCKY: collection = like a table in chromadb
# get_or_create = make it if not exist, use it if exist
collection = client.get_or_create_collection(
    name="pl_data",
    embedding_function=embedding_fn
)

def chunk_standings():
    # ROCKY: read standings table into dataframe
    df = pd.read_sql("SELECT DISTINCT * FROM standings ORDER BY rank", conn)
    
    chunks = []
    ids = []
    
    for i, row in df.iterrows():
        # ROCKY: convert each row to human readable sentence
        # this what AI will read to answer your questions
        text = (
            f"{row['team_name']} are ranked {row['rank']} in the Premier League "
            f"with {row['points']} points from {row['played']} games. "
            f"They have {row['won']} wins, {row['drawn']} draws, {row['lost']} losses. "
            f"Goals for: {row['goals_for']}, Goals against: {row['goals_against']}, "
            f"Goal difference: {row['goal_difference']}."
        )
        chunks.append(text)
        ids.append(f"standing_{i}_{row['team_name'].replace(' ', '_')}")
    
    return chunks, ids

def chunk_scorers():
    # ROCKY: same thing for top scorers table
    df = pd.read_sql("SELECT * FROM top_scorers ORDER BY goals DESC", conn)
    
    chunks = []
    ids = []
    
    for i, row in df.iterrows():
        text = (
            f"{row['player_name']} plays for {row['team_name']} "
            f"and has scored {row['goals']} goals "
            f"with {row['assists']} assists in the {row['season']} Premier League season."
        )
        chunks.append(text)
        ids.append(f"scorer_{row['season']}_{row['player_name'].replace(' ', '_')}")
    
    return chunks, ids

def chunk_fixtures():
    # ROCKY: last 10 matches as text
    df = pd.read_sql("SELECT * FROM fixtures ORDER BY fixture_date DESC", conn)
    
    chunks = []
    ids = []
    
    for i, row in df.iterrows():
        text = (
            f"{row['home_team']} vs {row['away_team']} "
            f"ended {row['home_goals']}-{row['away_goals']} "
            f"({row['status']}) on {row['fixture_date'][:10]}."
        )
        chunks.append(text)
        ids.append(f"fixture_{row['fixture_id']}")
    
    return chunks, ids

def store_in_chromadb(chunks, ids, label):
        collection.upsert(
        documents=chunks,
        ids=ids)
        print(f"stored {len(chunks)} {label} chunks in chromadb")
    
    # ROCKY: add all chunks to chromadb
    # this is where text gets converted to embeddings and stored
        collection.add(
        documents=chunks,
        ids=ids)
        print(f"stored {len(chunks)} {label} chunks in chromadb")

def main():
    print("building RAG knowledge base...")
    
    print("processing standings...")
    chunks, ids = chunk_standings()
    store_in_chromadb(chunks, ids, "standings")
    
    print("processing scorers...")
    chunks, ids = chunk_scorers()
    store_in_chromadb(chunks, ids, "scorers")
    
    print("processing fixtures...")
    chunks, ids = chunk_fixtures()
    store_in_chromadb(chunks, ids, "fixtures")
    
    print("done. knowledge base ready.")
    
    # ROCKY: test it works. ask a question and see what chunks come back
    print("\ntesting search...")
    results = collection.query(
        query_texts=["who has scored the most goals"],
        n_results=3  # give back top 3 most relevant chunks
    )
    print("\ntop 3 relevant chunks found:")
    for doc in results["documents"][0]:
        print(f"  → {doc}")

if __name__ == "__main__":
    main()
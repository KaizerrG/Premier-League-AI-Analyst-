import sqlite3
import pandas as pd
import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv
load_dotenv()

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
            f"STANDINGS - {row['team_name']} ranked {row['rank']} in Premier League "
            f"with {row['points']} points from {row['played']} games. "
            f"Record: {row['won']}W-{row['drawn']}D-{row['lost']}L. "
            f"Goals: {row['goals_for']} for, {row['goals_against']} against, "
            f"difference: {row['goal_difference']}."
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
            f"TOP SCORER - {row['player_name']} ({row['team_name']}): "
            f"{row['goals']} goals, {row['assists']} assists in {row['season']} season."
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
            f"FIXTURE - {row['home_team']} vs {row['away_team']} "
            f"ended {row['home_goals']}-{row['away_goals']} "
            f"({row['status']}) on {row['fixture_date'][:10]}."
        )
        chunks.append(text)
        ids.append(f"fixture_{row['fixture_id']}")
    
    return chunks, ids

def chunk_fixture_stats():
    # ROCKY: advanced stats for each team in each fixture
    df = pd.read_sql("SELECT * FROM fixture_stats", conn)
    
    chunks = []
    ids = []
    
    for i, row in df.iterrows():
        text = (
            f"In the match with fixture_id {row['fixture_id']}, {row['team_name']} "
            f"had {row['total_shots']} total shots, {row['shots_on_goal']} on target, "
            f"xG of {row['expected_goals']}, {row['possession']}% possession and "
            f"{row['accurate_passes']} accurate passes out of {row['total_passes']}."
        )
        chunks.append(text)
        ids.append(f"fixture_stats_{row['fixture_id']}_{row['team_name'].replace(' ', '_')}")
    
    return chunks, ids

def chunk_match_xg():
    # ROCKY: convert match xG data to human readable sentences
    # xG = expected goals, shows quality of chances created
    df = pd.read_sql("SELECT * FROM match_xg ORDER BY match_date DESC", conn)
    
    chunks = []
    ids = []
    
    for i, row in df.iterrows():
        # ROCKY: handle missing values gracefully
        home_xg = f"{row['home_xg']:.2f}" if row['home_xg'] else "N/A"
        away_xg = f"{row['away_xg']:.2f}" if row['away_xg'] else "N/A"
        home_goals = row['home_goals'] if row['home_goals'] is not None else "?"
        away_goals = row['away_goals'] if row['away_goals'] is not None else "?"
        
        # ROCKY: safely handle None team names
        home = str(row['home_team'] or 'unknown').replace(' ', '_')
        away = str(row['away_team'] or 'unknown').replace(' ', '_')
        
        text = (
            f"On {row['match_date']}, {row['home_team']} played {row['away_team']}. "
            f"The match ended {home_goals}-{away_goals}. "
            f"{row['home_team']} had an expected goals (xG) of {home_xg} and "
            f"{row['away_team']} had an xG of {away_xg}."
        )
        chunks.append(text)
        ids.append(f"match_xg_{row['match_date']}_{home}_vs_{away}")
    
    return chunks, ids

def chunk_player_xg():
    # ROCKY: convert player xG stats to readable sentences
    # individual player performance metrics including xG, xA, positions
    df = pd.read_sql("SELECT * FROM player_xg ORDER BY xg DESC", conn)
    
    chunks = []
    ids = []
    
    for i, row in df.iterrows():
        # ROCKY: handle missing/null values
        position = row['position'] if row['position'] else "Unknown"
        xg = f"{row['xg']:.2f}" if row['xg'] else "0.0"
        xa = f"{row['xa']:.2f}" if row['xa'] else "0.0"
        npxg = f"{row['npxg']:.2f}" if row['npxg'] else "0.0"
        
        # ROCKY: safely handle None player/team names
        player = str(row['player_name'] or 'unknown').replace(' ', '_')
        team = str(row['team_name'] or 'unknown').replace(' ', '_')
        
        # ROCKY: explicit compact format with full name at start for easy matching
        text = (
            f"PLAYER STATS - {row['player_name']} ({row['team_name']}, {position}): "
            f"{row['goals']} goals, {row['assists']} assists, xG: {xg}, xA: {xa}, "
            f"npxG: {npxg}, shots: {row['shots']}, key passes: {row['key_passes']}, "
            f"minutes: {row['minutes']} in {row['games']} games."
        )
        chunks.append(text)
        ids.append(f"player_xg_{player}_{team}")
    
    return chunks, ids

def store_in_chromadb(chunks, ids, label):
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
    
    print("processing fixtures...")
    chunks, ids = chunk_fixtures()
    store_in_chromadb(chunks, ids, "fixtures")
    
    print("processing fixture stats...")
    chunks, ids = chunk_fixture_stats()
    store_in_chromadb(chunks, ids, "fixture_stats")
    
    print("processing match xG...")
    chunks, ids = chunk_match_xg()
    store_in_chromadb(chunks, ids, "match_xg")
    
    print("processing player xG...")
    chunks, ids = chunk_player_xg()
    store_in_chromadb(chunks, ids, "player_xg")
    
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
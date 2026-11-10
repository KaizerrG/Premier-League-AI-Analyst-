"""
Fetch all data from Understat API and store in SQLite database.
Replaces both fetch_data.py (API-Football) and fetch_xg.py.

Data sources:
- League standings and team stats
- Player statistics (goals, assists, xG, xA, etc.)
- Match data (fixtures, goals, xG)
- Shot-level data
"""

import sqlite3
import pandas as pd
from datetime import datetime
from understat import Understat
import asyncio

# Configuration
LEAGUES = ["EPL", "La_Liga", "Bundesliga", "Serie_A", "Ligue_1"]
SEASON = "2026"  # 2024/25 season
DB_PATH = "pl_data.db"
BATCH_SIZE = 50

# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================

def init_database():
    """Create tables if they don't exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Standings table - team league statistics
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS standings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league TEXT NOT NULL,
            season TEXT NOT NULL,
            rank INTEGER,
            team_name TEXT UNIQUE,
            played INTEGER,
            won INTEGER,
            drawn INTEGER,
            lost INTEGER,
            goals_for INTEGER,
            goals_against INTEGER,
            goal_difference INTEGER,
            xg REAL,
            xga REAL,
            points INTEGER,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Fixtures table - match results with xG
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fixtures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league TEXT NOT NULL,
            season TEXT NOT NULL,
            fixture_id TEXT UNIQUE,
            home_team TEXT,
            away_team TEXT,
            home_goals INTEGER,
            away_goals INTEGER,
            home_xg REAL,
            away_xg REAL,
            home_win_prob REAL,
            draw_prob REAL,
            away_win_prob REAL,
            match_date TIMESTAMP,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Player xG statistics
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS player_xg (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league TEXT NOT NULL,
            season TEXT NOT NULL,
            player_name TEXT,
            team_name TEXT,
            position TEXT,
            games INTEGER,
            minutes INTEGER,
            goals INTEGER,
            assists INTEGER,
            xg REAL,
            xa REAL,
            npxg REAL,
            shots INTEGER,
            key_passes INTEGER,
            xgchain REAL,
            xgbuildup REAL,
            yellow_cards INTEGER,
            red_cards INTEGER,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(player_name, team_name, league, season)
        )
    """)
    
    # Match xG data (keep for compatibility or merge into fixtures)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS match_xg (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league TEXT NOT NULL,
            season TEXT NOT NULL,
            match_id TEXT UNIQUE,
            home_team TEXT,
            away_team TEXT,
            home_xg REAL,
            away_xg REAL,
            match_date TIMESTAMP,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Shot-level data
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league TEXT NOT NULL,
            season TEXT NOT NULL,
            player_name TEXT,
            team_name TEXT,
            x REAL,
            y REAL,
            xg REAL,
            result TEXT,
            match_id TEXT,
            minute INTEGER,
            situation TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Team stats (derived, for quick lookups)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league TEXT NOT NULL,
            season TEXT NOT NULL,
            team_name TEXT UNIQUE,
            xg_for REAL,
            xga REAL,
            xg_diff REAL,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()


def drop_obsolete_tables():
    """Remove tables no longer needed."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    tables_to_drop = ["fixture_stats", "top_scorers"]
    
    for table in tables_to_drop:
        try:
            cursor.execute(f"DROP TABLE IF EXISTS {table}")
            print(f"  ✓ Dropped {table} table")
        except Exception as e:
            print(f"  ✗ Error dropping {table}: {e}")
    
    conn.commit()
    conn.close()


# ============================================================================
# DATA FETCHING FROM UNDERSTAT
# ============================================================================

async def fetch_league_data(league: str):
    """
    Fetch all data for a single league from Understat.
    
    Args:
        league: League code (e.g., 'EPL', 'La_Liga', 'Bundesliga', 'Serie_A', 'Ligue_1')
    """
    print(f"\n📥 Fetching {league}...")
    
    try:
        async with Understat() as understat:
            league_obj = understat.league(league)
            
            # 1. Fetch team standings
            print(f"  → Teams and standings...")
            standings = await league_obj.get_team_data(SEASON)
            store_standings(standings, league)
            
            # 2. Fetch player statistics
            print(f"  → Player statistics...")
            players = await league_obj.get_player_data(SEASON)
            store_player_xg(players, league)
            
            # 3. Fetch match data
            print(f"  → Match fixtures...")
            matches = await league_obj.get_match_data(SEASON)
            store_fixtures(matches, league)
            store_match_xg(matches, league)
            
            # 4. Fetch shot data
            print(f"  → Shot data...")
            shots = await league_obj.get_shot_data(SEASON)
            store_shots(shots, league)
            
            print(f"  ✓ {league} complete")
            
    except Exception as e:
        print(f"  ✗ Error fetching {league}: {e}")


def store_standings(data: list, league: str):
    """Store team standings data."""
    if not data:
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Clear old data for this league
    cursor.execute("DELETE FROM standings WHERE league = ?", (league,))
    
    # Transform data and add rank based on points
    df = pd.DataFrame(data)
    df = df.sort_values('pts', ascending=False).reset_index(drop=True)
    df['rank'] = range(1, len(df) + 1)
    df['goal_difference'] = df['scored'] - df['missed']
    
    # Prepare for insertion
    records = []
    for _, row in df.iterrows():
        records.append((
            league,
            SEASON,
            int(row['rank']),
            row.get('team_name'),
            int(row.get('matches', 0)),
            int(row.get('wins', 0)),
            int(row.get('draws', 0)),
            int(row.get('losses', 0)),
            int(row.get('scored', 0)),
            int(row.get('missed', 0)),
            int(row.get('goal_difference', 0)),
            float(row.get('xG', 0)),
            float(row.get('xGA', 0)),
            int(row.get('pts', 0))
        ))
    
    # Batch insert
    insert_query = """
        INSERT INTO standings 
        (league, season, rank, team_name, played, won, drawn, lost, 
         goals_for, goals_against, goal_difference, xg, xga, points)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i:i+BATCH_SIZE]
        cursor.executemany(insert_query, batch)
        conn.commit()
    
    print(f"    ✓ Stored {len(records)} teams")
    conn.close()


def store_player_xg(data: list, league: str):
    """Store player statistics."""
    if not data:
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Clear old data
    cursor.execute("DELETE FROM player_xg WHERE league = ?", (league,))
    
    records = []
    for player in data:
        records.append((
            league,
            SEASON,
            player.get('player_name'),
            player.get('team_name'),
            player.get('position'),
            int(player.get('games', 0)),
            int(player.get('minutes', 0)),
            int(player.get('goals', 0)),
            int(player.get('assists', 0)),
            float(player.get('xG', 0)),
            float(player.get('xA', 0)),
            float(player.get('npxG', 0)),
            int(player.get('shots', 0)),
            int(player.get('key_passes', 0)),
            float(player.get('xGChain', 0)),
            float(player.get('xGBuildup', 0)),
            int(player.get('yellow_cards', 0)),
            int(player.get('red_cards', 0))
        ))
    
    insert_query = """
        INSERT INTO player_xg 
        (league, season, player_name, team_name, position, games, minutes, goals, assists,
         xg, xa, npxg, shots, key_passes, xgchain, xgbuildup, yellow_cards, red_cards)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i:i+BATCH_SIZE]
        cursor.executemany(insert_query, batch)
        conn.commit()
    
    print(f"    ✓ Stored {len(records)} players")
    conn.close()


def store_fixtures(data: list, league: str):
    """Store match fixtures with goals and xG."""
    if not data:
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM fixtures WHERE league = ?", (league,))
    
    records = []
    for match in data:
        records.append((
            league,
            SEASON,
            match.get('match_id'),
            match.get('home_team'),
            match.get('away_team'),
            int(match.get('goals_home', 0)),
            int(match.get('goals_away', 0)),
            float(match.get('xG_home', 0)),
            float(match.get('xG_away', 0)),
            float(match.get('home_win_prob', 0)),
            float(match.get('draw_prob', 0)),
            float(match.get('away_win_prob', 0)),
            match.get('match_date')
        ))
    
    insert_query = """
        INSERT INTO fixtures 
        (league, season, fixture_id, home_team, away_team, home_goals, away_goals,
         home_xg, away_xg, home_win_prob, draw_prob, away_win_prob, match_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i:i+BATCH_SIZE]
        cursor.executemany(insert_query, batch)
        conn.commit()
    
    print(f"    ✓ Stored {len(records)} fixtures")
    conn.close()


def store_match_xg(data: list, league: str):
    """Store match xG data (keep for compatibility)."""
    if not data:
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM match_xg WHERE league = ?", (league,))
    
    records = []
    for match in data:
        records.append((
            league,
            SEASON,
            match.get('match_id'),
            match.get('home_team'),
            match.get('away_team'),
            float(match.get('xG_home', 0)),
            float(match.get('xG_away', 0)),
            match.get('match_date')
        ))
    
    insert_query = """
        INSERT INTO match_xg 
        (league, season, match_id, home_team, away_team, home_xg, away_xg, match_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i:i+BATCH_SIZE]
        cursor.executemany(insert_query, batch)
        conn.commit()
    
    conn.close()


def store_shots(data: list, league: str):
    """Store shot-level data."""
    if not data:
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM shots WHERE league = ?", (league,))
    
    records = []
    for shot in data:
        records.append((
            league,
            SEASON,
            shot.get('player_name'),
            shot.get('team_name'),
            float(shot.get('x', 0)),
            float(shot.get('y', 0)),
            float(shot.get('xG', 0)),
            shot.get('result'),
            shot.get('match_id'),
            int(shot.get('minute', 0)),
            shot.get('situation'),
        ))
    
    insert_query = """
        INSERT INTO shots 
        (league, season, player_name, team_name, x, y, xg, result, match_id, minute, situation)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i:i+BATCH_SIZE]
        cursor.executemany(insert_query, batch)
        conn.commit()
    
    print(f"    ✓ Stored {len(records)} shots")
    conn.close()


# ============================================================================
# MAIN EXECUTION
# ============================================================================

async def main():
    """Main execution function."""
    print("🚀 Understat Data Fetch Pipeline")
    print(f"  Season: {SEASON}")
    print(f"  Leagues: {', '.join(LEAGUES)}\n")
    
    # Initialize database
    print("📦 Initializing database...")
    init_database()
    print("  ✓ Database tables ready")
    
    # Drop obsolete tables
    print("\n🗑️  Cleaning up old tables...")
    drop_obsolete_tables()
    
    # Fetch data for all leagues
    print("\n📡 Fetching data from Understat...")
    for league in LEAGUES:
        await fetch_league_data(league)
    
    print("\n✅ Data fetch complete!")
    print(f"  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    asyncio.run(main())

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
import json
import pandas as pd
from datetime import datetime
import aiohttp
from understat import Understat
import asyncio
import sys
from settings import DATABASE_PATH, SEASON

# Configuration
LEAGUES = [
    ("EPL", "Premier League"),
    ("La_Liga", "La Liga"),
    ("Bundesliga", "Bundesliga"),
    ("Serie_A", "Serie A"),
    ("Ligue_1", "Ligue 1"),
]
DB_PATH = str(DATABASE_PATH)
BATCH_SIZE = 50


def ensure_column(cursor, table: str, column: str, declaration: str):
    """Add a column when upgrading a database created by an older app version."""
    existing = {row[1] for row in cursor.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def migrate_standings_unique_key(cursor):
    """Replace the legacy team-only uniqueness rule with a league/season key."""
    for index in cursor.execute("PRAGMA index_list(standings)").fetchall():
        if not index[2]:
            continue
        columns = [row[2] for row in cursor.execute(f"PRAGMA index_info({index[1]})")]
        if columns not in (["team_name"], ["season", "team_name"]):
            continue

        cursor.execute("ALTER TABLE standings RENAME TO standings_legacy")
        cursor.execute("""
            CREATE TABLE standings_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                league TEXT NOT NULL,
                season TEXT NOT NULL,
                rank INTEGER,
                team_name TEXT,
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
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(team_name, league, season)
            )
        """)
        cursor.execute("""
            INSERT INTO standings_new
            SELECT id, league, season, rank, team_name, played, won, drawn, lost,
                   goals_for, goals_against, goal_difference, xg, xga, points, fetched_at
            FROM standings_legacy
        """)
        cursor.execute("DROP TABLE standings_legacy")
        cursor.execute("ALTER TABLE standings_new RENAME TO standings")
        break


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
            team_name TEXT,
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
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(team_name, league, season)
        )
    """)
    
    # Fixtures table - match results with xG
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fixtures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league TEXT NOT NULL,
            season TEXT NOT NULL,
            fixture_id TEXT,
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
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(fixture_id, league, season)
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
            match_id TEXT,
            home_team TEXT,
            away_team TEXT,
            home_xg REAL,
            away_xg REAL,
            match_date TIMESTAMP,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(match_id, league, season)
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

    # Upgrade databases created by the earlier API-Football/fetch_xg scripts.
    migrations = {
        "standings": {
            "league": "TEXT NOT NULL DEFAULT 'Premier League'",
            "xg": "REAL",
            "xga": "REAL",
        },
        "fixtures": {
            "league": "TEXT NOT NULL DEFAULT 'Premier League'",
            "home_xg": "REAL",
            "away_xg": "REAL",
            "home_win_prob": "REAL",
            "draw_prob": "REAL",
            "away_win_prob": "REAL",
            "match_date": "TEXT",
        },
        "player_xg": {
            "league": "TEXT NOT NULL DEFAULT 'Premier League'",
            "season": "TEXT NOT NULL DEFAULT '2024'",
            "npxg": "REAL",
            "xgchain": "REAL",
            "xgbuildup": "REAL",
            "yellow_cards": "INTEGER",
            "red_cards": "INTEGER",
        },
        "match_xg": {
            "league": "TEXT NOT NULL DEFAULT 'Premier League'",
            "season": "TEXT NOT NULL DEFAULT '2024'",
            "match_id": "TEXT",
        },
    }
    for table, columns in migrations.items():
        for column, declaration in columns.items():
            ensure_column(cursor, table, column, declaration)

    # Preserve dates when upgrading from a schema that used fixture_date.
    fixture_columns = {row[1] for row in cursor.execute("PRAGMA table_info(fixtures)")}
    if "fixture_date" in fixture_columns:
        cursor.execute("UPDATE fixtures SET match_date = fixture_date WHERE match_date IS NULL")

    migrate_standings_unique_key(cursor)
    
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

async def fetch_league_shots(understat, matches: list, league_name: str) -> list:
    """Fetch and normalize shot data for each completed match."""
    semaphore = asyncio.Semaphore(8)

    async def fetch_match(match):
        async with semaphore:
            try:
                shot_data = await understat.get_match_shots(match.get("id"))
            except Exception as exc:
                print(f"    ! Shots unavailable for match {match.get('id')}: {exc}")
                return []

        records = []
        for side in ("h", "a"):
            team = (match.get(side) or {}).get("title")
            for shot in (shot_data or {}).get(side, []):
                records.append({
                    "player_name": shot.get("player_name") or shot.get("player"),
                    "team_name": team,
                    "x": shot.get("x", shot.get("X", 0)),
                    "y": shot.get("y", shot.get("Y", 0)),
                    "xG": shot.get("xG", 0),
                    "result": shot.get("result"),
                    "match_id": match.get("id"),
                    "minute": shot.get("minute", 0),
                    "situation": shot.get("situation"),
                })
        return records

    batches = await asyncio.gather(*(fetch_match(match) for match in matches))
    return [shot for batch in batches for shot in batch]


async def fetch_league_data(league_code: str, league_name: str):
    """
    Fetch all data for a single league from Understat.
    
    Args:
        league_code: Understat API league code.
        league_name: Display name stored in the database.
    """
    print(f"\n📥 Fetching {league_name}...")
    
    try:
        async with aiohttp.ClientSession() as session:
            understat = Understat(session)

            print("  → Teams and standings...")
            table = await understat.get_league_table(league_code, SEASON, with_headers=False)
            standings = [
                {
                    "team_name": row[0], "matches": row[1], "wins": row[2],
                    "draws": row[3], "losses": row[4], "scored": row[5],
                    "missed": row[6], "pts": row[7], "xG": row[8], "xGA": row[10],
                }
                for row in table
            ]
            store_standings(standings, league_name)

            print("  → Player statistics...")
            players = await understat.get_league_players(league_code, SEASON)
            store_player_xg(players, league_name)

            print("  → Match fixtures and xG...")
            matches = await understat.get_league_results(league_code, SEASON)
            store_fixtures(matches, league_name)
            store_match_xg(matches, league_name)

            print("  → Shot data...")
            shots = await fetch_league_shots(understat, matches, league_name)
            store_shots(shots, league_name)

        print(f"  ✓ {league_name} complete")
        return True
            
    except Exception as e:
        if isinstance(e, json.JSONDecodeError):
            print(f"  ✗ Understat returned non-JSON content for {league_name}; the provider may be unavailable. Try again later.")
        else:
            print(f"  ✗ Error fetching {league_name}: {e}")
        return False


def store_standings(data: list, league: str):
    """Store team standings data."""
    if not data:
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Clear old data for this league
    cursor.execute("DELETE FROM standings WHERE league = ? AND season = ?", (league, SEASON))
    
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
    cursor.execute("DELETE FROM player_xg WHERE league = ? AND season = ?", (league, SEASON))
    
    records = []
    for player in data:
        records.append((
            league,
            SEASON,
            player.get('player_name'),
            player.get('team_name') or player.get('team_title'),
            player.get('position'),
            int(player.get('games', 0)),
            int(player.get('minutes', player.get('time', 0)) or 0),
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


def normalize_match(match: dict) -> dict:
    """Convert Understat's nested match record into the database field names."""
    home = match.get("h") or {}
    away = match.get("a") or {}
    goals = match.get("goals") or {}
    xg = match.get("xG") or {}
    forecast = match.get("forecast") or {}
    return {
        "match_id": match.get("id") or match.get("match_id"),
        "home_team": home.get("title") or match.get("home_team"),
        "away_team": away.get("title") or match.get("away_team"),
        "home_goals": goals.get("h", match.get("home_goals", 0)),
        "away_goals": goals.get("a", match.get("away_goals", 0)),
        "home_xg": xg.get("h", match.get("xG_home", 0)),
        "away_xg": xg.get("a", match.get("xG_away", 0)),
        "home_win_prob": forecast.get("w", match.get("home_win_prob", 0)),
        "draw_prob": forecast.get("d", match.get("draw_prob", 0)),
        "away_win_prob": forecast.get("l", match.get("away_win_prob", 0)),
        "match_date": match.get("datetime") or match.get("match_date"),
    }


def store_fixtures(data: list, league: str):
    """Store match fixtures with goals and xG."""
    if not data:
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM fixtures WHERE league = ? AND season = ?", (league, SEASON))
    
    records = []
    for match in data:
        match = normalize_match(match)
        records.append((
            league,
            SEASON,
            match.get('match_id'),
            match.get('home_team'),
            match.get('away_team'),
            int(match.get('home_goals') or 0),
            int(match.get('away_goals') or 0),
            float(match.get('home_xg') or 0),
            float(match.get('away_xg') or 0),
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
    
    cursor.execute("DELETE FROM match_xg WHERE league = ? AND season = ?", (league, SEASON))
    
    records = []
    for match in data:
        match = normalize_match(match)
        records.append((
            league,
            SEASON,
            match.get('match_id'),
            match.get('home_team'),
            match.get('away_team'),
            float(match.get('home_xg') or 0),
            float(match.get('away_xg') or 0),
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
    
    cursor.execute("DELETE FROM shots WHERE league = ? AND season = ?", (league, SEASON))
    
    records = []
    for shot in data:
        records.append((
            league,
            SEASON,
            shot.get('player_name') or shot.get('player'),
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
    print(f"  Leagues: {', '.join(name for _, name in LEAGUES)}\n")
    
    # Initialize database
    print("📦 Initializing database...")
    init_database()
    print("  ✓ Database tables ready")
    
    # Fetch data for all leagues
    print("\n📡 Fetching data from Understat...")
    failures = []
    for league_code, league_name in LEAGUES:
        if not await fetch_league_data(league_code, league_name):
            failures.append(league_name)
    
    if failures:
        raise RuntimeError(f"Data fetch failed for: {', '.join(failures)}")

    print("\n✅ Data fetch complete!")
    print(f"  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    asyncio.run(main())

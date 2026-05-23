import asyncio
import aiohttp
import sqlite3
import logging
from datetime import datetime
from understat import Understat
from typing import Optional, Dict, Any

# ROCKY: logging setup so you see what's happening
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("fetch_xg.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

SEASON = 2024
LEAGUE = "EPL"
TIMEOUT = 30


def clean_position(pos: Optional[str]) -> str:
    """ROCKY: clean player position from API format"""
    if not pos:
        return "Unknown"
    
    pos = pos.strip()
    
    if "G" in pos:
        return "Goalkeeper"
    if pos == "D" or pos == "D S":
        return "Defender"
    if pos == "M" or pos == "M S":
        return "Midfielder"
    if pos == "F" or pos == "F S":
        return "Forward"
    if "D" in pos and "M" in pos:
        return "Defensive Midfielder"
    if "F" in pos and "M" in pos:
        return "Attacking Midfielder"
    if "D" in pos:
        return "Defender"
    return "Unknown"


def init_xg_database():
    """ROCKY: create tables for xG data if they don't exist"""
    try:
        conn = sqlite3.connect("pl_data.db")
        cursor = conn.cursor()

        # ROCKY: match_xg = all matches with their expected goals
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS match_xg (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                home_team TEXT,
                away_team TEXT,
                home_xg REAL,
                away_xg REAL,
                home_goals INTEGER,
                away_goals INTEGER,
                match_date TEXT,
                home_win_prob REAL,
                draw_prob REAL,
                away_win_prob REAL,
                season INTEGER,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(home_team, away_team, match_date)
            )
        """)

        # ROCKY: player_xg = individual player xG stats
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS player_xg (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_name TEXT,
                team_name TEXT,
                position TEXT,
                games INTEGER,
                minutes INTEGER,
                goals INTEGER,
                assists INTEGER,
                xg REAL,
                xa REAL,
                shots INTEGER,
                key_passes INTEGER,
                npg INTEGER,
                npxg REAL,
                xgchain REAL,
                xgbuildup REAL,
                yellow_cards INTEGER,
                red_cards INTEGER,
                season INTEGER,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(player_name, season)
            )
        """)

        conn.commit()
        logger.info("✓ xG tables initialized")
        return conn
    except Exception as e:
        logger.error(f"✗ failed to init database: {e}")
        raise


async def fetch_match_xg(session: aiohttp.ClientSession, understat_client: Understat):
    """ROCKY: fetch all match xG data for the season"""
    try:
        logger.info(f"fetching {LEAGUE} {SEASON} match xG data...")
        
        # ROCKY: get_league_results returns all matches with xG stats
        matches = await understat_client.get_league_results(LEAGUE, SEASON)
        
        logger.info(f"✓ fetched {len(matches)} matches")
        return matches
    except Exception as e:
        logger.error(f"✗ failed to fetch match xG: {e}")
        return []


async def fetch_player_xg(session: aiohttp.ClientSession, understat_client: Understat):
    """ROCKY: fetch all player xG data for the season"""
    try:
        logger.info(f"fetching {LEAGUE} {SEASON} player xG data...")
        
        # ROCKY: get_league_players returns all players with xG stats
        players = await understat_client.get_league_players(LEAGUE, SEASON)
        
        logger.info(f"✓ fetched {len(players)} players")
        return players
    except Exception as e:
        logger.error(f"✗ failed to fetch player xG: {e}")
        return []


def save_match_xg(conn: sqlite3.Connection, matches: list):
    """ROCKY: save match xG data to SQLite with INSERT OR REPLACE"""
    cursor = conn.cursor()
    saved = 0
    failed = 0
    
    for match in matches:
        try:
            # ROCKY: extract from actual understat API structure
            # "h" = home, "a" = away
            home_team = match.get("h", {}).get("title")
            away_team = match.get("a", {}).get("title")
            
            # ROCKY: xG is nested under "xG" key
            xg_data = match.get("xG", {})
            home_xg = float(xg_data.get("h")) if xg_data.get("h") else None
            away_xg = float(xg_data.get("a")) if xg_data.get("a") else None
            
            # ROCKY: goals nested under "goals" key
            goals_data = match.get("goals", {})
            home_goals = int(goals_data.get("h")) if goals_data.get("h") else None
            away_goals = int(goals_data.get("a")) if goals_data.get("a") else None
            
            # ROCKY: match datetime
            match_date = match.get("datetime")
            
            # ROCKY: forecast probabilities: w=win, d=draw, l=loss
            forecast_data = match.get("forecast", {})
            home_win_prob = float(forecast_data.get("w")) if forecast_data.get("w") else None
            draw_prob = float(forecast_data.get("d")) if forecast_data.get("d") else None
            away_win_prob = float(forecast_data.get("l")) if forecast_data.get("l") else None
            
            # ROCKY: INSERT OR REPLACE = upsert (update if exists, insert if not)
            cursor.execute("""
                INSERT OR REPLACE INTO match_xg 
                (home_team, away_team, home_xg, away_xg, home_goals, away_goals, 
                 match_date, home_win_prob, draw_prob, away_win_prob, season)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (home_team, away_team, home_xg, away_xg, home_goals, away_goals,
                  match_date, home_win_prob, draw_prob, away_win_prob, SEASON))
            
            saved += 1
        except Exception as e:
            failed += 1
            home = match.get("h", {}).get("title", "Unknown")
            away = match.get("a", {}).get("title", "Unknown")
            logger.warning(f"  skipped match {home} vs {away}: {e}")
    
    conn.commit()
    logger.info(f"✓ saved {saved} matches ({failed} skipped)")


def save_player_xg(conn: sqlite3.Connection, players: list):
    """ROCKY: save player xG data to SQLite with INSERT OR REPLACE"""
    cursor = conn.cursor()
    saved = 0
    failed = 0
    
    for player in players:
        try:
            # ROCKY: safely extract values with defaults
            player_name = player.get("player_name") or player.get("name")
            team_name = player.get("team_title")
            position = clean_position(player.get("position"))
            games = int(player.get("games", 0)) if player.get("games") else 0
            minutes = int(player.get("minutes", 0)) if player.get("minutes") else 0
            goals = int(player.get("goals", 0)) if player.get("goals") else 0
            assists = int(player.get("assists", 0)) if player.get("assists") else 0
            xg = float(player.get("xG", 0)) if player.get("xG") else 0
            xa = float(player.get("xA", 0)) if player.get("xA") else 0
            shots = int(player.get("shots", 0)) if player.get("shots") else 0
            key_passes = int(player.get("key_passes", 0)) if player.get("key_passes") else 0
            npg = int(player.get("npg", 0)) if player.get("npg") else 0
            npxg = float(player.get("npxG", 0)) if player.get("npxG") else 0
            xgchain = float(player.get("xGChain", 0)) if player.get("xGChain") else 0
            xgbuildup = float(player.get("xGBuildup", 0)) if player.get("xGBuildup") else 0
            yellow_cards = int(player.get("yellow_cards", 0)) if player.get("yellow_cards") else 0
            red_cards = int(player.get("red_cards", 0)) if player.get("red_cards") else 0
            
            # ROCKY: INSERT OR REPLACE upsert
            cursor.execute("""
                INSERT OR REPLACE INTO player_xg
                (player_name, team_name, position, games, minutes, goals, assists, xg, xa,
                 shots, key_passes, npg, npxg, xgchain, xgbuildup, yellow_cards, red_cards, season)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (player_name, team_name, position, games, minutes, goals, assists, xg, xa,
                  shots, key_passes, npg, npxg, xgchain, xgbuildup, yellow_cards, red_cards, SEASON))
            
            saved += 1
        except Exception as e:
            failed += 1
            logger.warning(f"  skipped player {player.get('player_name')}: {e}")
    
    conn.commit()
    logger.info(f"✓ saved {saved} players ({failed} skipped)")


async def main():
    """ROCKY: async main function - fetch and save all xG data"""
    logger.info(f"starting xG fetch for {LEAGUE} {SEASON}...")
    
    # ROCKY: init database tables
    conn = init_xg_database()
    
    # ROCKY: create async http session for understat
    async with aiohttp.ClientSession() as session:
        # ROCKY: create understat client (does auth and api calls)
        understat = Understat(session)
        
        try:
            # ROCKY: fetch both datasets
            matches = await fetch_match_xg(session, understat)
            players = await fetch_player_xg(session, understat)
            
            # ROCKY: save to SQLite
            if matches:
                save_match_xg(conn, matches)
            
            if players:
                save_player_xg(conn, players)
            
            logger.info("✓ all xG data saved successfully")
            
        except Exception as e:
            logger.error(f"✗ fatal error: {e}")
            raise
        finally:
            conn.close()


if __name__ == "__main__":
    # ROCKY: asyncio.run() = main function for async code
    asyncio.run(main())

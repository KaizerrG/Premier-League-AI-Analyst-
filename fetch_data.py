import requests
import os
import sqlite3
import json
import logging
import time
from dotenv import load_dotenv
from typing import Optional, Dict, Any

# ROCKY: load .env file so python can read your API key safely
load_dotenv()

API_KEY = os.getenv("API_FOOTBALL_KEY")
if not API_KEY:
    raise ValueError("API_FOOTBALL_KEY not found in .env file")

# ROCKY: season and flags come from .env too so you can change without touching code
SEASON = int(os.getenv("SEASON", "2024"))
FETCH_TEAM_STATS = os.getenv("FETCH_TEAM_STATS", "false").lower() == "true"

headers = {"x-apisports-key": API_KEY}
BASE_URL = "https://v3.football.api-sports.io"
TIMEOUT = 10

# ROCKY: logging = your program talking to you
# it write to a file AND prints to terminal at same time
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("fetch_data.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def init_database():
    # ROCKY: create sqlite database file on your machine
    # CREATE TABLE IF NOT EXISTS = only make table if not already there
    # UNIQUE(...) = no duplicate rows for same season + team
    try:
        conn = sqlite3.connect("pl_data.db")
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS standings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                season INTEGER,
                rank INTEGER,
                team_name TEXT,
                played INTEGER,
                won INTEGER,
                drawn INTEGER,
                lost INTEGER,
                goals_for INTEGER,
                goals_against INTEGER,
                goal_difference INTEGER,
                points INTEGER,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(season, team_name)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS top_scorers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                season INTEGER,
                player_name TEXT,
                team_name TEXT,
                goals INTEGER,
                assists INTEGER,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(season, player_name)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fixtures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                season INTEGER,
                fixture_id INTEGER,
                home_team TEXT,
                away_team TEXT,
                status TEXT,
                home_goals INTEGER,
                away_goals INTEGER,
                fixture_date TIMESTAMP,
                gameweek INTEGER,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(season, fixture_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS team_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                season INTEGER,
                team_name TEXT,
                played INTEGER,
                wins INTEGER,
                draws INTEGER,
                losses INTEGER,
                goals_for INTEGER,
                goals_against INTEGER,
                goal_difference INTEGER,
                clean_sheets INTEGER,
                failed_to_score INTEGER,
                penalty_scored INTEGER,
                penalty_missed INTEGER,
                yellow_cards INTEGER,
                red_cards INTEGER,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(season, team_name)
            )
        """)

        conn.commit()
        logger.info(f"database ready for season {SEASON}")
        return conn
    except Exception as e:
        logger.error(f"database init failed: {e}")
        raise


def fetch_with_retry(url: str) -> Optional[Dict[str, Any]]:
    # ROCKY: this is the most important function
    # it call the API. if API say "too many requests" (429)
    # it WAIT and try again. wait time doubles each time = exponential backoff
    # this stop you from getting banned by API
    max_wait = 60
    wait_time = 1

    while wait_time <= max_wait:
        try:
            res = requests.get(url, headers=headers, timeout=TIMEOUT)

            if res.status_code == 429:
                # ROCKY: 429 = API saying slow down. we wait and retry
                logger.warning(f"rate limited. waiting {wait_time}s...")
                time.sleep(wait_time)
                wait_time *= 2
                continue

            if res.status_code != 200:
                logger.error(f"HTTP error {res.status_code}")
                return None

            data = res.json()

            if "response" not in data:
                logger.error("no response key in API data")
                return None

            logger.info(f"fetch success")
            return data

        except requests.exceptions.Timeout:
            logger.error("request timed out")
            return None
        except Exception as e:
            logger.error(f"unexpected error: {e}")
            return None

    return None


def fetch_standings():
    # ROCKY: league=39 is Premier League. season=2024 is 2024/25 season
    import json
    url = f"{BASE_URL}/standings?league=39&season={SEASON}"
    return fetch_with_retry(url)


def fetch_top_scorers():
    url = f"{BASE_URL}/players/topscorers?league=39&season={SEASON}"
    return fetch_with_retry(url)


def fetch_fixtures():
    # ROCKY: fetch all Premier League fixtures for the season
    url = f"{BASE_URL}/fixtures?league=39&season={SEASON}"
    return fetch_with_retry(url)


def fetch_team_stats(team_id: int):
    url = f"{BASE_URL}/teams/statistics?league=39&season={SEASON}&team={team_id}"
    return fetch_with_retry(url)


def save_standings(conn, data):
    # ROCKY: INSERT OR REPLACE = if row exist update it. if not create it.
    # this mean you can run script every day and data stay fresh
    try:
        cursor = conn.cursor()
        standings_list = data["response"][0]["league"]["standings"][0]

        for team in standings_list:
            cursor.execute("""
                INSERT OR REPLACE INTO standings 
                (season, rank, team_name, played, won, drawn, lost, 
                 goals_for, goals_against, goal_difference, points)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                SEASON,
                team["rank"],
                team["team"]["name"],
                team["all"]["played"],
                team["all"]["win"],
                team["all"]["draw"],
                team["all"]["lose"],
                team["all"]["goals"]["for"],
                team["all"]["goals"]["against"],
                team["goalsDiff"],
                team["points"]
            ))

        conn.commit()
        logger.info(f"saved {len(standings_list)} teams to standings")
    except Exception as e:
        logger.error(f"save standings failed: {e}")
        raise


def save_top_scorers(conn, data):
    try:
        cursor = conn.cursor()
        scorers = data["response"]

        for scorer in scorers:
            cursor.execute("""
                INSERT OR REPLACE INTO top_scorers 
                (season, player_name, team_name, goals, assists)
                VALUES (?, ?, ?, ?, ?)
            """, (
                SEASON,
                scorer["player"]["name"],
                scorer["statistics"][0]["team"]["name"],
                scorer["statistics"][0]["goals"]["total"],
                scorer["statistics"][0]["goals"]["assists"] or 0
            ))

        conn.commit()
        logger.info(f"saved {len(scorers)} scorers")
    except Exception as e:
        logger.error(f"save scorers failed: {e}")


def save_fixtures(conn, data):
    try:
        cursor = conn.cursor()
        fixtures = data["response"]

        for fixture in fixtures:
            cursor.execute("""
                INSERT OR REPLACE INTO fixtures 
                (season, fixture_id, home_team, away_team, status, 
                 home_goals, away_goals, fixture_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                SEASON,
                fixture["fixture"]["id"],
                fixture["teams"]["home"]["name"],
                fixture["teams"]["away"]["name"],
                fixture["fixture"]["status"]["long"],
                fixture["goals"]["home"],
                fixture["goals"]["away"],
                fixture["fixture"]["date"]
            ))

        conn.commit()
        logger.info(f"saved {len(fixtures)} fixtures")
    except Exception as e:
        logger.error(f"save fixtures failed: {e}")


def save_team_stats(conn, data):
    try:
        cursor = conn.cursor()
        stats = data["response"]

        fixtures = stats["fixtures"]
        played = fixtures["played"]["total"]
        wins = fixtures["wins"]["total"]
        draws = fixtures["draws"]["total"]
        losses = fixtures["loses"]["total"]

        goals_for = stats["goals"]["for"]["total"]["total"]
        goals_against = stats["goals"]["against"]["total"]["total"]
        goal_diff = goals_for - goals_against

        # ROCKY: FIX. penalty is nested dict. need ["total"] at end
        penalty_scored = stats["penalty"]["scored"]["total"] or 0
        penalty_missed = stats["penalty"]["missed"]["total"] or 0

        # ROCKY: FIX. cards nested by time range. sum all ranges together
        yellow = sum(
            v["total"] or 0
            for v in stats["cards"]["yellow"].values()
            if isinstance(v, dict)
        )
        red = sum(
            v["total"] or 0
            for v in stats["cards"]["red"].values()
            if isinstance(v, dict)
        )

        cursor.execute("""
            INSERT OR REPLACE INTO team_stats 
            (season, team_name, played, wins, draws, losses, goals_for, goals_against,
             goal_difference, clean_sheets, failed_to_score, penalty_scored, 
             penalty_missed, yellow_cards, red_cards)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            SEASON,
            stats["team"]["name"],
            played, wins, draws, losses,
            goals_for, goals_against, goal_diff,
            stats["clean_sheet"]["total"],
            stats["failed_to_score"]["total"],
            penalty_scored, penalty_missed,
            yellow, red
        ))

        conn.commit()
        logger.info(f"saved team stats for {stats['team']['name']}")
    except Exception as e:
        logger.error(f"save team stats failed: {e}")


def main():
    logger.info("=" * 50)
    logger.info(f"fetching PL data for season {SEASON}")
    logger.info("=" * 50)

    try:
        # ROCKY: conn = connection to database. like opening a door to your data
        conn = init_database()

        logger.info("fetching standings...")
        standings_data = fetch_standings()
        if standings_data:
            save_standings(conn, standings_data)
            team_ids = {
                team["team"]["id"]: team["team"]["name"]
                for team in standings_data["response"][0]["league"]["standings"][0]
            }
        else:
            team_ids = {}

        logger.info("fetching top scorers...")
        scorers_data = fetch_top_scorers()
        if scorers_data:
            save_top_scorers(conn, scorers_data)

        logger.info("fetching fixtures...")
        fixtures_data = fetch_fixtures()
        if fixtures_data:
            save_fixtures(conn, fixtures_data)

        # ROCKY: team stats disabled by default. uses too many API calls (20 teams = 20 calls)
        # to enable: add FETCH_TEAM_STATS=true in your .env file
        if FETCH_TEAM_STATS and team_ids:
            logger.info(f"fetching team stats for {len(team_ids)} teams...")
            for team_id, team_name in team_ids.items():
                logger.info(f"fetching {team_name}...")
                team_stats = fetch_team_stats(team_id)
                if team_stats:
                    save_team_stats(conn, team_stats)

        conn.close()
        logger.info("ALL DONE. data saved to pl_data.db")

    except Exception as e:
        logger.error(f"fatal error: {e}")
        raise


if __name__ == "__main__":
    main()

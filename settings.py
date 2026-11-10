"""Shared, platform-independent project settings."""

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

_database_value = os.getenv("PL_DATA_DB", "pl_data.db")
DATABASE_PATH = Path(_database_value).expanduser()
if not DATABASE_PATH.is_absolute():
    DATABASE_PATH = PROJECT_ROOT / DATABASE_PATH

# Understat identifies a season by its starting year (2024 means 2024/25).
SEASON = os.getenv("PL_SEASON", os.getenv("SEASON", "2024")).strip() or "2024"
if not SEASON.isdigit() or len(SEASON) != 4:
    raise ValueError("PL_SEASON must be a four-digit starting year, such as 2024.")
SEASON_LABEL = f"{SEASON}/{(int(SEASON) + 1) % 100:02d}"

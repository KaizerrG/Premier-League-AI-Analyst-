# Premier League Data Fetcher

Fetches Premier League data from the API-Football service and stores it in SQLite.

## Features

✅ **Multi-season support** - Fetch data for any season  
✅ **Comprehensive metrics** - Standings, top scorers, fixtures, team stats  
✅ **Exponential backoff** - Handles API rate limiting gracefully  
✅ **Logging** - Console + file logging to `fetch_data.log`  
✅ **Error handling** - Robust error handling for network issues  

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Create .env with your API key
echo "API_FOOTBALL_KEY=your_key_here" > .env
```

## Usage

### Basic Usage (Current Season)
```bash
SEASON=2024 python fetch_data.py
```

### Different Seasons
```bash
SEASON=2023 python fetch_data.py
SEASON=2022 python fetch_data.py
```

### With Advanced Team Stats (Optional - triggers more API calls)
```bash
SEASON=2024 FETCH_TEAM_STATS=true python fetch_data.py
```

## Database Schema

### `standings` table
- `season`, `rank`, `team_name`, `played`, `won`, `drawn`, `lost`
- `goals_for`, `goals_against`, `goal_difference`, `points`

### `top_scorers` table
- `season`, `player_name`, `team_name`, `goals`, `assists`

### `fixtures` table
- `season`, `fixture_id`, `home_team`, `away_team`, `status`
- `home_goals`, `away_goals`, `fixture_date`

### `team_stats` table (Advanced Metrics)
- `season`, `team_name`, `played`, `wins`, `draws`, `losses`
- `goals_for`, `goals_against`, `goal_difference`, `clean_sheets`
- `failed_to_score`, `penalty_scored`, `penalty_missed`
- `yellow_cards`, `red_cards`

## Rate Limiting

The API has rate limits. The script handles this with:
- ✅ **Exponential backoff** - Waits 1s, then 2s, 4s, 8s... up to 60s
- ✅ **Graceful degradation** - Skips team stats if rate limited (they're optional)
- ✅ **Auto-retry** - Automatically retries on 429 responses

### Tips to Avoid Rate Limiting
1. Disable team stats fetching (enabled by default) - `FETCH_TEAM_STATS=false`
2. Run during off-peak hours
3. Use a higher API tier for more requests

## Example Queries

```sql
-- Top 5 teams by points
SELECT team_name, points FROM standings 
WHERE season = 2024 
ORDER BY points DESC LIMIT 5;

-- Top scorers
SELECT player_name, team_name, goals FROM top_scorers 
WHERE season = 2024 
ORDER BY goals DESC LIMIT 10;

-- Team stats for a season
SELECT team_name, played, wins, draws, losses, goal_difference 
FROM team_stats 
WHERE season = 2024 
ORDER BY wins DESC;
```

## Logs

All activity is logged to `fetch_data.log`:
```
2026-04-21 02:49:29,042 - INFO - Starting PL data fetch for Season 2024...
2026-04-21 02:49:29,786 - INFO - ✓ Fetched standings...
2026-04-21 02:49:30,758 - INFO - ✓ Fetched top scorers...
```

## Troubleshooting

**"API_FOOTBALL_KEY not found in .env"**
- Create `.env` file in the script directory with your API key

**"Rate limited. Waiting..."**
- The script will automatically retry with exponential backoff
- Consider disabling `FETCH_TEAM_STATS` to reduce API calls

**Database locked error**
- Ensure no other process is accessing `pl_data.db`
- Close any database viewers

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SEASON` | 2024 | Premier League season to fetch |
| `FETCH_TEAM_STATS` | false | Fetch advanced team statistics (more API calls) |
| `API_FOOTBALL_KEY` | - | Your API Football key (required) |

## Advanced Metrics Available (with FETCH_TEAM_STATS=true)

When enabled, fetches detailed stats including:
- Clean sheets, failed to score streaks
- Penalty conversion rates
- Card distributions (yellows/reds)
- Goals scored by time period
- Under/over performance metrics

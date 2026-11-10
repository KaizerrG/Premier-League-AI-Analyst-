"""
Premier League 2024/25 Analytics Dashboard using Streamlit and Plotly.

This module creates an interactive dashboard with multiple tabs:
1. League Table - Standings with color coding and points visualization
2. xG Analysis - Expected goals analysis and efficiency metrics
3. Top Scorers & Playmakers - Individual player rankings with filtering
4. Player Comparison - Head-to-head radar chart comparison

Data source: pl_data.db (SQLite)
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import sqlite3
import pandas as pd
from typing import Tuple, Optional

# ============================================================================
# DATABASE UTILITY FUNCTIONS
# ============================================================================
# NOTE: No cached DB connection. Each loader function opens/closes
# its own SQLite connection with `check_same_thread=False` to avoid
# cross-thread SQLite issues in Streamlit.

@st.cache_data
def load_standings(league: str) -> Optional[pd.DataFrame]:
    """
    Load league standings table from database filtered by league.
    Since standings table doesn't have league column, we filter by teams
    that belong to the selected league (determined from match_xg table).
    
    Args:
        league: League display name (e.g., 'Premier League', 'La Liga', etc.)
    
    Returns:
        pd.DataFrame: Standings data with columns [rank, team_name, played, won, drawn, lost, points, goals_for, goals_against, goal_difference]
        None if query fails
    """
    try:
        conn = sqlite3.connect("pl_data.db", check_same_thread=False)
        
        # Get all teams for this league from match_xg table
        teams_query = f"SELECT DISTINCT home_team FROM match_xg WHERE league = ?"
        teams_df = pd.read_sql_query(teams_query, conn, params=(league,))
        
        if teams_df.empty:
            st.warning(f"No teams found for {league}")
            conn.close()
            return None
        
        teams_list = teams_df['home_team'].tolist()
        placeholders = ','.join(['?' for _ in teams_list])
        
        # Load standings filtered by teams in this league
        query = f"""SELECT rank, team_name, played, won, drawn, lost, points, 
                          goals_for, goals_against, goal_difference 
                   FROM standings 
                   WHERE team_name IN ({placeholders})
                   ORDER BY rank"""
        df = pd.read_sql_query(query, conn, params=teams_list)
        conn.close()

        if df.empty:
            st.warning(f"No standings data available for {league}")
            return None
        
        return df
    
    except Exception as e:
        st.error(f"Error loading standings: {str(e)}")
        return None


@st.cache_data
def load_match_xg(league: str) -> Optional[pd.DataFrame]:
    """
    Load match xG data from database filtered by league.
    
    Args:
        league: League name (e.g., 'Premier League', 'La Liga', 'Bundesliga', 'Serie A', 'Ligue 1')
    
    Returns:
        pd.DataFrame: Match xG data with columns [home_team, away_team, home_xg, away_xg, match_date]
        None if query fails
    """
    try:
        conn = sqlite3.connect("pl_data.db", check_same_thread=False)
        query = "SELECT home_team, away_team, home_xg, away_xg, match_date FROM match_xg WHERE league = ?"
        df = pd.read_sql_query(query, conn, params=(league,))
        conn.close()
        
        if df.empty:
            st.warning(f"No match xG data available for {league}")
            return None
        
        return df
    
    except Exception as e:
        st.error(f"Error loading match xG: {str(e)}")
        return None


@st.cache_data
def load_fixtures(league: str) -> Optional[pd.DataFrame]:
    """
    Load fixture data (actual goals) from database filtered by league.
    
    Args:
        league: League name (e.g., 'Premier League', 'La Liga', 'Bundesliga', 'Serie A', 'Ligue 1')
    
    Returns:
        pd.DataFrame: Fixture data with columns [home_team, away_team, goals_home, goals_away, fixture_date]
        None if query fails
    """
    try:
        conn = sqlite3.connect("pl_data.db", check_same_thread=False)
        query = "SELECT home_team, away_team, home_goals, away_goals, fixture_date FROM fixtures WHERE league = ?"
        df = pd.read_sql_query(query, conn, params=(league,))
        conn.close()
        
        if df.empty:
            st.warning(f"No fixture data available for {league}")
            return None
        
        return df
    
    except Exception as e:
        st.error(f"Error loading fixtures: {str(e)}")
        return None


@st.cache_data
def load_player_xg(league: str) -> Optional[pd.DataFrame]:
    """
    Load player xG statistics from database filtered by league.
    
    Args:
        league: League name (e.g., 'Premier League', 'La Liga', 'Bundesliga', 'Serie A', 'Ligue 1')
    
    Returns:
        pd.DataFrame: Player xG data with all available columns
        None if query fails
    """
    try:
        conn = sqlite3.connect("pl_data.db", check_same_thread=False)
        query = """SELECT player_name, team_name, position, games, minutes, goals, 
                          assists, xg, xa, npxg, shots, key_passes, xgchain, xgbuildup
                   FROM player_xg
                   WHERE league = ?"""
        df = pd.read_sql_query(query, conn, params=(league,))
        conn.close()
        
        if df.empty:
            st.warning(f"No player xG data available for {league}")
            return None
        
        return df
    
    except Exception as e:
        st.error(f"Error loading player xG: {str(e)}")
        return None


# ============================================================================
# TAB 1: LEAGUE TABLE
# ============================================================================

def tab_league_table(league: str):
    """
    Display league standings with FotMob-style formatting.
    
    Features:
    - Dark background
    - Colored left border for top 4 (green) and relegation zone (red)
    - Columns: #, Team, PL, W, D, L, +/-, GD, PTS
    
    Args:
        league: League name (e.g., 'Premier League', 'La Liga', 'Bundesliga', 'Serie A', 'Ligue 1')
    """
    st.header("📊 League Table")
    
    # Load standings data
    standings_df = load_standings(league)
    
    if standings_df is None or standings_df.empty:
        st.error("Unable to load standings data")
        return
    
    # Helper function to get border color based on position
    def get_border_color(rank):
        """Get left border color based on league position."""
        if rank <= 4:
            return "#22C55E"  # Green - Champions League
        elif rank >= len(standings_df) - 3:
            return "#EF4444"  # Red - Relegation zone
        else:
            return "#6B7280"  # Gray - Mid-table
    
    # Create styled table display
    st.markdown("### Final Standings")
    
    # Display header
    header_html = """
    <div style="display: grid; grid-template-columns: 30px 150px 35px 35px 35px 35px 35px 35px 35px; 
                gap: 8px; padding: 12px; background-color: #1F2937; border-radius: 5px; margin-bottom: 5px; font-weight: bold; color: white;">
        <div>#</div>
        <div>Team</div>
        <div>PL</div>
        <div>W</div>
        <div>D</div>
        <div>L</div>
        <div>+/-</div>
        <div>GD</div>
        <div>PTS</div>
    </div>
    """
    st.markdown(header_html, unsafe_allow_html=True)
    
    # Display each team row
    for idx, row in standings_df.iterrows():
        rank = int(row['rank'])
        team_name = row['team_name']
        played = int(row['played'])
        won = int(row['won'])
        drawn = int(row['drawn'])
        lost = int(row['lost'])
        goals_for = int(row['goals_for'])
        goals_against = int(row['goals_against'])
        goal_diff = int(row['goal_difference'])
        points = int(row['points'])
        
        border_color = get_border_color(rank)
        
        # Determine row background color (alternate for readability)
        bg_color = "#111827" if idx % 2 == 0 else "#1F2937"
        
        row_html = f"""
        <div style="display: grid; grid-template-columns: 30px 150px 35px 35px 35px 35px 35px 35px 35px;
                    gap: 8px; padding: 12px; background-color: {bg_color}; border-left: 4px solid {border_color}; 
                    border-radius: 3px; margin-bottom: 3px; color: white; align-items: center;">
            <div><strong>{rank}</strong></div>
            <div style="font-weight: 500;">{team_name}</div>
            <div>{played}</div>
            <div style="color: #22C55E; font-weight: bold;">{won}</div>
            <div style="color: #9CA3AF; font-weight: bold;">{drawn}</div>
            <div style="color: #EF4444; font-weight: bold;">{lost}</div>
            <div>{goals_for}-{goals_against}</div>
            <div style="font-weight: bold;">{goal_diff:+d}</div>
            <div style="font-weight: bold; font-size: 14px;">{points}</div>
        </div>
        """
        
        st.markdown(row_html, unsafe_allow_html=True)
    
    # Add legend
    st.markdown("---")
    st.markdown("""
    **Legend:**
    - 🟩 Green border: Champions League qualification (Top 4)
    - 🟥 Red border: Relegation zone (Bottom 3)
    - **PL:** Matches Played
    - **W/D/L:** Wins/Draws/Losses (green/gray/red)
    - **GD:** Goal Difference
    - **PTS:** Points
    """)


# ============================================================================
# TAB 2: xG ANALYSIS
# ============================================================================

def tab_xg_analysis(league: str):
    """
    Display xG analysis: efficiency metrics and performance vs expected goals.
    
    Includes:
    - Scatter plot: xG for vs xG against (teams above diagonal overperform)
    - Bar chart: xG vs actual goals comparison
    
    Args:
        league: League name (e.g., 'Premier League', 'La Liga', 'Bundesliga', 'Serie A', 'Ligue 1')
    """
    st.header("📈 xG Analysis")
    
    # Load xG data
    match_xg_df = load_match_xg(league)
    fixtures_df = load_fixtures(league)
    
    if match_xg_df is None or fixtures_df is None:
        st.error("Unable to load xG data")
        return
    
    # Aggregate xG per team
    # Home team stats
    home_xg = match_xg_df.groupby('home_team').agg({
        'home_xg': 'sum',
        'away_xg': 'sum'
    }).reset_index()
    home_xg.columns = ['team', 'xg_for', 'xg_against']
    
    # Away team stats
    away_xg = match_xg_df.groupby('away_team').agg({
        'away_xg': 'sum',
        'home_xg': 'sum'
    }).reset_index()
    away_xg.columns = ['team', 'xg_for', 'xg_against']
    
    # Combine home and away
    team_xg = pd.concat([home_xg, away_xg], ignore_index=True)
    team_xg = team_xg.groupby('team').agg({
        'xg_for': 'sum',
        'xg_against': 'sum'
    }).reset_index()
    
    # Aggregate actual goals per team
    home_goals = fixtures_df.groupby('home_team').agg({
        'home_goals': 'sum',
        'away_goals': 'sum'
    }).reset_index()
    home_goals.columns = ['team', 'goals_for', 'goals_against']
    
    away_goals = fixtures_df.groupby('away_team').agg({
        'away_goals': 'sum',
        'home_goals': 'sum'
    }).reset_index()
    away_goals.columns = ['team', 'goals_for', 'goals_against']
    
    team_goals = pd.concat([home_goals, away_goals], ignore_index=True)
    team_goals = team_goals.groupby('team').agg({
        'goals_for': 'sum',
        'goals_against': 'sum'
    }).reset_index()
    
    # Merge xG and goals
    team_performance = team_xg.merge(team_goals, on='team')
    
    # Scatter plot: xG For vs xG Against
    st.subheader("xG Efficiency: Goals For vs Against")
    
    fig_scatter = px.scatter(
        team_performance,
        x='xg_against',
        y='xg_for',
        size='goals_for',
        color='goals_for',
        hover_name='team',
        hover_data={
            'xg_for': ':.2f',
            'xg_against': ':.2f',
            'goals_for': True,
            'goals_against': True
        },
        title="xG For vs xG Against (teams above diagonal overperform)",
        labels={
            'xg_for': 'Expected Goals For',
            'xg_against': 'Expected Goals Against'
        }
    )
    
    # Add diagonal line (expected performance)
    min_val = min(team_performance['xg_against'].min(), team_performance['xg_for'].min())
    max_val = max(team_performance['xg_against'].max(), team_performance['xg_for'].max())
    
    fig_scatter.add_trace(go.Scatter(
        x=[min_val, max_val],
        y=[min_val, max_val],
        mode='lines',
        name='Expected Performance',
        line=dict(dash='dash', color='gray'),
        hoverinfo='skip'
    ))
    
    fig_scatter.update_layout(height=500)
    st.plotly_chart(fig_scatter, use_container_width=True)
    
    # Bar chart: xG vs Actual Goals
    st.subheader("xG vs Actual Goals Performance")
    
    # Prepare data for grouped bar chart
    performance_comparison = team_performance[['team', 'xg_for', 'goals_for', 'xg_against', 'goals_against']].copy()
    performance_comparison = performance_comparison.sort_values('goals_for', ascending=True).tail(15)
    
    fig_bar = go.Figure()
    
    fig_bar.add_trace(go.Bar(
        y=performance_comparison['team'],
        x=performance_comparison['xg_for'],
        name='xG For',
        orientation='h',
        marker=dict(color='rgba(33, 150, 243, 0.7)')
    ))
    
    fig_bar.add_trace(go.Bar(
        y=performance_comparison['team'],
        x=performance_comparison['goals_for'],
        name='Actual Goals',
        orientation='h',
        marker=dict(color='rgba(76, 175, 80, 0.7)')
    ))
    
    fig_bar.update_layout(
        barmode='group',
        title='Top 15 Teams: xG vs Actual Goals',
        xaxis_title='Goals / xG',
        yaxis_title='Team',
        height=500,
        hovermode='y unified'
    )
    
    st.plotly_chart(fig_bar, use_container_width=True)


# ============================================================================
# TAB 3: TOP SCORERS & PLAYMAKERS
# ============================================================================

def tab_top_scorers_playmakers(league: str):
    """
    Display top scorers and playmakers with optional position filtering.
    
    Args:
        league: League name (e.g., 'Premier League', 'La Liga', 'Bundesliga', 'Serie A', 'Ligue 1')
    """
    st.header("👥 Top Scorers & Playmakers")
    
    # Load player data
    player_df = load_player_xg(league)
    
    if player_df is None or player_df.empty:
        st.error("Unable to load player data")
        return
    
    # Position filter
    available_positions = player_df['position'].unique()
    selected_position = st.selectbox(
        "Filter by Position",
        ["All"] + sorted(list(available_positions))
    )
    
    # Filter data
    if selected_position != "All":
        filtered_df = player_df[player_df['position'] == selected_position].copy()
    else:
        filtered_df = player_df.copy()
    
    # Create two columns
    col1, col2 = st.columns(2)
    
    # Top Scorers
    with col1:
        st.subheader("🔥 Top 10 Scorers")
        
        top_scorers = filtered_df.nlargest(10, 'goals')[['player_name', 'team_name', 'goals', 'xg', 'shots']].copy()
        
        if top_scorers.empty:
            st.warning("No scorer data available for selected position")
        else:
            fig_scorers = px.bar(
                top_scorers,
                x='goals',
                y='player_name',
                color='xg',
                orientation='h',
                title='Top 10 Goal Scorers',
                labels={'goals': 'Goals', 'player_name': 'Player'},
                hover_data=['team_name', 'shots']
            )
            
            fig_scorers.update_layout(height=450, showlegend=True)
            st.plotly_chart(fig_scorers, use_container_width=True)
    
    # Top Playmakers
    with col2:
        st.subheader("🎯 Top 10 Playmakers")
        
        # Create playmaking score: xA + assists (weighted towards assists)
        filtered_df['playmaking_score'] = filtered_df['xa'] * 0.4 + filtered_df['assists'] * 0.6
        
        top_playmakers = filtered_df.nlargest(10, 'playmaking_score')[['player_name', 'team_name', 'assists', 'xa', 'key_passes']].copy()
        
        if top_playmakers.empty:
            st.warning("No playmaker data available for selected position")
        else:
            fig_playmakers = px.bar(
                top_playmakers,
                x='assists',
                y='player_name',
                color='xa',
                orientation='h',
                title='Top 10 Playmakers (by assists)',
                labels={'assists': 'Assists', 'player_name': 'Player'},
                hover_data=['team_name', 'key_passes']
            )
            
            fig_playmakers.update_layout(height=450, showlegend=True)
            st.plotly_chart(fig_playmakers, use_container_width=True)


# ============================================================================
# TAB 4: PLAYER COMPARISON RADAR
# ============================================================================

def normalize_stats(value, min_val, max_val):
    """
    Normalize stat to 0-1 range for radar chart comparison.
    
    Args:
        value: The value to normalize
        min_val: Minimum value in dataset
        max_val: Maximum value in dataset
        
    Returns:
        float: Normalized value between 0-1
    """
    if max_val == min_val:
        return 0.5
    return (value - min_val) / (max_val - min_val)


def load_all_player_xg() -> Optional[pd.DataFrame]:
    """
    Load player xG statistics from database (all leagues).
    Used for player comparison where players can be from any league.
    
    Returns:
        pd.DataFrame: Player xG data with all available columns
        None if query fails
    """
    try:
        conn = sqlite3.connect("pl_data.db", check_same_thread=False)
        query = """SELECT player_name, team_name, position, games, minutes, goals, 
                          assists, xg, xa, npxg, shots, key_passes, xgchain, xgbuildup, league
                   FROM player_xg"""
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if df.empty:
            st.warning("No player xG data available")
            return None
        
        return df
    
    except Exception as e:
        st.error(f"Error loading player xG: {str(e)}")
        return None


def tab_player_comparison():
    """
    Display radar chart comparing two selected players across multiple metrics.
    Players can be from any league.
    
    Metrics: goals, assists, xg, xa, key_passes, shots
    """
    st.header("⚔️ Player Comparison Radar")
    
    st.markdown("*Compare any players from any league*")
    
    # Load player data from all leagues
    player_df = load_all_player_xg()
    
    if player_df is None or player_df.empty:
        st.error("Unable to load player data")
        return
    
    # Get list of all players
    all_players = sorted(player_df['player_name'].unique())
    
    col1, col2 = st.columns(2)
    
    with col1:
        player1_name = st.selectbox(
            "Select Player 1",
            all_players,
            key="player1"
        )
    
    with col2:
        player2_name = st.selectbox(
            "Select Player 2",
            all_players,
            index=1 if len(all_players) > 1 else 0,
            key="player2"
        )
    
    # Get player data
    player1_data = player_df[player_df['player_name'] == player1_name]
    player2_data = player_df[player_df['player_name'] == player2_name]
    
    if player1_data.empty or player2_data.empty:
        st.error("Selected player not found")
        return
    
    # Metrics to compare
    metrics = ['goals', 'assists', 'xg', 'xa', 'key_passes', 'shots']
    
    # Extract values
    player1_values = player1_data[metrics].values[0]
    player2_values = player2_data[metrics].values[0]
    
    # Normalize stats for fair comparison
    normalized_p1 = []
    normalized_p2 = []
    
    for metric in metrics:
        min_val = player_df[metric].min()
        max_val = player_df[metric].max()
        
        p1_norm = normalize_stats(player1_data[metric].values[0], min_val, max_val)
        p2_norm = normalize_stats(player2_data[metric].values[0], min_val, max_val)
        
        normalized_p1.append(p1_norm)
        normalized_p2.append(p2_norm)
    
    # Create radar chart
    fig = go.Figure()
    
    fig.add_trace(go.Scatterpolar(
        r=normalized_p1,
        theta=metrics,
        fill='toself',
        name=player1_name,
        line=dict(color='rgba(33, 150, 243, 0.8)'),
        fillcolor='rgba(33, 150, 243, 0.3)'
    ))
    
    fig.add_trace(go.Scatterpolar(
        r=normalized_p2,
        theta=metrics,
        fill='toself',
        name=player2_name,
        line=dict(color='rgba(76, 175, 80, 0.8)'),
        fillcolor='rgba(76, 175, 80, 0.3)'
    ))
    
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 1]
            )
        ),
        title=f"Player Comparison: {player1_name} vs {player2_name}",
        height=600,
        showlegend=True
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Display detailed stats
    st.subheader("Detailed Statistics")
    
    stats_comparison = pd.DataFrame({
        player1_name: player1_data[metrics].values[0],
        player2_name: player2_data[metrics].values[0]
    }, index=metrics)
    
    st.dataframe(stats_comparison, use_container_width=True)

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
# PAGE CONFIGURATION
# ============================================================================

st.set_page_config(
    page_title="PL 2024/25 Analytics Dashboard",
    page_icon="⚽",
    layout="wide"
)

# Add custom title and header
st.title("⚽ Premier League 2024/25 Analytics Dashboard")
st.markdown("---")

# ============================================================================
# DATABASE UTILITY FUNCTIONS
# ============================================================================
# NOTE: No cached DB connection. Each loader function opens/closes
# its own SQLite connection with `check_same_thread=False` to avoid
# cross-thread SQLite issues in Streamlit.

@st.cache_data
def load_standings() -> Optional[pd.DataFrame]:
    """
    Load league standings table from database.
    
    Returns:
        pd.DataFrame: Standings data with columns [rank, team_name, won, drawn, lost, points, goals_for, goals_against, goal_difference]
        None if query fails
    """
    try:
        conn = sqlite3.connect("pl_data.db", check_same_thread=False)
        query = "SELECT rank, team_name, played, won, drawn, lost, points, goals_for, goals_against, goal_difference FROM standings ORDER BY rank"
        df = pd.read_sql_query(query, conn)
        conn.close()

        if df.empty:
            st.warning("No standings data available")
            return None
        
        return df
    
    except Exception as e:
        st.error(f"Error loading standings: {str(e)}")
        return None


@st.cache_data
def load_match_xg() -> Optional[pd.DataFrame]:
    """
    Load match xG data from database.
    
    Returns:
        pd.DataFrame: Match xG data with columns [home_team, away_team, home_xg, away_xg, date]
        None if query fails
    """
    try:
        conn = sqlite3.connect("pl_data.db", check_same_thread=False)
        query = "SELECT home_team, away_team, home_xg, away_xg, match_date FROM match_xg"
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if df.empty:
            st.warning("No match xG data available")
            return None
        
        return df
    
    except Exception as e:
        st.error(f"Error loading match xG: {str(e)}")
        return None


@st.cache_data
def load_fixtures() -> Optional[pd.DataFrame]:
    """
    Load fixture data (actual goals) from database.
    
    Returns:
        pd.DataFrame: Fixture data with columns [home_team, away_team, goals_home, goals_away, date]
        None if query fails
    """
    try:
        conn = sqlite3.connect("pl_data.db", check_same_thread=False)
        query = "SELECT home_team, away_team, home_goals, away_goals, fixture_date FROM fixtures"
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if df.empty:
            st.warning("No fixture data available")
            return None
        
        return df
    
    except Exception as e:
        st.error(f"Error loading fixtures: {str(e)}")
        return None


@st.cache_data
def load_player_xg() -> Optional[pd.DataFrame]:
    """
    Load player xG statistics from database.
    
    Returns:
        pd.DataFrame: Player xG data with all available columns
        None if query fails
    """
    try:
        conn = sqlite3.connect("pl_data.db", check_same_thread=False)
        query = """SELECT player_name, team_name, position, games, minutes, goals, 
                          assists, xg, xa, npxg, shots, key_passes, xgchain, xgbuildup
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


# ============================================================================
# TAB 1: LEAGUE TABLE
# ============================================================================

def tab_league_table():
    """
    Display league standings with color coding and points visualization.
    
    Color scheme:
    - Green (Top 4): Champions League qualification
    - Blue (5-7): Europa League qualification
    - Orange/Yellow (8-17): Mid-table
    - Red (18-20): Relegation zone
    """
    st.header("📊 League Table")
    
    # Load standings data
    standings_df = load_standings()
    
    if standings_df is None or standings_df.empty:
        st.error("Unable to load standings data")
        return
    
    # Create color coding based on position
    def get_color(rank):
        """Assign color based on league position."""
        if rank <= 4:
            return "rgba(76, 175, 80, 0.3)"  # Green - Champions League
        elif rank <= 7:
            return "rgba(33, 150, 243, 0.3)"  # Blue - Europa League
        elif rank <= 17:
            return "rgba(255, 193, 7, 0.2)"  # Yellow - Mid-table
        else:
            return "rgba(244, 67, 54, 0.3)"  # Red - Relegation zone
    
    # Display standings table with color coding
    st.subheader("Final Standings")
    
    # Create styled dataframe display
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Display table with metrics
        for idx, row in standings_df.iterrows():
            color = get_color(row['rank'])
            with st.container():
                st.markdown(f"""
                <div style="background-color: {color}; padding: 10px; border-radius: 5px; margin: 5px 0;">
                    <b>{int(row['rank'])}. {row['team_name']}</b> - 
                    {int(row['points'])} pts | 
                    {int(row['won'])}W-{int(row['drawn'])}D-{int(row['lost'])}L | 
                    GD: {int(row['goal_difference'])}
                </div>
                """, unsafe_allow_html=True)
    
    with col2:
        st.metric("Leader", standings_df.iloc[0]['team_name'], standings_df.iloc[0]['points'])
        st.metric("Relegation Zone", standings_df.iloc[-1]['team_name'], standings_df.iloc[-1]['points'])
    
    # Points distribution bar chart
    st.subheader("Points Distribution by Team")
    
    # Create bar chart with color coding
    fig = go.Figure()
    
    colors_list = [get_color(pos).replace("0.3", "1").replace("0.2", "1") for pos in standings_df['rank']]
    
    fig.add_trace(go.Bar(
        x=standings_df['team_name'],
        y=standings_df['points'],
        marker=dict(color=colors_list),
        text=standings_df['points'],
        textposition='outside',
        hovertemplate='<b>%{x}</b><br>Points: %{y}<extra></extra>'
    ))
    
    fig.update_layout(
        title="Points by Team",
        xaxis_title="Team",
        yaxis_title="Points",
        height=500,
        showlegend=False,
        xaxis_tickangle=-45,
        hovermode='x unified'
    )
    
    st.plotly_chart(fig, use_container_width=True)


# ============================================================================
# TAB 2: xG ANALYSIS
# ============================================================================

def tab_xg_analysis():
    """
    Display xG analysis: efficiency metrics and performance vs expected goals.
    
    Includes:
    - Scatter plot: xG for vs xG against (teams above diagonal overperform)
    - Bar chart: xG vs actual goals comparison
    """
    st.header("📈 xG Analysis")
    
    # Load xG data
    match_xg_df = load_match_xg()
    fixtures_df = load_fixtures()
    
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

def tab_top_scorers_playmakers():
    """
    Display top scorers and playmakers with optional position filtering.
    """
    st.header("👥 Top Scorers & Playmakers")
    
    # Load player data
    player_df = load_player_xg()
    
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


def tab_player_comparison():
    """
    Display radar chart comparing two selected players across multiple metrics.
    
    Metrics: goals, assists, xg, xa, key_passes, shots
    """
    st.header("⚔️ Player Comparison Radar")
    
    # Load player data
    player_df = load_player_xg()
    
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


# ============================================================================
# MAIN APP: CREATE TABS
# ============================================================================

def main():
    """
    Main application function. Creates tabs and renders selected tab content.
    """
    # Create tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 League Table",
        "📈 xG Analysis",
        "👥 Top Scorers & Playmakers",
        "⚔️ Player Comparison"
    ])
    
    # TAB 1: League Table
    with tab1:
        tab_league_table()
    
    # TAB 2: xG Analysis
    with tab2:
        tab_xg_analysis()
    
    # TAB 3: Top Scorers & Playmakers
    with tab3:
        tab_top_scorers_playmakers()
    
    # TAB 4: Player Comparison
    with tab4:
        tab_player_comparison()
    
    # Footer
    st.markdown("---")
    st.markdown(
        """
        <div style="text-align: center; color: gray; font-size: 12px;">
            Premier League 2024/25 Analytics Dashboard | Data from pl_data.db
        </div>
        """,
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()

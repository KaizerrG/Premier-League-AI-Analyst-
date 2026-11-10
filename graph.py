"""
LangGraph-based workflow for Premier League data analysis.

This module implements a multi-node graph that:
1. Routes questions to appropriate specialist nodes
2. Executes specialized SQL queries based on question type
3. Combines results from multiple sources
4. Generates coherent final answers using Groq LLM
"""

import os
import re
import sqlite3
from typing import TypedDict, Optional, Annotated
import pandas as pd

from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, END
from settings import DATABASE_PATH, SEASON, SEASON_LABEL

# ============================================================================
# STATE MERGING UTILITY
# ============================================================================

def merge_dicts(a: dict, b: dict) -> dict:
    """
    Merge two dictionaries, with b values overwriting a values.
    Used for concurrent state updates where multiple nodes write to results.
    
    Args:
        a: Base dictionary
        b: Dictionary to merge in
        
    Returns:
        Merged dictionary
    """
    merged = a.copy()
    merged.update(b)
    return merged

# ============================================================================
# STATE DEFINITION
# ============================================================================

class PLAnalystState(TypedDict):
    """
    State object passed through the LangGraph workflow.
    
    Attributes:
        question: The user's natural language question
        routes: List of specialist nodes to execute (e.g., ["player", "standings"])
        results: Dictionary storing results from each specialist node
                 Uses Annotated with merge_dicts for concurrent safe updates
        answer: Final synthesized answer from combine_node
        conversation: List of prior conversation turns for context
    """
    question: str
    routes: list
    results: Annotated[dict, merge_dicts]
    answer: str
    conversation: list


# ============================================================================
# LLM CONFIGURATION
# ============================================================================

# Initialize Groq LLM with environment API key
llm = ChatGroq(
    model="openai/gpt-oss-20b",
    api_key=os.getenv("GROQ_API_KEY"),
    temperature=0.7,
    timeout=30,
)


# ============================================================================
# SQL EXECUTION TOOL
# ============================================================================

def read_sql_frame(query: str, params=()) -> pd.DataFrame:
    """Read one SELECT query from the database opened in read-only mode."""
    query = query.strip().rstrip(";").strip()
    if ";" in query or not re.match(r"^(select|with)\b", query, re.IGNORECASE):
        raise ValueError("Only one read-only SELECT query is allowed.")
    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(f"Database not found: {DATABASE_PATH}. Run fetch_all.py first.")

    db_uri = f"{DATABASE_PATH.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(db_uri, uri=True, timeout=15)
    try:
        conn.execute("PRAGMA query_only = ON")
        return pd.read_sql_query(query, conn, params=params)
    finally:
        conn.close()


def run_sql(query: str, params=()) -> str:
    """Execute one read-only SELECT and format its rows for the analyst."""
    df = read_sql_frame(query, params)
    if df.empty:
        return "No data found for this query."
    return df.to_string(index=False)


def clean_sql_response(sql: str) -> str:
    """Remove an optional Markdown SQL fence from an LLM response."""
    return re.sub(r"^```(?:sql)?\s*|\s*```$", "", sql.strip(), flags=re.IGNORECASE).strip()


def run_query_from_prompt(prompt: str) -> str:
    """Generate and execute a query, retrying once with the database error."""
    last_error = None
    for attempt in range(2):
        retry_note = ""
        if attempt:
            retry_note = (
                f"\nThe previous SQL failed with this error: {last_error}\n"
                "Correct the query using only the tables and columns listed above. "
                "Return one read-only SELECT query and no explanation."
            )
        response = llm.invoke(prompt + retry_note)
        sql_query = clean_sql_response(response.content)
        try:
            return run_sql(sql_query)
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"SQL query failed after one retry: {last_error}") from last_error


def answer_common_question(question: str) -> Optional[str]:
    """Answer common leaderboard questions with fixed, schema-safe queries."""
    q = question.casefold()
    leagues = {
        "premier league": "Premier League",
        "la liga": "La Liga",
        "bundesliga": "Bundesliga",
        "serie a": "Serie A",
        "ligue 1": "Ligue 1",
    }
    league = next((name for key, name in leagues.items() if key in q), "Premier League")
    season_match = re.search(r"\b20\d{2}\b", q)
    season = season_match.group(0) if season_match else SEASON
    all_leagues = "all leagues" in q or "across leagues" in q
    league_filter = "" if all_leagues else " AND league = ?"
    # The SQL places the season placeholder before the optional league one.
    params = (season,) if all_leagues else (season, league)

    player_query = None
    title = None
    metric = None
    if re.search(r"\b(top scorer|most goals|highest scoring)\b", q):
        player_query = f"SELECT player_name, goals FROM player_xg WHERE season = ?{league_filter} ORDER BY goals DESC LIMIT 1"
        title, metric = "top scorer", "goals"
    elif re.search(r"\b(most assists|highest assists)\b", q):
        player_query = f"SELECT player_name, assists FROM player_xg WHERE season = ?{league_filter} ORDER BY assists DESC LIMIT 1"
        title, metric = "most assists", "assists"
    elif re.search(r"\b(highest|most) (?:xg|expected goals)\b", q):
        player_query = f"SELECT player_name, xg FROM player_xg WHERE season = ?{league_filter} ORDER BY xg DESC LIMIT 1"
        title, metric = "highest xG", "xg"
    elif re.search(r"\b(overperform|overperforming|outperform|outperforming)\b.*\bxg\b", q):
        player_query = f"SELECT player_name, goals - xg AS difference FROM player_xg WHERE season = ?{league_filter} ORDER BY difference DESC LIMIT 1"
        title, metric = "highest overperformance against xG", "difference"
    elif re.search(r"\b(compare|comparison)\b.*\btop two scorers\b|\btop two scorers\b.*\b(compare|comparison)\b", q):
        player_query = f"SELECT player_name, goals, assists FROM player_xg WHERE season = ?{league_filter} ORDER BY goals DESC LIMIT 2"

    if player_query:
        df = read_sql_frame(player_query, params)
        if df.empty:
            return f"No player data is available for {league} in the {season}/{(int(season) + 1) % 100:02d} season."
        if metric:
            row = df.iloc[0]
            value = f"{float(row[metric]):.2f}" if metric == "difference" else str(row[metric])
            return f"{row['player_name']} has the {title} in {league} with {value} {metric if metric != 'difference' else 'goals above xG'}."
        lines = [f"{row.player_name}: {int(row.goals)} goals, {int(row.assists)} assists" for row in df.itertuples(index=False)]
        return f"Top two scorers in {league}: " + "; ".join(lines) + "."

    standings_query = None
    standings_title = None
    if re.search(r"\b(best|highest) goal difference\b", q):
        standings_query = f"SELECT team_name, goal_difference FROM standings WHERE season = ?{league_filter} ORDER BY goal_difference DESC LIMIT 1"
        standings_title = "best goal difference"
    elif re.search(r"\b(top of (?:the )?(?:league|table)|leader of (?:the )?(?:league|table)|top team)\b", q):
        standings_query = f"SELECT team_name, points FROM standings WHERE season = ?{league_filter} ORDER BY points DESC LIMIT 1"
        standings_title = "top of the league"

    if standings_query:
        df = read_sql_frame(standings_query, params)
        if df.empty:
            return f"No standings data is available for {league} in the {season}/{(int(season) + 1) % 100:02d} season."
        row = df.iloc[0]
        value = row.iloc[1]
        unit = "points" if standings_title == "top of the league" else "goal difference"
        return f"{row['team_name']} has the {standings_title} in {league} with {value} {unit}."
    return None


# ============================================================================
# NODE 1: ROUTER NODE
# ============================================================================

def router_node(state: PLAnalystState) -> PLAnalystState:
    """
    Route the user's question to one or more specialist nodes.
    
    Uses Groq to classify the question into categories:
    - player: Questions about individual player stats, goals, xG
    - match: Questions about specific matches, performance
    - standings: Questions about league table, points, position
    - prediction: Questions asking for predictions or analysis
    
    Decision logic:
    - A question can route to multiple categories
    - Router uses structured prompt to ensure comma-separated output
    - Results stored in state["routes"] as list
    
    Args:
        state: Current workflow state
        
    Returns:
        Updated state with "routes" field populated
    """
    try:
        # Construct prompt with explicit instruction for output format
        routing_prompt = f"""You are a question router for a Premier League analysis system.

Classify the user's question into one or more of these categories:
- player: Questions about player stats, goals, assists, xG, performance
- match: Questions about specific matches, team performance in games
- standings: Questions about league table, points, rankings, team position
- prediction: Questions asking for predictions or comparative analysis

User Question: {state['question']}

IMPORTANT: Return ONLY a comma-separated list of applicable categories. 
Example format: "player,standings" or "match" or "player,match,prediction"

Do not include explanations, just the categories."""

        # Call Groq LLM
        response = llm.invoke(routing_prompt)
        routes_text = response.content.strip().lower()
        
        # Parse comma-separated routes and clean whitespace
        routes = [route.strip() for route in routes_text.split(',')]
        
        # Validate routes against allowed categories
        allowed_routes = {"player", "match", "standings", "prediction"}
        routes = [r for r in routes if r in allowed_routes]
        
        # Fallback: if no valid routes found, default to match
        if not routes:
            routes = ["match"]
        
        state["routes"] = routes
        
    except Exception as e:
        print(f"Error in router_node: {str(e)}")
        # Fallback to broad search if routing fails
        state["routes"] = ["match"]
    
    return state


# ============================================================================
# NODE 2: PLAYER NODE
# ============================================================================

def player_node(state: PLAnalystState) -> PLAnalystState:
    """
    Handle questions about player statistics.
    
    Queries tables:
    - player_xg: Expected goals by player (now includes league column)
    - top_scorers: Top goal scorers
    
    Process:
    1. Use Groq to generate SQL based on question
    2. Execute SQL against pl_data.db
    3. Store results in state["results"]["player"]
    
    Args:
        state: Current workflow state
        
    Returns:
        Updated state with results from player queries
    """
    try:
        sql_prompt = f"""You are a Premier League SQL expert.

Available columns ONLY:
Table: player_xg
player_name, team_name, position, games, minutes, goals, 
assists, xg, xa, npxg, shots, key_passes, xgchain, xgbuildup, yellow_cards, red_cards, league, season

IMPORTANT LEAGUE FILTERING:
- If user mentions a specific league (e.g., "Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1"), ALWAYS add WHERE league = 'League Name'
- Default to Premier League unless the user explicitly asks for all leagues
- Filter by the named league whenever the question specifies one

Choose the statistic requested and sort by that statistic (for example, goals
DESC for top scorer, assists DESC for most assists, xg DESC for highest xG).
Use only columns listed above. Default to league = 'Premier League' and season
= '{SEASON}' unless the user requests a different league or season. Return a
small useful result set with a LIMIT of at most 20.

User Question: {state['question']}

Return ONLY SQL. no explanation.
Use proper SQLite syntax.
NEVER invent columns."""

        results = run_query_from_prompt(sql_prompt)
        
    except Exception as e:
        error_msg = f"QUERY_ERROR: player data could not be queried: {e}"
        print(error_msg)
        results = error_msg
    
    # Only return the results update for this node
    # This prevents concurrent write conflicts with other specialist nodes
    return {"results": {"player": results}}


# ============================================================================
# NODE 3: MATCH NODE
# ============================================================================

def match_node(state: PLAnalystState) -> PLAnalystState:
    """
    Handle questions about match data and performance.
    
    Queries tables:
    - fixtures: Match information (teams, dates, results)
    - match_xg: Expected goals per match (now includes league column)
    - fixture_stats: Match statistics (possession, shots, corners, etc.)
    
    Process:
    1. Use Groq to generate SQL based on question
    2. Execute SQL against pl_data.db
    3. Store results in state["results"]["match"]
    
    Args:
        state: Current workflow state
        
    Returns:
        Updated state with results from match queries
    """
    try:
        sql_prompt = f"""You are a Premier League SQL expert for match analysis.

Allowed table: fixtures (preferred) or match_xg.
Available columns in fixtures:
id, league, season, fixture_id, home_team, away_team, home_goals, away_goals,
home_xg, away_xg, home_win_prob, draw_prob, away_win_prob, match_date

Available columns in match_xg:
id, league, season, match_id, home_team, away_team, home_xg, away_xg, match_date

Use fixtures for match results and expected goals; it already contains both.
Filter to league = 'Premier League' and season = '{SEASON}' by default, unless
the user requests a different league, all leagues, or another season. Use
match_date as the date column. Do not reference tables or columns not listed.

User Question: {state['question']}

Return ONLY SQL. no explanation.
Use proper SQLite syntax.
NEVER invent columns."""

        results = run_query_from_prompt(sql_prompt)
        
    except Exception as e:
        error_msg = f"QUERY_ERROR: match data could not be queried: {e}"
        print(error_msg)
        results = error_msg
    
    # Only return the results update for this node
    # This prevents concurrent write conflicts with other specialist nodes
    return {"results": {"match": results}}


# ============================================================================
# NODE 4: STANDINGS NODE
# ============================================================================

def standings_node(state: PLAnalystState) -> PLAnalystState:
    """
    Handle questions about league standings and team rankings.
    
    Queries tables:
    - standings: Current league table with points, wins, losses, draws
    - team-level xG and results stored directly in standings
    
    Process:
    1. Use Groq to generate SQL based on question
    2. Execute SQL against pl_data.db
    3. Store results in state["results"]["standings"]
    
    Args:
        state: Current workflow state
        
    Returns:
        Updated state with results from standings queries
    """
    try:
        sql_prompt = f"""You are a SQL expert for Premier League data analysis.

Allowed table: standings. EXACT schema (DO NOT USE OTHER COLUMNS):

standings table columns:
  league, season, rank, team_name, played, won, drawn, lost, goals_for,
  goals_against, goal_difference, xg, xga, points

The active season is {SEASON_LABEL} (season value '{SEASON}'). Filter to league
= 'Premier League' and season = '{SEASON}' unless the question explicitly asks
for another league, all leagues, or another season. Use only the columns above.

User Question: {state['question']}

Generate a SQL query to answer this question.
IMPORTANT: Return ONLY the SQL query, no explanation.
Sort by relevant columns (e.g., points DESC for standings).
Use proper SQL syntax for SQLite.
NEVER use unlisted columns."""

        results = run_query_from_prompt(sql_prompt)
        
    except Exception as e:
        error_msg = f"QUERY_ERROR: standings data could not be queried: {e}"
        print(error_msg)
        results = error_msg
    
    # Only return the results update for this node
    # This prevents concurrent write conflicts with other specialist nodes
    return {"results": {"standings": results}}


# ============================================================================
# NODE 5: PREDICTION NODE
# ============================================================================

def prediction_node(state: PLAnalystState) -> PLAnalystState:
    """
    Handle predictive and analytical questions requiring multi-table reasoning.
    
    Queries tables:
    - fixtures: Match data for form analysis
    - match_xg: Expected goals for xG-based predictions (now includes league column)
    - fixture_stats: Match statistics
    - standings: Current standings for context
    - player_xg: Player performance metrics (now includes league column)
    
    Key reasoning factors:
    - Team form (recent results)
    - Expected Goals (xG and xGA)
    - Home advantage patterns
    - Head-to-head records (if relevant)
    
    Process:
    1. Use Groq to generate SQL with explicit reasoning instructions
    2. Execute SQL to gather prediction data
    3. Store results in state["results"]["prediction"]
    
    Args:
        state: Current workflow state
        
    Returns:
        Updated state with results for prediction analysis
    """
    try:
        sql_prompt = f"""You are a Premier League SQL expert for predictive analysis.

Available columns ONLY:
Allowed tables: fixtures, match_xg, standings, player_xg.
fixtures: league, season, fixture_id, home_team, away_team, home_goals, away_goals, home_xg, away_xg, match_date
match_xg: league, season, match_id, home_team, away_team, home_xg, away_xg, match_date
standings: league, season, rank, team_name, played, won, drawn, lost, goals_for, goals_against, goal_difference, xg, xga, points
player_xg: league, season, player_name, team_name, position, games, minutes, goals, assists, xg, xa, npxg, shots, key_passes, xgchain, xgbuildup, yellow_cards, red_cards

Filter every relevant table to league = 'Premier League' and season = '{SEASON}'
by default unless the user requests a different league, all leagues, or another
season. Use match_date for time ordering. Do not reference unlisted columns or
tables. Join fixtures and match_xg with fixtures.fixture_id = match_xg.match_id,
and include league and season in the join.

User Question: {state['question']}

Return ONLY SQL. no explanation.
Order by recent data (match_date DESC) for form analysis.
Use proper SQLite syntax.
NEVER invent columns."""

        results = run_query_from_prompt(sql_prompt)
        
    except Exception as e:
        error_msg = f"QUERY_ERROR: prediction data could not be queried: {e}"
        print(error_msg)
        results = error_msg
    
    # Only return the results update for this node
    # This prevents concurrent write conflicts with other specialist nodes
    return {"results": {"prediction": results}}


# ============================================================================
# NODE 6: COMBINE NODE
# ============================================================================

def combine_node(state: PLAnalystState) -> PLAnalystState:
    """
    Synthesize results from all specialist nodes into a coherent final answer.
    
    Process:
    1. Collect all results from state["results"] dictionary
    2. Pass results + original question to Groq
    3. Groq reasons across all data sources
    4. Generate natural language answer
    5. Store in state["answer"]
    
    The LLM is instructed to:
    - Cross-reference data from multiple sources
    - Highlight key insights and patterns
    - Provide context and interpretation
    - Structure answer clearly for end user
    
    Args:
        state: Current workflow state with results from specialist nodes
        
    Returns:
        Updated state with final answer in state["answer"]
    """
    try:
        # Compile all available results
        results_text = ""
        for route, result in state["results"].items():
            results_text += f"\n[{route.upper()} DATA]\n{result}\n"
        
        # If no results available, return empty answer
        if not results_text.strip():
            return {"answer": "Unable to retrieve data for this question."}

        if all(str(result).startswith("QUERY_ERROR:") for result in state["results"].values()):
            return {"answer": "I couldn't retrieve matching data from the database. Check that the database has been fetched and that the question uses supported data."}
        
        # Construct synthesis prompt
        synthesis_prompt = f"""You are a Premier League analyst synthesizing data from multiple sources.

User Question: {state['question']}

Available Data from Specialist Nodes:
{results_text}

Task:
1. Analyze all provided data
2. Cross-reference insights from different sources
3. Identify patterns and key metrics
4. Provide a clear, comprehensive answer to the user's question

Guidelines:
- Be specific and cite data from the results above
- Treat database results as the only source of factual claims; never invent values
- If a specialist reports QUERY_ERROR, say that the data could not be retrieved
- For a ranking, state the entity and the requested number (goals, assists, xG, or points)
- For comparisons, include every returned entity and all requested metrics
- Highlight relevant patterns or trends
- If data is incomplete or contradictory, acknowledge it
- Structure your answer clearly with key points first
- Keep language natural and conversational

Generate a final answer that directly addresses the user's question."""

        # Call Groq LLM to synthesize
        response = llm.invoke(synthesis_prompt)
        answer = response.content
        
    except Exception as e:
        error_msg = f"Error in combine_node: {str(e)}"
        print(error_msg)
        answer = error_msg
    
    # Only return the answer update for this node
    return {"answer": answer}


# ============================================================================
# CONDITIONAL ROUTING LOGIC
# ============================================================================

def route_to_specialist_nodes(state: PLAnalystState) -> list:
    """
    Determine which specialist nodes should execute based on routes.
    
    This function is used as a "conditional edge" in LangGraph.
    It returns the next node(s) to execute based on state["routes"].
    
    Mapping:
    - "player" -> "player_node"
    - "match" -> "match_node"
    - "standings" -> "standings_node"
    - "prediction" -> "prediction_node"
    
    After executing specialist nodes, the workflow always proceeds to "combine_node".
    
    Args:
        state: Current workflow state
        
    Returns:
        List of node names to execute next
    """
    routes_map = {
        "player": "player_node",
        "match": "match_node",
        "standings": "standings_node",
        "prediction": "prediction_node",
    }
    
    # Convert routes to node names
    next_nodes = [routes_map.get(route, "match_node") for route in state["routes"]]
    
    # Remove duplicates while preserving order
    seen = set()
    next_nodes = [x for x in next_nodes if not (x in seen or seen.add(x))]
    
    return next_nodes


# ============================================================================
# GRAPH CONSTRUCTION
# ============================================================================

def build_graph():
    """
    Construct the LangGraph workflow with all nodes and edges.
    
    Workflow Structure:
    1. START → router_node (classify question into routes)
    2. router_node → [conditional dispatch to specialist nodes]
    3. player_node → combine_node
       match_node → combine_node
       standings_node → combine_node
       prediction_node → combine_node
    4. combine_node → END
    
    Conditional Routing:
    - Router outputs determine which specialist nodes execute
    - All specialist nodes execute in parallel (LangGraph optimization)
    - All results feed into combine_node
    - Combine synthesizes final answer
    
    Returns:
        Compiled LangGraph workflow ready for invocation
    """
    # Initialize state graph
    workflow = StateGraph(PLAnalystState)
    
    # Add all nodes to the graph
    workflow.add_node("router_node", router_node)
    workflow.add_node("player_node", player_node)
    workflow.add_node("match_node", match_node)
    workflow.add_node("standings_node", standings_node)
    workflow.add_node("prediction_node", prediction_node)
    workflow.add_node("combine_node", combine_node)
    
    # Set entry point (router always runs first)
    workflow.set_entry_point("router_node")
    
    # Add conditional edge from router to specialist nodes
    # route_to_specialist_nodes determines which nodes execute
    workflow.add_conditional_edges(
        "router_node",
        route_to_specialist_nodes,
    )
    
    # All specialist nodes route to combine_node
    workflow.add_edge("player_node", "combine_node")
    workflow.add_edge("match_node", "combine_node")
    workflow.add_edge("standings_node", "combine_node")
    workflow.add_edge("prediction_node", "combine_node")
    
    # Combine node ends the workflow
    workflow.add_edge("combine_node", END)
    
    # Compile the graph
    graph = workflow.compile()
    
    return graph


# ============================================================================
# MAIN EXECUTION LOOP
# ============================================================================

def run_analyst(question: str, conversation_history: Optional[list] = None) -> str:
    """
    Execute the graph with a user question and return the final answer.
    
    Main entry point for the LangGraph workflow.
    
    Args:
        question: User's natural language question about Premier League data
        conversation_history: Optional list of prior turns for context
        
    Returns:
        Final synthesized answer from the graph
    """
    if re.search(r"\b(drop|delete|insert|update|alter|create|truncate|replace)\s+(table|into|from|set)\b", question, re.IGNORECASE):
        return "I can't modify the database. Analyst queries are read-only."

    years = [int(year) for year in re.findall(r"\b20\d{2}\b", question)]
    asks_for_prediction = re.search(r"\b(will win|winner|champion|predict|forecast)\b", question, re.IGNORECASE)
    if asks_for_prediction and any(year > int(SEASON) + 1 for year in years):
        return f"I can't reliably predict results for {max(years)}; the analyst only answers from available {SEASON_LABEL} data."

    direct_answer = answer_common_question(question)
    if direct_answer is not None:
        return direct_answer

    # Initialize state
    initial_state = {
        "question": question,
        "routes": [],
        "results": {},
        "answer": "",
        "conversation": conversation_history or [],
    }
    
    # Build and invoke graph
    graph = build_graph()
    
    try:
        # Execute the workflow
        final_state = graph.invoke(initial_state)
        return final_state["answer"]
    
    except Exception as e:
        return f"Error executing analysis workflow: {str(e)}"


# ============================================================================
# INTERACTIVE CLI FOR TESTING
# ============================================================================

if __name__ == "__main__":
    """
    Simple command-line interface to test the graph interactively.
    
    Usage:
        python graph.py
        
    The CLI will:
    - Prompt for questions
    - Run through the full workflow
    - Display the final answer
    - Maintain conversation history
    """
    print("\n" + "="*70)
    print("Premier League AI Analyst - LangGraph Workflow")
    print("="*70)
    print(f"Ask any question about the Premier League {SEASON_LABEL} season.")
    print("Type 'quit' to exit.\n")
    
    conversation_history = []
    
    while True:
        try:
            # Get user input
            user_input = input("You: ").strip()
            
            if user_input.lower() in ["quit", "exit", "q"]:
                print("\nGoodbye! ⚽")
                break
            
            if not user_input:
                continue
            
            print("\n🔄 Analyzing question...")
            
            # Run the analyst
            answer = run_analyst(user_input, conversation_history)
            
            # Display answer
            print(f"\nAnalyst: {answer}\n")
            
            # Add to conversation history
            conversation_history.append({"question": user_input, "answer": answer})
            
        except KeyboardInterrupt:
            print("\n\nGoodbye! ⚽")
            break
        except Exception as e:
            print(f"\nError: {str(e)}\n")

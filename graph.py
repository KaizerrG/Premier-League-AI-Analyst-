"""
LangGraph-based workflow for Premier League data analysis.

This module implements a multi-node graph that:
1. Routes questions to appropriate specialist nodes
2. Executes specialized SQL queries based on question type
3. Combines results from multiple sources
4. Generates coherent final answers using Groq LLM
"""

import os
import sqlite3
from typing import TypedDict, Optional, Annotated
from dotenv import load_dotenv
import pandas as pd

from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage

# Load environment variables from .env file
load_dotenv()

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
    model="llama-3.3-70b-versatile",
    api_key=os.getenv("GROQ_API_KEY"),
    temperature=0.7,
    timeout=30,
)


# ============================================================================
# SQL EXECUTION TOOL
# ============================================================================

def run_sql(query: str) -> str:
    """
    Execute SQL query against pl_data.db and return results as formatted string.
    
    Args:
        query: SQL query string to execute
        
    Returns:
        String representation of query results (pandas DataFrame.to_string())
        
    Raises:
        sqlite3.Error: If database connection or query execution fails
    """
    try:
        conn = sqlite3.connect("pl_data.db")
        df = pd.read_sql(query, conn)
        conn.close()
        
        # Return formatted string, handle empty results
        if df.empty:
            return "No data found for this query."
        
        return df.to_string()
    
    except sqlite3.Error as e:
        return f"Database error: {str(e)}"
    except Exception as e:
        return f"Error executing SQL query: {str(e)}"


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
    - player_xg: Expected goals by player
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
        # Prompt Groq to generate SQL query with stat combination guidance
        sql_prompt = f"""You are a Premier League SQL expert.

For complex concepts use these stat combinations:
- creative/playmaker = xA, key_passes, assists, xGChain
- clinical/finisher = goals, npxG, shots, xG
- complete player = goals, assists, xG, xA, xGChain
- dangerous = xG, shots, key_passes
- hardworking = minutes, games, xGBuildup

Available columns ONLY:
player_name, team_name, position, games, minutes, goals, 
assists, xG, xA, npxG, shots, key_passes, xGChain, xGBuildup, yellow_cards, red_cards

Write ONE SQL query that:
1. Selects all individual stats as separate columns (for comparison)
2. Orders by a weighted score to rank players (but do NOT display the score)
3. Shows which stats outweigh others by the ranking

Example - for creative players order by playmaking but show all stats:
SELECT player_name, team_name, position,
       xA, key_passes, assists, xGChain
FROM player_xg
ORDER BY (xA * 0.3 + key_passes * 0.3 + assists * 0.4) DESC
LIMIT 10

Example - for strikers order by finishing but show all stats:
SELECT player_name, team_name, position,
       goals, npxG, shots, xG
FROM player_xg
ORDER BY (goals * 0.4 + npxG * 0.3 + shots * 0.3) DESC
LIMIT 10

User Question: {state['question']}

Return ONLY SQL. no explanation.
SELECT all individual stats as columns (NOT the score).
ORDER BY weighted combination to rank players.
Use proper SQLite syntax.
NEVER invent columns."""

        response = llm.invoke(sql_prompt)
        sql_query = response.content.strip()
        
        # Remove markdown code blocks if present
        if sql_query.startswith("```"):
            sql_query = sql_query.split("```")[1].replace("sql", "", 1).strip()
        
        # Execute query
        results = run_sql(sql_query)
        
    except Exception as e:
        error_msg = f"Error in player_node: {str(e)}"
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
    - match_xg: Expected goals per match
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

For performance metrics use these stat combinations:
- offensive dominance = goals_home + xg_home + shots_home + possession_home
- defensive strength = goals_away + xg_away + shots_away
- possession control = possession_home + shots_home
- set piece danger = corners_home (use with goals_home for correlation)
- match intensity = shots_home + shots_away + corners_home (total action)

Available columns ONLY:
fixtures: home_team, away_team, date, goals_home, goals_away, gameweek
match_xg: home_team, away_team, xg_home, xg_away, date
fixture_stats: home_team, away_team, date, possession_home, shots_home, shots_away, corners_home

Combine tables with JOINs on (home_team, away_team, date).
For rankings use weighted scoring to show dominance:
SELECT home_team, (xg_home * 0.4 + possession_home * 0.3) as dominance_score

User Question: {state['question']}

Return ONLY SQL. no explanation.
Use proper SQLite syntax.
NEVER invent columns."""

        response = llm.invoke(sql_prompt)
        sql_query = response.content.strip()
        
        # Remove markdown code blocks if present
        if sql_query.startswith("```"):
            sql_query = sql_query.split("```")[1].replace("sql", "", 1).strip()
        
        # Execute query
        results = run_sql(sql_query)
        
    except Exception as e:
        error_msg = f"Error in match_node: {str(e)}"
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
    - team_stats: Aggregate team statistics (goals, xG, defensive stats)
    
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

EXACT Table Schemas (DO NOT USE ANY OTHER COLUMNS):

standings table columns:
  position, team, wins, draws, losses, points, goal_difference

team_stats table columns:
  team, games_played, total_goals, total_xg, total_xg_against

User Question: {state['question']}

Generate a SQL query to answer this question.
IMPORTANT: Return ONLY the SQL query, no explanation.
Sort by relevant columns (e.g., points DESC for standings).
Use proper SQL syntax for SQLite.
NEVER use unlisted columns."""

        response = llm.invoke(sql_prompt)
        sql_query = response.content.strip()
        
        # Remove markdown code blocks if present
        if sql_query.startswith("```"):
            sql_query = sql_query.split("```")[1].replace("sql", "", 1).strip()
        
        # Execute query
        results = run_sql(sql_query)
        
    except Exception as e:
        error_msg = f"Error in standings_node: {str(e)}"
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
    - match_xg: Expected goals for xG-based predictions
    - fixture_stats: Match statistics
    - standings: Current standings for context
    - player_xg: Player performance metrics
    
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

For prediction concepts use these stat combinations:
- team form = recent wins + recent xG differential (ORDER BY date DESC)
- home advantage = home_goals / home_xg ratio vs away_goals / away_xg ratio
- xG-based strength = xg_home - xg_away over recent matches
- player threat = top player goals + xG in recent games
- defensive record = goals_against + xga patterns
- momentum = recent points trend

Available columns ONLY:
fixtures: home_team, away_team, date, goals_home, goals_away, gameweek
match_xg: home_team, away_team, xg_home, xg_away, date
fixture_stats: home_team, away_team, date, possession_home, shots_home, shots_away, corners_home
standings: position, team, wins, draws, losses, points, goal_difference
player_xg: player_name, team_name, position, games, minutes, goals, assists, xG, xA, npxG, shots, key_passes, xGChain, xGBuildup, yellow_cards, red_cards

JOIN tables on dates and team names to combine form, xG, and player data.
For predictions use weighted scoring:
SELECT home_team, away_team, (xg_home * 0.4 + points_home * 0.3) as prediction_score

User Question: {state['question']}

Return ONLY SQL. no explanation.
Order by recent data (date DESC) for form analysis.
Use proper SQLite syntax.
NEVER invent columns."""

        response = llm.invoke(sql_prompt)
        sql_query = response.content.strip()
        
        # Remove markdown code blocks if present
        if sql_query.startswith("```"):
            sql_query = sql_query.split("```")[1].replace("sql", "", 1).strip()
        
        # Execute query
        results = run_sql(sql_query)
        
    except Exception as e:
        error_msg = f"Error in prediction_node: {str(e)}"
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
    print("Ask any question about the Premier League 2024/25 season.")
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

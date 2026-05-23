"""
ROCKY: Premier League Analytics Crew using CrewAI
WHY: This module orchestrates a hierarchical crew of AI agents to answer Premier League analytics questions.
Each agent specializes in a different domain (players, matches, standings, predictions) with the Manager
agent routing questions to the appropriate specialist and synthesizing the final answer.
"""

import os
import sqlite3
from typing import Optional
from dotenv import load_dotenv

# ROCKY: Import CrewAI components
# WHY: CrewAI provides the framework for managing agent orchestration, tasks, and hierarchical processes
from crewai import Agent, Crew, Task, Process
from crewai.tools import tool

# ROCKY: Import LangChain Groq for LLM
# WHY: Groq provides low-latency, high-throughput LLM inference; llama-3.3-70b is powerful for reasoning
from crewai import LLM

# ROCKY: Import pandas for readable SQL result formatting
# WHY: Pandas DataFrames display SQL results in a human-readable table format for better agent understanding
import pandas as pd

# Load environment variables from .env file
load_dotenv()

# ROCKY: Disable LiteLLM cache and set logging to ERROR
# WHY: Groq API doesn't support cache_breakpoint parameter; disabling prevents incompatibility errors.
# Setting LITELLM_LOG to ERROR reduces noise from verbose logging during crew execution.
os.environ["LITELLM_CACHE"] = "False"
os.environ["LITELLM_LOG"] = "ERROR"

# ============================================================================
# LLM SETUP
# ============================================================================

# ROCKY: Initialize Groq LLM for all agents
# WHY: Using same LLM instance ensures consistency across all agents and reduces API calls.
# Groq's llama-3.3-70b offers excellent reasoning for complex sports analytics questions.
# cache=False prevents cache_breakpoint errors from Groq API incompatibility.
llm = LLM(
    model="groq/llama-3.3-70b-versatile",
    api_key=os.getenv("GROQ_API_KEY"),
    cache=False
)
# ============================================================================
# SQL TOOL DEFINITION
# ============================================================================


@tool("SQL Database Tool")
def sql_tool(query: str) -> str:
    """
    Execute SQL query on pl_data.db and return formatted results.
    
    ROCKY: This tool bridges agents to the database.
    WHY: Agents need direct database access to retrieve accurate, up-to-date Premier League data.
    The tool handles connection management and result formatting automatically.
    
    Args:
        query: SQL query string to execute
        
    Returns:
        Formatted string representation of query results
    """
    try:
        # ROCKY: Use context manager for safe connection handling
        # WHY: Ensures database connection is closed even if errors occur
        conn = sqlite3.connect("pl_data.db")
        
        # ROCKY: Use pandas to read SQL for automatic type handling
        # WHY: Pandas intelligently converts SQL results to appropriate Python types and formats nicely
        df = pd.read_sql(query, conn)
        conn.close()
        
        # ROCKY: Return as string with index for readability
        # WHY: Agents work with text; formatted output helps them parse and reason about data
        return df.to_string()
    except Exception as e:
        # ROCKY: Return error message rather than raising
        # WHY: Agents can read and learn from errors, potentially adjusting their queries
        return f"Database error: {str(e)}"


# ============================================================================
# AGENT DEFINITIONS
# ============================================================================

# ROCKY: Manager Agent - orchestrator role
# WHY: Hierarchical process requires a manager to route questions and synthesize answers.
# No tools for the manager intentionally; it makes routing decisions based on question content.
manager_agent = Agent(
    role="Premier League Analytics Director",
    goal="Route questions to the correct specialist agent and synthesize their findings into a comprehensive final answer",
    backstory=(
        "You are an expert Premier League analyst with deep knowledge of all aspects of the sport. "
        "Your role is to understand what type of question is being asked, delegate to the appropriate specialist, "
        "and combine their insights into a coherent final answer. "
        "You have specialists for: player statistics, match analysis, league standings, and match predictions."
    ),
    llm=llm,
    verbose=True,
    # ROCKY: Manager has no tools - only uses reasoning to route
    # WHY: Prevents manager from accidentally executing queries; keeps it focused on orchestration
    tools=[],
)

# ROCKY: Player Agent - player statistics specialist
# WHY: Handles all player-level questions (individual performance, comparisons, rankings)
player_agent = Agent(
    role="Player Statistics Specialist",
    goal="Answer all questions about individual player performance, statistics, and comparisons using Premier League data",
    backstory=(
        "You are an expert in player statistics and performance analysis. "
        "You have deep knowledge of the player_xg and top_scorers tables, which contain comprehensive statistics "
        "including goals, assists, expected goals (xG), expected assists (xA), non-penalty xG (npxG), "
        "shot counts, key passes, xG chain, and xG buildup. "
        "You provide detailed, data-driven answers about player performance and comparisons."
    ),
    llm=llm,
    verbose=True,
    # ROCKY: Player agent gets SQL tool for database access
    # WHY: Must query player_xg and top_scorers tables to answer questions
    tools=[sql_tool],
)

# ROCKY: Match Agent - fixture and match specialist
# WHY: Handles all match-level questions (individual games, tactical analysis, historical records)
match_agent = Agent(
    role="Match Analysis Specialist",
    goal="Answer all questions about specific matches, fixtures, and match-level statistics",
    backstory=(
        "You are a match analysis expert specializing in fixture data and in-game statistics. "
        "You have access to fixtures (match schedules), match_xg (expected goals by team), "
        "and fixture_stats (possession, shots, corners, and other match metrics). "
        "You provide detailed insights into individual matches, team performance in specific games, "
        "and tactical statistics like possession and shot distribution."
    ),
    llm=llm,
    verbose=True,
    # ROCKY: Match agent gets SQL tool
    # WHY: Must query fixtures, match_xg, and fixture_stats tables for match information
    tools=[sql_tool],
)

# ROCKY: Standings Agent - league table specialist
# WHY: Handles all season-level questions (points, positions, comparisons, form trends)
standings_agent = Agent(
    role="League Table Specialist",
    goal="Answer all questions about Premier League standings, team rankings, and season-long performance",
    backstory=(
        "You are an expert in league standings and team performance analysis. "
        "You have access to the standings table (with rank, points, won/drawn/lost records) "
        "and team_stats (comprehensive team-level statistics). "
        "You provide insights into team positions, goal differentials, win-loss patterns, "
        "and comparative team performance throughout the season."
    ),
    llm=llm,
    verbose=True,
    # ROCKY: Standings agent gets SQL tool
    # WHY: Must query standings and team_stats tables for league information
    tools=[sql_tool],
)

# ROCKY: Prediction Agent - match outcome specialist
# WHY: Handles predictive questions using xG, team form, home advantage, and current standings
prediction_agent = Agent(
    role="Match Prediction Specialist",
    goal="Predict match outcomes using expected goals (xG), team form, home advantage, and player data",
    backstory=(
        "You are an expert at predicting Premier League match outcomes using advanced analytics. "
        "You combine expected goals (xG) data, team form from standings and recent fixtures, "
        "home advantage statistics, and player performance data to make informed predictions. "
        "You use the fixtures, match_xg, fixture_stats, standings, and player_xg tables "
        "to build comprehensive prediction models. You explain the reasoning behind your predictions clearly."
    ),
    llm=llm,
    verbose=True,
    # ROCKY: Prediction agent gets SQL tool
    # WHY: Must access all relevant tables (fixtures, match_xg, standings, player_xg) for predictions
    tools=[sql_tool],
)

# ============================================================================
# TASK DEFINITIONS
# ============================================================================


def create_tasks(user_question: str):
    """
    Create tasks for all agents based on the user's question.
    
    ROCKY: This function generates dynamic tasks for the crew.
    WHY: Tasks must be created with the specific user question so each agent knows what to analyze.
    """
    
    # ROCKY: Manager task - analyze and delegate
    # WHY: Manager must first understand the question and route it appropriately before specialist agents work
    manager_task = Task(
        description=(
            f"Analyze this Premier League analytics question and determine which specialist(s) should answer it: "
            f"\n\n'{user_question}'\n\n"
            f"Identify whether this is about: players, matches, standings, or predictions. "
            f"Provide clear routing instructions for the appropriate specialist agent(s)."
        ),
        agent=manager_agent,
        # ROCKY: Expected output describes routing logic
        # WHY: Helps manager think through delegation systematically
        expected_output="Clear analysis of question type and routing instructions to specialist agents",
    )

    # ROCKY: Player specialist task
    # WHY: Runs in parallel with other specialists once manager routes to them
    player_task = Task(
        description=(
            f"Answer this Premier League question using player statistics and performance data: "
            f"\n\n'{user_question}'\n\n"
            f"Use SQL queries to access player_xg and top_scorers tables. "
            f"Provide specific data points, comparisons, and insights about player performance."
        ),
        agent=player_agent,
        expected_output="Detailed answer about player statistics with specific data evidence",
    )

    # ROCKY: Match specialist task
    match_task = Task(
        description=(
            f"Answer this Premier League question using match and fixture data: "
            f"\n\n'{user_question}'\n\n"
            f"Use SQL queries to access fixtures, match_xg, and fixture_stats tables. "
            f"Provide specific match details, tactical analysis, and performance metrics."
        ),
        agent=match_agent,
        expected_output="Detailed answer about matches with specific fixture and tactical data",
    )

    # ROCKY: Standings specialist task
    standings_task = Task(
        description=(
            f"Answer this Premier League question using league standings and team statistics: "
            f"\n\n'{user_question}'\n\n"
            f"Use SQL queries to access standings and team_stats tables. "
            f"Provide rankings, points, win-loss records, and comparative team analysis."
        ),
        agent=standings_agent,
        expected_output="Detailed answer about league standings with specific team statistics",
    )

    # ROCKY: Prediction specialist task
    prediction_task = Task(
        description=(
            f"Answer this Premier League question with match predictions and predictive analysis: "
            f"\n\n'{user_question}'\n\n"
            f"Use SQL queries to access fixtures, match_xg, fixture_stats, standings, and player_xg tables. "
            f"Provide predictions based on xG, team form, home advantage, and player data. "
            f"Explain your reasoning and confidence in the predictions."
        ),
        agent=prediction_agent,
        expected_output="Match predictions and predictive analysis with data-driven reasoning",
    )

    return manager_task, player_task, match_task, standings_task, prediction_task


# ============================================================================
# CREW SETUP
# ============================================================================

def create_crew(user_question: str) -> Crew:
    """
    Create a crew with hierarchical process for analyzing the user's question.
    
    ROCKY: Crew combines agents, tasks, and process.
    WHY: Hierarchical process ensures manager controls flow and synthesizes final answer,
    while specialist agents work on their domains in parallel (when applicable).
    
    Args:
        user_question: The user's Premier League analytics question
        
    Returns:
        Configured Crew instance ready to kickoff
    """
    
    # ROCKY: Generate tasks dynamically based on question
    manager_task, player_task, match_task, standings_task, prediction_task = create_tasks(
        user_question
    )

    # ROCKY: Create crew with hierarchical process
    # WHY: Hierarchical process = manager makes routing decision, then coordinates specialists.
    # This ensures intelligent delegation rather than just running all agents on all questions.
    crew = Crew(
        agents=[
            manager_agent,
            player_agent,
            match_agent,
            standings_agent,
            prediction_agent,
        ],
        tasks=[
            manager_task,
            player_task,
            match_task,
            standings_task,
            prediction_task,
        ],
        # ROCKY: Use hierarchical process with manager as orchestrator
        # WHY: Prevents agents from running in isolation; ensures coordinated analysis
        process=Process.hierarchical,
        manager_llm=llm,
        # ROCKY: Verbose=True shows agent thinking and reasoning
        # WHY: Transparency into decision-making helps debug and understand agent behavior
        verbose=True,
    )

    return crew


# ============================================================================
# MAIN FUNCTION
# ============================================================================

def main():
    """
    Main function to interact with the Premier League Analytics Crew.
    
    ROCKY: Entry point for the application.
    WHY: Allows users to ask questions in a loop; crew processes each and returns analysis.
    """
    
    print("=" * 80)
    print("Premier League Analytics Crew - Powered by CrewAI & Groq")
    print("=" * 80)
    print("Ask any question about Premier League analytics, players, matches, or predictions.")
    print("Type 'exit' to quit.\n")

    # ROCKY: Continuous question loop
    # WHY: Users can ask multiple questions in one session without restarting
    while True:
        user_question = input("\nYour question: ").strip()

        # ROCKY: Exit condition
        # WHY: Graceful way to end the session
        if user_question.lower() == "exit":
            print("Goodbye!")
            break

        # ROCKY: Skip empty inputs
        # WHY: Empty questions can cause issues; prompt user again
        if not user_question:
            print("Please enter a question.")
            continue

        print("\n" + "=" * 80)
        print("Crew Processing Your Question...")
        print("=" * 80 + "\n")

        # ROCKY: Create crew for this specific question
        # WHY: Fresh crew for each question ensures clean state and proper task generation
        crew = create_crew(user_question)

        # ROCKY: Execute crew and capture result
        # WHY: kickoff() runs the hierarchical process and returns final synthesis
        try:
            result = crew.kickoff()
            print("\n" + "=" * 80)
            print("FINAL ANSWER FROM CREW")
            print("=" * 80)
            print(result)
            print("=" * 80 + "\n")
        except Exception as e:
            # ROCKY: Catch and display errors
            # WHY: Prevents crashes; helps users understand what went wrong
            print(f"Error processing question: {str(e)}")
            print("Please try another question.\n")


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    # ROCKY: Check for API key before starting
    # WHY: Fails early with clear message rather than during crew execution
    if not os.getenv("GROQ_API_KEY"):
        print("Error: GROQ_API_KEY environment variable not set.")
        print("Please create a .env file with: GROQ_API_KEY=your_key_here")
        exit(1)

    # ROCKY: Start the main loop
    main()

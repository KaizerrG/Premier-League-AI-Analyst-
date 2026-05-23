import sqlite3
import pandas as pd
from groq import Groq



client = Groq()  # Uses GROQ_API_KEY environment variable

# Database schema
SCHEMA = """
standings: rank, team_name, played, won, drawn, lost, goals_for, goals_against, goal_difference, points
top_scorers: player_name, team_name, goals, assists
fixtures: home_team, away_team, home_goals, away_goals, gameweek, fixture_date, status
fixture_stats: fixture_id, team_name, total_shots, shots_on_goal, possession, expected_goals, goals_prevented, corners, fouls
match_xg: home_team, away_team, home_xg, away_xg, home_goals, away_goals, match_date
player_xg: player_name, team_name, position, games, minutes, goals, assists, xG, xA, npxG, shots, key_passes, xGChain, xGBuildup
"""

# System prompt for Groq
SYSTEM_PROMPT = """You are a Premier League football analyst with access to a SQL database.
Your task is to answer football questions by analyzing data.

Think step by step:
1. Identify what statistics define the concept being asked about
2. Write ONE SQL query to get those stats (for complex concepts like "creative" or "clinical", combine multiple stats)
3. Reason across the results
4. Give a clear answer with explanation

Database schema:
{schema}

When asked to write SQL, respond with ONLY the SQL query, nothing else. No explanations, no markdown, just the query."""


def run_sql(query: str) -> str:
    """Execute SQL query and return results as string"""
    conn = sqlite3.connect("pl_data.db")
    try:
        df = pd.read_sql(query, conn)
        return df.to_string()
    finally:
        conn.close()


def write_sql_query(user_question: str, conversation_history: list) -> str:
    """First Groq call: Write SQL query only"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(schema=SCHEMA)}
    ]
    messages.extend(conversation_history)
    messages.append({
        "role": "user",
        "content": f"Write a SQL query to answer this question: {user_question}\n\nRespond with ONLY the SQL query, nothing else."
    })
    
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        max_tokens=500
    )
    
    return response.choices[0].message.content.strip()


def reason_and_answer(user_question: str, sql_query: str, sql_results: str, conversation_history: list) -> str:
    """Second Groq call: Reason over results and provide answer"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(schema=SCHEMA)}
    ]
    messages.extend(conversation_history)
    messages.append({
        "role": "user",
        "content": f"Question: {user_question}\n\nSQL Query executed: {sql_query}\n\nResults:\n{sql_results}\n\nPlease reason over these results and provide a clear answer with explanation."
    })
    
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        max_tokens=1000
    )
    
    return response.choices[0].message.content.strip()


def query_agent(user_question: str, conversation_history: list = None) -> tuple[str, list]:
    """Main agent function"""
    if conversation_history is None:
        conversation_history = []
    
    # Keep only last 5 exchanges (10 messages)
    if len(conversation_history) > 10:
        conversation_history = conversation_history[-10:]
    
    # Step 1: Groq writes SQL
    print(f"\n🤔 Analyzing question: {user_question}")
    sql_query = write_sql_query(user_question, conversation_history)
    print(f"\n📝 Generated SQL:\n{sql_query}")
    
    # Step 2: Python runs SQL
    print(f"\n⚙️  Executing query...")
    try:
        sql_results = run_sql(sql_query)
        print(f"\n📊 Results:\n{sql_results}")
    except Exception as e:
        sql_results = f"Error executing query: {str(e)}"
        print(f"\n❌ {sql_results}")
    
    # Step 3 & 4: Groq reasons and answers
    print(f"\n🧠 Reasoning over results...")
    final_answer = reason_and_answer(user_question, sql_query, sql_results, conversation_history)
    print(f"\n✅ Answer:\n{final_answer}")
    
    # Update conversation history
    conversation_history.append({"role": "user", "content": user_question})
    conversation_history.append({"role": "assistant", "content": final_answer})
    
    return final_answer, conversation_history


def main():
    """Interactive conversation loop"""
    conversation_history = []
    
    print("🏆 Premier League Football Analyst Agent v2")
    print("=" * 50)
    print("Ask me any Premier League question!")
    print("Type 'quit' to exit\n")
    
    while True:
        user_input = input("You: ").strip()
        
        if user_input.lower() == 'quit':
            print("Goodbye! ⚽")
            break
        
        if not user_input:
            continue
        
        answer, conversation_history = query_agent(user_input, conversation_history)


if __name__ == "__main__":
    main()

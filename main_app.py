import streamlit as st
import sqlite3
import subprocess
import sys

from settings import DATABASE_PATH, PROJECT_ROOT, SEASON_LABEL

# ─────────────────────────────────────────
# LEAGUE CONFIGURATION
# ─────────────────────────────────────────
LEAGUE_MAP = {
    "Premier League": "Premier League",
    "La Liga": "La Liga", 
    "Bundesliga": "Bundesliga",
    "Serie A": "Serie A",
    "Ligue 1": "Ligue 1"
}

# ROCKY: page config must be first streamlit call. always.
st.set_page_config(
    page_title=f"PL {SEASON_LABEL} AI Analyst",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ROCKY: import agent from graph.py. this is the LangGraph multi-agent brain.
# wrapped in try/except so app loads even if graph has import error
try:
    from graph import run_analyst
    AGENT_READY = True
except Exception as e:
    AGENT_READY = False
    AGENT_ERROR = str(e)

# ROCKY: import visualization functions from visualizations.py
try:
    from visualizations import (
        tab_league_table,
        tab_xg_analysis,
        tab_top_scorers_playmakers,
        tab_player_comparison
    )
    VIZ_READY = True
except Exception as e:
    VIZ_READY = False
    VIZ_ERROR = str(e)


# ─────────────────────────────────────────
# ROCKY: helper to get last data refresh time
# reads max fetched_at from standings table
# ─────────────────────────────────────────
def get_last_refresh():
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        result = conn.execute("SELECT MAX(fetched_at) FROM standings").fetchone()
        conn.close()
        if result and result[0]:
            return result[0][:16]
        return "Never"
    except sqlite3.Error:
        return "Unknown"


# ─────────────────────────────────────────
# ROCKY: sidebar navigation
# ─────────────────────────────────────────
with st.sidebar:
    st.markdown(f"## ⚽ PL {SEASON_LABEL}")
    st.markdown("**AI Football Analyst**")
    st.divider()

    # navigation
    page = st.radio(
        "Navigate",
        ["💬 AI Chat", "📊 Analytics Dashboard"],
        label_visibility="collapsed"
    )

    st.divider()

    # ROCKY: show season and last refresh info
    st.markdown(f"**Season:** {SEASON_LABEL}")
    st.markdown(f"**Last refresh:** {get_last_refresh()}")

    st.divider()

    # ROCKY: manual refresh button
    # runs fetch scripts to update data
    if st.button("🔄 Refresh Data", use_container_width=True):
        with st.spinner("fetching latest data from Understat..."):
            try:
                subprocess.run(
                    [sys.executable, str(PROJECT_ROOT / "fetch_all.py")],
                    check=True,
                    cwd=PROJECT_ROOT,
                    capture_output=True,
                    text=True,
                )
                st.cache_data.clear()
                st.success("data updated!")
            except Exception as e:
                detail = str(e)
                if isinstance(e, subprocess.CalledProcessError):
                    detail = (e.stderr or e.stdout or detail).strip()
                st.error(f"Refresh failed: {detail}")

    st.divider()
    st.markdown("*Built with LangGraph + Groq*")
    st.markdown("*Data: Understat*")


# ─────────────────────────────────────────
# ROCKY: PAGE 1 → AI CHAT
# uses LangGraph multi-agent from graph.py
# ─────────────────────────────────────────
if page == "💬 AI Chat":
    st.title("💬 PL AI Analyst")
    st.markdown(f"Ask anything about the {SEASON_LABEL} season.")

    # ROCKY: session state stores conversation history
    # without this chat history disappears on every interaction
    if "messages" not in st.session_state:
        st.session_state.messages = []

    if "conversation_history" not in st.session_state:
        st.session_state.conversation_history = []

    # show agent status
    if not AGENT_READY:
        st.error(f"agent not ready: {AGENT_ERROR}")

    # ROCKY: display all previous messages in chat format
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # ROCKY: chat input at bottom. only active if agent ready.
    question = st.chat_input(
        f"Ask about PL {SEASON_LABEL}...",
        disabled=not AGENT_READY
    )
    question = question or st.session_state.pop("pending_question", None)

    if question:
        # show user message
        with st.chat_message("user"):
            st.write(question)

        st.session_state.messages.append({
            "role": "user",
            "content": question
        })

        # ROCKY: get answer from LangGraph agent
        with st.chat_message("assistant"):
            with st.spinner("analysing..."):
                try:
                    answer = run_analyst(
                        question,
                        st.session_state.conversation_history
                    )
                    st.write(answer)

                    # update conversation history for context
                    st.session_state.conversation_history.append({
                        "role": "user",
                        "content": question
                    })
                    st.session_state.conversation_history.append({
                        "role": "assistant",
                        "content": answer
                    })

                    # keep only last 10 messages in history
                    if len(st.session_state.conversation_history) > 10:
                        st.session_state.conversation_history = \
                            st.session_state.conversation_history[-10:]

                except Exception as e:
                    answer = f"error: {e}"
                    st.error(answer)

        st.session_state.messages.append({
            "role": "assistant",
            "content": answer
        })

    # ROCKY: example questions to help user get started
    if not st.session_state.messages:
        st.markdown("### Try asking:")
        cols = st.columns(2)
        examples = [
            "Who is the top scorer?",
            "Who is the most creative midfielder?",
            "Which team has the best xG?",
            "Compare Salah and Haaland stats",
        ]
        for i, example in enumerate(examples):
            with cols[i % 2]:
                if st.button(example, use_container_width=True):
                    st.session_state.pending_question = example
                    st.rerun()


# ─────────────────────────────────────────
# ROCKY: PAGE 2 → ANALYTICS DASHBOARD
# imports tab functions from visualizations.py
# ─────────────────────────────────────────
elif page == "📊 Analytics Dashboard":
    st.title("📊 Analytics Dashboard")

    if not VIZ_READY:
        st.error(f"visualizations not ready: {VIZ_ERROR}")
    else:
        # ROCKY: League selector dropdown
        selected_league_name = st.selectbox(
            "Select League",
            list(LEAGUE_MAP.keys()),
            index=0
        )
        selected_league = LEAGUE_MAP[selected_league_name]
        
        st.divider()
        
        # ROCKY: 4 tabs. each calls function from visualizations.py
        tab1, tab2, tab3, tab4 = st.tabs([
            "🏆 League Table",
            "⚡ xG Analysis",
            "🥅 Top Scorers & Playmakers",
            "🔄 Player Comparison"
        ])

        with tab1:
            tab_league_table(selected_league)

        with tab2:
            tab_xg_analysis(selected_league)

        with tab3:
            tab_top_scorers_playmakers(selected_league)

        with tab4:
            tab_player_comparison()

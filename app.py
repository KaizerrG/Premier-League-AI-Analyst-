import streamlit as st
from agent import ask

# ROCKY: page config = browser tab title and icon
st.set_page_config(
    page_title="PL Football Analyst",
    page_icon="⚽"
)

# ROCKY: title and description
st.title("⚽ PL 2024/25 Analyst")
st.markdown("Ask anything about the Premier League 2024/25 season.")

# ROCKY: chat history stored in session_state
# session_state = memory that survives between interactions
# without this history disappear every time you ask question
if "messages" not in st.session_state:
    st.session_state.messages = []

# ROCKY: display all previous messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# ROCKY: chat input at bottom of page
# st.chat_input = that box at bottom like chatgpt
question = st.chat_input("Ask about PL 2024/25...")

if question:
    # ROCKY: show user question in chat
    with st.chat_message("user"):
        st.write(question)
    
    # ROCKY: save question to history
    st.session_state.messages.append({
        "role": "user",
        "content": question
    })
    
    # ROCKY: get answer from agent
    with st.chat_message("assistant"):
        with st.spinner("thinking..."):
            answer = ask(question)
        st.write(answer)
    
    # ROCKY: save answer to history
    st.session_state.messages.append({
        "role": "assistant", 
        "content": answer
    })
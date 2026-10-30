import os

import streamlit as st

# On Streamlit Cloud, keys come from "Secrets"; locally they come from .env
try:
    for key_name in ("GEMINI_API_KEY", "DATA_GOV_API_KEY"):
        if key_name in st.secrets:
            os.environ[key_name] = st.secrets[key_name]
except Exception:
    pass

from agent import run_agent  # noqa: E402  (must come after the keys are set)

st.set_page_config(page_title="Farmer Advisory Assistant", page_icon="🌾", layout="centered")

st.title("🌾 Farmer Advisory Assistant")
st.caption(
    "An AI agent that checks live weather and mandi prices, then gives "
    "simple advice in your language."
)

# ---- Sidebar: farmer details ----
with st.sidebar:
    st.header("Your details")
    language = st.selectbox("Language", ["English", "Hindi", "Odia"])
    location = st.text_input("Village / town", value="Rourkela")
    state = st.text_input("State", value="Odisha")
    crop = st.text_input("Crop", value="Potato")
    st.divider()
    st.markdown("**Try asking:**")
    st.markdown("- Should I irrigate this week?\n- Should I sell now or wait?\n- Is it safe to harvest?")

# ---- Chat history ----
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ---- New question ----
question = st.chat_input("Ask your farming question...")

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    full_question = (
        f"Farmer details: location = {location}, state = {state}, crop = {crop}.\n"
        f"Question: {question}\n"
        f"Reply in {language}."
    )

    with st.chat_message("assistant"):
        with st.status("Agent is working...", expanded=True) as status:
            def show_step(text):
                st.write(text)

            answer = run_agent(full_question, on_step=show_step)
            status.update(label="Done", state="complete", expanded=False)
        st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
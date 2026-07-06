import os
import streamlit as st
import requests
import time
import uuid
import logfire
from dotenv import load_dotenv


# Load environment variables explicitly from the root directory
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(dotenv_path=env_path)

# Initialize Logfire
try:
    token = os.getenv("LOGFIRE_TOKEN")
    if not token:
        print("ERROR: LOGFIRE_TOKEN is empty or None!")
    logfire.configure(token=token)
    # logfire.instrument_requests() # Disabled due to OpenTelemetry bug on Windows: MeterProvider.get_meter() got multiple values for argument 'version'
    LOGFIRE_STATUS = "Connected & Tracing"

except Exception as e:
    print(f"Logfire Init Error in UI: {e}")
    LOGFIRE_STATUS = f"Standby (Error: {e})"


# Page Config ----
st.set_page_config(
    page_title = "Enterprise Agentic RAG",
    page_icon = "🤖",
    layout = "wide",
)

# -- AVATARS --
AI_AVATAR = "🤖"
USER_AVATAR = "👤"

# session_state is a temporary memory for user's Streamlit session
# Normally, when you interact with Streamlit(click button, send a message),
# the entire script runs top top to bottom
# Without session_state, all variables would reset
# If the current session_id is new, create a unique id for the user
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
    logfire.info(f"✨ New User Session Created: {st.session_state.session_id}")

# Checks whether the conversation history exists, if not create a empty list
if "messages" not in st.session_state:
    st.session_state.messages = []

# Sidebar
with st.sidebar:
    st.title("🧠 Agent OS")
    st.markdown("---")
    # Show that LOGFIRE is working or not
    st.success(f"Logfire: {LOGFIRE_STATUS}")
    # Basically for each session, a session id is generated
    st.info(f"Memory ID: {st.session_state.session_id[:8]}")
 
    if st.button("🗑️ Clear History and Memory", width="stretch", type="primary"):
        logfire.warn(f"🗑️ Memory Wipe Triggered for session: {st.session_state.session_id}")
        st.session_state.messages = []
        st.session_state.session_id = str(uuid.uuid4())
        st.rerun()

# --- MAIN CHAT ---
st.title("🤖 Enterprise Agentic Assistant")

# Display History
for message in st.session_state.messages:
    # We display the session history along with the avatar
    avatar = AI_AVATAR if message["role"] == "assistant" else USER_AVATAR
    with st.chat_message(message["role"], avatar = avatar):
        st.markdown(message["content"])

# Chat Input - user query becomes prompt
if prompt := st.chat_input("Ask about your documentation..."):
    # START TRACE: User Interaction - First everything is stored in logfire and sent to backend
    with logfire.span("User Chat Interaction", user_query = prompt, session_id = st.session_state.session_id):
        # Add whatever user has asked in chat, in messages - Only for Streamlit UI
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # Show the avatar and the prompt/user query
        with st.chat_message("user", avatar = USER_AVATAR):
            st.markdown(prompt)

        # Assistant Response - First create an empty assistant bubble
        with st.chat_message("assistant", avatar = AI_AVATAR):
            with st.status("🔍 Agent is thinking...", expanded = True) as status:
                try:
                    # Distributed Trace: Calling Backend
                    with logfire.span("Calling RAG Backend"):
                        # Get Backend URL from env, or default to local if not set
                        base_url = os.getenv("BACKEND_URL", "http://localhost:8000")

                        # http://localhost:8000/query - This is the endpoint the FastAPI exposes, it hits 
                        # @app.post("/query")
                        url = f"{base_url}/query"
                        payload = {"q": prompt, "thread_id": st.session_state.session_id}

                        # Send HTTP Post Request to backend (FastAPI) - if the backend doesn't respond in 60 seconds, 
                        # show timeout instead of waiting forever
                        response = requests.post(url, json = payload, timeout = 60)

                        # Convert the response received from RAG/Backend to JSON format
                        data = response.json()

                    # Show Planning Steps from Backend
                    plan = data.get("thought_process", [])
                    for step in plan:
                        st.write(f"📋 {step}")

                    # Show Status
                    status_msg = data.get("status", "Processing...")
                    st.write(f"Status: {status_msg}")

                    status.update(label = "✅ Answer Synthesized", state = "complete", expanded = False)

                    # Show sources (Retrieved Context) ---
                    sources = data.get("sources", [])
                    if sources:
                        with st.expander("📄 View Retrieved Context"):
                            for i, source in enumerate(sources):
                                # Create a preview title for each chunk
                                preview = source[:100].replace("\n", " ") + "..."
                                with st.expander(f"Context {i+1}: {preview}"):
                                    st.info(source)

                except Exception as e:
                    logfire.error(f"❌ UI-Backend Connection Failed: {e}")
                    status.update(label="❌ Connection Failed", state="error")
                    st.error(f"Backend Error: {str(e)}")
                    st.stop()

            # Final Answering Streaming - Reserve empty place for answering
            answer_placeholder = st.empty()

            # If response is received from backend, then answer else "No response"
            full_answer = data.get("answer", "No response.")

            # These steps are done to show user that answer is generating step by step
            curr_text = ""
            for char in full_answer:
                curr_text += char
                answer_placeholder.markdown(curr_text + "▌")
                time.sleep(0.005)

            answer_placeholder.markdown(full_answer)
            st.session_state.messages.append({"role": "assistant", "content": full_answer})
            logfire.info("✅ Chat cycle completed successfully.")




#                                    ┌──────────────────────────────┐
#                                    │        User Opens App        │
#                                    └──────────────┬───────────────┘
#                                                   │
#                                                   ▼
#                               ┌────────────────────────────────────┐
#                               │ Load .env Variables                │
#                               │ • LOGFIRE_TOKEN                    │
#                               │ • BACKEND_URL                      │
#                               └────────────────┬───────────────────┘
#                                                │
#                                                ▼
#                               ┌────────────────────────────────────┐
#                               │ Initialize Logfire                 │
#                               │ configure(token)                   │
#                               └────────────────┬───────────────────┘
#                                                │
#                                                ▼
#                               ┌────────────────────────────────────┐
#                               │ Configure Streamlit Page           │
#                               │ Title, Icon, Layout                │
#                               └────────────────┬───────────────────┘
#                                                │
#                                                ▼
#                      ┌────────────────────────────────────────────────────┐
#                      │ Does session_id exist in session_state?            │
#                      └───────────────┬───────────────────────┬────────────┘
#                                      │No                     │Yes
#                                      ▼                       ▼
#                      Generate UUID using uuid4()      Reuse Existing UUID
#                                      │
#                                      ▼
#                      Store session_id in session_state
#                                      │
#                                      ▼
#                  ┌──────────────────────────────────────────────┐
#                  │ Does messages list exist?                    │
#                  └───────────────┬───────────────────┬──────────┘
#                                  │No                 │Yes
#                                  ▼                   ▼
#                       Create Empty List        Reuse Existing Chat
#                                  │
#                                  ▼
#                 ┌──────────────────────────────────────────────┐
#                 │ Build Sidebar                               │
#                 │ • Logfire Status                            │
#                 │ • Memory ID                                 │
#                 │ • Clear History Button                      │
#                 └────────────────┬─────────────────────────────┘
#                                  │
#                     User clicks "Clear History"?
#                                  │
#                  ┌───────────────┴───────────────┐
#                  │No                             │Yes
#                  ▼                               ▼
#          Continue Normally             Clear messages[]
#                                        Generate NEW UUID
#                                        Rerun Streamlit
#                                                │
#                                                ▼
#                                         Fresh Conversation

# ══════════════════════════════════════════════════════════════════════

#                       MAIN CHAT INTERFACE

#                 ┌──────────────────────────────────────────────┐
#                 │ Display Previous Chat History                │
#                 │ Loop through session_state.messages          │
#                 └────────────────┬─────────────────────────────┘
#                                  │
#                                  ▼
#                   ┌────────────────────────────────────┐
#                   │ User enters a question             │
#                   │ st.chat_input()                    │
#                   └────────────────┬───────────────────┘
#                                    │
#                                    ▼
#                    ┌────────────────────────────────────┐
#                    │ Start Logfire Trace                │
#                    │ Store Session ID + User Query      │
#                    └────────────────┬───────────────────┘
#                                     │
#                                     ▼
#                  ┌──────────────────────────────────────────────┐
#                  │ Save User Message                            │
#                  │ session_state.messages.append()              │
#                  └────────────────┬─────────────────────────────┘
#                                   │
#                                   ▼
#                  ┌──────────────────────────────────────────────┐
#                  │ Display User Chat Bubble                     │
#                  └────────────────┬─────────────────────────────┘
#                                   │
#                                   ▼
#                  ┌──────────────────────────────────────────────┐
#                  │ Create Assistant Chat Bubble                 │
#                  │ Show "Agent is thinking..."                  │
#                  └────────────────┬─────────────────────────────┘
#                                   │
#                                   ▼
#                  ┌──────────────────────────────────────────────┐
#                  │ Read BACKEND_URL from .env                   │
#                  │ Default → http://localhost:8000              │
#                  └────────────────┬─────────────────────────────┘
#                                   │
#                                   ▼
#                  ┌──────────────────────────────────────────────┐
#                  │ Create Endpoint                              │
#                  │ http://localhost:8000/query                  │
#                  └────────────────┬─────────────────────────────┘
#                                   │
#                                   ▼
#                  ┌──────────────────────────────────────────────┐
#                  │ Create Payload                              │
#                  │                                             │
#                  │ {                                           │
#                  │   q : prompt                                │
#                  │   thread_id : session_id                    │
#                  │ }                                           │
#                  └────────────────┬─────────────────────────────┘
#                                   │
#                                   ▼
#                  ┌──────────────────────────────────────────────┐
#                  │ POST Request to FastAPI Backend              │
#                  │ requests.post()                              │
#                  └────────────────┬─────────────────────────────┘
#                                   │
#                                   ▼
# ══════════════════════ BACKEND (FastAPI + LangGraph) ══════════════════════

#                         Planner Node
#                               │
#                               ▼
#                     Retriever Node (if technical)
#                               │
#                               ▼
#                      Responder / LLM Node
#                               │
#                               ▼
#                       Return JSON Response

# ══════════════════════════════════════════════════════════════════════════════

#                                   │
#                                   ▼
#                  ┌──────────────────────────────────────────────┐
#                  │ Convert JSON Response                        │
#                  │ response.json()                              │
#                  └────────────────┬─────────────────────────────┘
#                                   │
#                                   ▼
#           ┌─────────────────────────────────────────────────────────┐
#           │ Extract Response Fields                                 │
#           │                                                         │
#           │ • plan                                                  │
#           │ • status                                                │
#           │ • documents                                             │
#           │ • final_answer                                          │
#           └────────────────┬────────────────────────────────────────┘
#                            │
#                            ▼
#              ┌────────────────────────────────────────────┐
#              │ Display Planning Steps                     │
#              │ 📋 Planner                                │
#              │ 📋 Retrieved Context                      │
#              │ 📋 Cache Hit                              │
#              └────────────────┬──────────────────────────┘
#                               │
#                               ▼
#              ┌────────────────────────────────────────────┐
#              │ Display Current Status                     │
#              │ Example: "Response Generated"              │
#              └────────────────┬──────────────────────────┘
#                               │
#                               ▼
#              ┌────────────────────────────────────────────┐
#              │ Show Retrieved Documents                   │
#              │ Expanders for each retrieved chunk         │
#              └────────────────┬──────────────────────────┘
#                               │
#                               ▼
#              ┌────────────────────────────────────────────┐
#              │ Stream Final Answer Character-by-Character │
#              │ Like ChatGPT typing effect                 │
#              └────────────────┬──────────────────────────┘
#                               │
#                               ▼
#              ┌────────────────────────────────────────────┐
#              │ Save Assistant Response                    │
#              │ session_state.messages.append()            │
#              └────────────────┬──────────────────────────┘
#                               │
#                               ▼
#              ┌────────────────────────────────────────────┐
#              │ Log Success to Logfire                     │
#              │ "Chat cycle completed successfully"        │
#              └────────────────┬──────────────────────────┘
#                               │
#                               ▼
#                      Wait for Next User Question
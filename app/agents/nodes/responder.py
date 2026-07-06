import logfire
from app.agents.state import AgentState
from app.gateway import portkey_client, extract_cache_status

def generate_node(state: AgentState):
    """
    Synthesizes a response using both Documentation Context AND Conversation History.
    Uses the native Portkey client (not LangChain) so we can read the
    x-portkey-cache-status response header and surface Cache: Hit in the UI.
    """
    query = state["current_query"]

    history_str = ""
    for msg in state["messages"][:-1]:
        role = "User" if msg["role"] == "user" else "Assistant"
        history_str += f"{role}: {msg['content']}\n"

    user_msg = state["messages"][-1]["content"] if state["messages"] else ""

    if query == "CONVERSATIONAL":
        logfire.info("Generating conversational response using memory.")
        prompt = f"""
        You are a friendly and helpful Enterprise AI Assistant.
        Answer the user's latest message using the CONVERSATION history below.

        CONVERSATION HISTORY:
        {history_str}

        LATEST MESSAGE:
        {user_msg}
        """
    else:
        logfire.info("Generating technical RAG response")
        # Suppose doc 1,2,3,4,5 is being passed. doc 1-9000 chars, doc 2 - 14000 chars
        # 9000 + 14000 = 24000 < 25000, so it will be passed to LLM. Now when we add doc 3
        # 3000 chars, total = 27000 > 25000, it breaks after logging. Only doc 1 and 2 (24k chars) will be passed to LLM
        max_context_chars = 25000
        full_context = ""

        for doc in state["documents"]:
            if len(full_context) + len(doc) < max_context_chars:
                full_context += doc + "\n\n"
            else:
                logfire.warning("Context truncated yo fit Groq TPM limits.")
                break
        
        prompt = f"""
        You are a Senior Technical Architect.
        Answe the question using the TECHNICAL CONTEXT provided.

        TECHNICAL CONTEXT:
        {full_context}

        CONVERSATION HISTORY:
        {history_str}

        USER QUESTION:
        {user_msg}
        """

    with logfire.span("✍️ LLM Synthesis"):
        try:
            # Sending prompts to Portkey
            response = portkey_client.chat.completions.create(
                messages = [{"role": "user", "content": prompt}],
                temperature = 0.1
            )

            # Store the LLM response
            content = response.choices[0].message.content
            # Check the cache status --- HIT or MISS
            cache_status = extract_cache_status(response)
            is_cache_hit = cache_status == "HIT"

            # If the same question is asked before, response is generated using the stored answer 
            # immediately in less time 
            if is_cache_hit:
                logfire.info("⚡ Gateway Cache Hit - response served from Portkey cache.")
                plan_update = state["plan"] + ["Cache: Hit "]
                status = "Cache hit - instant response"
            else:
                logfire.info("✅ Response synthesised via LLM.")
                plan_update = state["plan"]
                status = "Response Generated"
            
            # This state will be retured by LLM
            return {
                "final_answer": content,
                "status": status,
                "plan": plan_update,
                "messages": [{"role": "assistant", "content": content}]
            }


        except Exception as e:
            logfire.error(f"LLM Generation failed: {e}")
            raise e

#                            generate_response(state)
#                                      │
#                                      ▼
#                      Read AgentState (query, docs, messages)
#                                      │
#                                      ▼
#                 ┌──────────────── Is Query == "CONVERSATIONAL"? ────────────────┐
#                 │                                                               │
#               YES                                                              NO
#                 │                                                               │
#                 ▼                                                               ▼
#  Build Prompt using Conversation History                     Build Prompt using Documents
#         + Latest User Message                             + Conversation History
#                 │                                          + Latest User Question
#                 │                                                               │
#                 └──────────────────────────────┬────────────────────────────────┘
#                                                │
#                                                ▼
#                                    Send Prompt to Portkey
#                                                │
#                                                ▼
#                                         Groq LLM Processes
#                                                │
#                                                ▼
#                                    Receive Response + Headers
#                                                │
#                                                ▼
#                                Check Portkey Cache Status
#                                                │
#                          ┌─────────────────────┴─────────────────────┐
#                          │                                           │
#                     Cache HIT                                   Cache MISS
#                          │                                           │
#                          ▼                                           ▼
#              Add "Cache Hit" to Plan                      Normal Plan
#              Faster Response                              Fresh LLM Response
#                          │                                           │
#                          └─────────────────────┬─────────────────────┘
#                                                │
#                                                ▼
#                               Return Updated AgentState
from app.agents.state import AgentState
from app.gateway import get_langchain_llm
import logfire

# Portkey-backed LLM: fallback + cache + retry — same .invoke() interface as ChatGroq
llm = get_langchain_llm(feature = "planner")

# This function will decide if the user query is conversation or technical
def planner_node(state: AgentState):
    """
    The Planner determines if a search is needed based on the ENTIRE conversation
    """
    # First get the conversational history (excluding the latest message)
    history = ""
    for msg in state["messages"][:-1]:
        role = "User" if msg["role"] == "user" else "Assistant"
        history += f"{role}: {msg['content']}\n"

    user_message = state["messages"][-1]["content"] if state["messages"] else ""

    prompt = f"""
    You are an intelligent Assistant Planner.
    Analyze the conversation history and the latest user message.

    CONVERSATION HISTORY: 
    {history}

    LATEST MESSAGE: 
    {user_message}

    Task:
    1. If the latest message is a greeting (hi, hello) or a question that can be answered using 
    ONLY the conversation history above (e.g., "What is my name"), respond with 'CONVERSATIONAL'.
    2. If it is a technical question about Kubernetes, Intel, or Networking that requires fresh documentation,
    output a refined search query.

    Output ONLY 'CONVERSATIONAL or the search query.
    """

    # We print here what is the decision of the Planner Node - Technical or Conversational
    with logfire.span("🧠 Planner Decision"):
        decision = llm.invoke(prompt).content.strip()
        logfire.info(f"Intent identified: {decision}")
    
    if decision == "CONVERSATIONAL":
        return {
            "current_query": "CONVERSATIONAL",
            "status": "Handling Conversationally (using memory)....",
            "plan": ["Intent: Conversational/Memory", "Retrieval: Skipped"]
        }
    return {
            "current_query": decision,
            "status": f"Technical research needed. Searching for: {decision}",
            "plan": ["Intent: Technical", f"Search Term: {decision}"]
    }
    



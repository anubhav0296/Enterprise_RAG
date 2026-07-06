import logfire
from app.agents.state import AgentState
from app.services.retrieval.qdrant_service import search_enterprise_knowledge
from app.services.retrieval.ranking_service import rerank_documents

def retrieve_node(state: AgentState):
    """
    Performs vector search and semantic reranking for technical queries.
    """
    query = state["current_query"]

    # Standard retrieval Logic
    with logfire.span("Knowledge Retrieval"):
        logfire.info(f"Searching Qdrant for {query}")
        raw_results = search_enterprise_knowledge(query, limit = 15)
        logfire.info(f"Retrieved {len(raw_results)} candidates from Vector DB")

        # Storing the retrievd chunks in doc_chunks, basically extracting the CONTENT of it
        doc_contents = [doc['content'] for doc in raw_results]

        # We are now reranking the retrieved docs/chunks
        with logfire.span("Semantic Reranking"):
            reranked_content = rerank_documents(query, doc_contents, top_n=5)
            logfire.info("Reranking complete. Kept top 5 most relevant chunks.")

        formatted_docs = [f"CONTENT: {doc}" for doc in reranked_content]

    # Retriever node is passing the state information to Responder Node further
    return {
        "documents": formatted_docs,
        "status": f"Found technical context.",
        "plan": state["plan"] + ["Context Retrievd"]
    }


        #             retrieve_node(state)
        #                    │
        #                    ▼
        #        Read current_query from state
        #                    │
        #                    ▼
        #          Search Vector Database (Qdrant)
        #                    │
        #                    ▼
        #    Retrieve Top 15 Similar Document Chunks
        #                    │
        #                    ▼
        #       Extract only the document contents
        #                    │
        #                    ▼
        #   Semantic Reranking using Cross Encoder
        #                    │
        #                    ▼
        #     Keep only Top 5 Relevant Chunks
        #                    │
        #                    ▼
        #      Format chunks for the LLM Prompt
        #                    │
        #                    ▼
        #   Return Updated AgentState to Next Node
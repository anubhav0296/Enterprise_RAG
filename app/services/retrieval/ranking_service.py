import time
import logfire
from flashrank import Ranker, RerankRequest

# Lazy initialization - Ranker is loaded on first use to ensure logfire.configure() has run
# Don't load the AI model when the application starts, load it when someone actually gives a query
_ranker = None

# This function ensures that the model is loaded only once
def _get_ranker() -> Ranker:
    """
    Initializes the FlashRank engine lazily. 
    FlashRank uses a local ONNX model (ms-marco-MiniLM-L-6-v2) for ultra-fast reranking.
    """
    global _ranker
    if _ranker is None:
        logfire.info("Initializing FlashRank Model (TinyBERT) locally...")
        try:
            # We use a specific cache directory to avoid permission issues in production
            # When FlashRank downloads it's ONNX model, it stores in this folder
            # Next time, it simply loads the model, instead of downloading again
            _ranker = Ranker(cache_dir = "/temp/flashrank")
        except Exception:
            _ranker = Ranker()
    return _ranker

# This function decides out of the retrievd chunks, what are the top ranked chunks (after reranking)
def rerank_documents(query: str, documents: list[str], top_n: int = 5) -> list[str]:
    """
    Refines retrieval results by re-scoring documents against the query semantically.
    
    Why FlashRank? 
    Standard vector search (Cosine Similarity) is fast but mathematically "fuzzy."
    FlashRank uses a Cross-Encoder approach which is much more precise but usually slow.
    FlashRank solves this by using highly optimized, quantized ONNX models locally.
    """
    # If Qdrant finds nothing, no need to rerank
    if not documents:
        return []
    
    start_time = time.time()
    # Sending 15 docs to FlashRank
    logfire.info(f"📡 [Reranker] Sending {len(documents)} docs to FlashRank Cross-Encoder...")

    try:
        # Get the loaded model of FlashRank
        ranker = _get_ranker()
        # FlashRank expects a list of dictionaries with "id" and "text"--[{"id":0,"text":"..."}], 
        # but Qdrant returns like this - ["kubernetes", "Pods...", "HPA..."]
        # FlashRank labels each document
        passages = [
            {"id": i, "text": doc}
            for i, doc in enumerate(documents)
        ]

        # Packages the query and retrieved document into 1, so it can be passed to Reranker
        request = RerankRequest(query = query, passages = passages)
        # FlashRank takes query + doc 1, gives score 0.97
        # query + doc 2, score = 0.87, unlike Vector search FlashRank actually understands 
        # query + doc and gives score. Hence, it is called Cross-encoder
        results = ranker.rerank(request)

        # Results are returned sorted by highest semantic score first
        
        reranked_docs = []
        for res in results[:top_n]:
            reranked_docs.append(res["text"])

        duration = time.time()
        # Useful to know how confident the reranker was
        top_score = results[0]["score"] if results else "N/A"
        logfire.info(f"[Reranker] Done in {duration:.2f}s. Top semantic score: {top_score}")
        
        return reranked_docs

    except Exception as e:
        logfire.error(f"❌ [Reranker] Semantic Reranking Failed: {e}")
        # Fallback to the original Qdrant order to ensure the user still gets an answer
        return documents[:top_n]
    

    #                  User Question
    #                    │
    #                    ▼
    #    Qdrant returns Top 15 candidate documents
    #                    │
    #                    ▼
    #      Is the document list empty?
    #              │              │
    #            Yes              No
    #              │              ▼
    #         Return []     Load/Re-use FlashRank model
    #                             │
    #                             ▼
    #      Convert documents into {id, text} format
    #                             │
    #                             ▼
    #    Create RerankRequest (query + passages)
    #                             │
    #                             ▼
    #   FlashRank Cross-Encoder scores each document
    #                             │
    #                             ▼
    #   Results sorted by highest semantic score
    #                             │
    #                             ▼
    #          Select only the top 5 documents
    #                             │
    #                             ▼
    #       Return reranked documents to the LLM
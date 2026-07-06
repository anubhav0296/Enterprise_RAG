# """Embedding utilities for converting text chunks into vector representations for retrieval."""

# import vertexai
# from vertexai.language_models import TextEmbeddingModel
# from app.config import settings

# model = None
# # Instead of passing the chunks all at once or one by one, we pass them in batches
# # If 100 chunks - 100 API calls for Embeddings, so we pass (Chunk 1-20) in one batch
# # Then 20-40,...So we pass them in batches of 20. Then total 5 API calls instead of 100
# BATCH_SIZE = 50

# # Get the Embeddings Model from Vertex AI
# def get_embedding_model():
#     global model
#     if model is None:
#         #Initialize Vertex AI before loading the model
#         vertexai.init(project = settings.PROJECT_ID, location = settings.LOCATION)
#         # Reverting to TextEmbeddingModel for stability
#         model = TextEmbeddingModel.from_pretrained("text-embedding-004")
#     return model

# # Here we are embedding the user query using the Vertex AI Model
# def embed_query(query: str):
#     """Embed a single query string using the stable Vertex AI API."""
#     model = get_embedding_model()
#     embeddings = model.get_embeddings([query])
#     return embeddings

# # Here we are embedding the chunks in batches of 20, to reduce the API calls
# def embed_texts(texts: list[str]):
#     """Embed a list of text strings in batches."""
#     model = get_embedding_model()
#     all_embeddings = []

#     for i in range(0, len(texts), BATCH_SIZE):
#         batch = texts[i:i+BATCH_SIZE]
#         embeddings = model.get_embeddings(batch)
#         all_embeddings.extend([e.values for e in embeddings])

#     return all_embeddings

import vertexai
from vertexai.language_models import TextEmbeddingModel
from app.config import settings
import logfire

model = None
BATCH_SIZE = 50
MODEL_NAME = "text-embedding-004"

def get_embedding_model():
    global model
    if model is None:
        try:
            vertexai.init(project=settings.PROJECT_ID, location=settings.LOCATION)
            logfire.info("Vertex AI initialized for embeddings")
            model = TextEmbeddingModel.from_pretrained(MODEL_NAME)
            logfire.info(f"Loaded Vertex AI embedding model: {MODEL_NAME}")
        except Exception as e:
            logfire.error(f"Failed to initialize Vertex AI embedding model: {e}")
            raise RuntimeError(
                "Vertex AI embedding initialization failed. "
                "Check Google ADC credentials, quota project, and that aiplatform.googleapis.com is enabled."
            ) from e
    return model

def embed_query(query: str):
    """Embed a single query string using Vertex AI."""
    model = get_embedding_model()
    embeddings = model.get_embeddings([query])
    return embeddings[0].values

def embed_texts(texts: list[str]):
    """Embed a list of text strings in batches."""
    model = get_embedding_model()
    all_embeddings = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i+BATCH_SIZE]
        embeddings = model.get_embeddings(batch)
        all_embeddings.extend([e.values for e in embeddings])

    return all_embeddings

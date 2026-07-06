"""Chunk extracted text into smaller, paragraph-based segments for embedding and indexing."""

from typing import List
import logfire

def chunk_text(text: str, chunk_size: int = 1500) -> List[str]:
    """
    Simple semantic-ish chunker that splits by paragraphs.
    Ensures chunks do not exceed the specified size.
    """
    with logfire.span("✂️ Text Chunking", text_length = len(text)):
        if not text.strip():
            return []
        
        # Split the entire 20,000 len chunk based on paragraphs, so meaning is not lost
        paragraphs = text.split("\n\n")
        # It holds final chunks - ["chunk1","chunk2","chunk3"]
        chunks = []
        # It will have current chunk and then after some checking it will be appended to chunks
        current_chunk = ""

        # Loop through each paragraphs - p1,p2,p3,p4...
        # Makes sure current_chunk = (p1(900 len) + p2(400 len) + p3(100) < 1500), at the end this 
        # current_chunk gets added to chunks list
        for p in paragraphs:
            if len(current_chunk) + len(p) < chunk_size:
                current_chunk += p + "\n\n"
            else:
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                current_chunk = p + "\n\n"
        
        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        # Makes sure that empty chunks are not added to valid_chunks
        valid_chunks = [c for c in chunks if c.strip()]
        logfire.info(f"✅ Generated {len(valid_chunks)} chunks")
        return valid_chunks
    
    
#                         Large Document
#                            │
#                            ▼
#               Split by Double Newlines (\n\n)
#                            │
#                            ▼
#                   List of Paragraphs
#                            │
#                            ▼
#                Start Building First Chunk
#                            │
#         ┌──────────────────┴──────────────────┐
#         │                                     │
# Paragraph Fits?                         Chunk Full?
#         │                                     │
#         ▼                                     ▼
# Add to Current Chunk                  Save Current Chunk
#         │                                     │
#         └──────────────────┬──────────────────┘
#                            ▼
#                Continue Until All Paragraphs
#                            │
#                            ▼
#               Save Remaining Final Chunk
#                            │
#                            ▼
#                  Remove Empty Chunks
#                            │
#                            ▼
#                  Return List of Chunks
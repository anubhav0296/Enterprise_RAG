# Ingestion Pipeline Function Map

This document summarizes the current ingestion pipeline implemented in the repository.

## 1. Overview

The pipeline takes files from the DATA folder, processes them into text, chunks the text, stores metadata in GCS, creates vector embeddings, and indexes them into Qdrant.

### End-to-end flow

1. Discover files from DATA/true_data, DATA/noisy_data, or a custom directory.
2. Upload the original file to the GCS raw bucket.
3. Parse the file into plain text based on its format.
4. Split the extracted text into chunks.
5. Save processed metadata as JSON in the GCS processed bucket.
6. Generate embeddings in batches.
7. Upsert the chunk vectors into Qdrant.

---

## 2. High-level pipeline view

| Stage | What happens | Main functions |
|---|---|---|
| Input discovery | Scans folders and identifies files | run_universal_ingestion, process_directory |
| Raw storage | Uploads the source file to GCS | upload_to_gcs |
| Parsing | Converts PDF / HTML / TXT / DOCX / PPTX into text | parse_pdf, parse_html, parse_text, parse_office |
| Chunking | Splits text into smaller documents | chunk_text |
| Processed storage | Writes chunked metadata as JSON to GCS | upload_to_gcs |
| Embedding | Converts chunks into vector embeddings | embed_texts |
| Vector DB indexing | Stores vectors and metadata in Qdrant | qdrant_client.upsert |

---

## 3. Drill-down by function

| File | Function | Purpose | Input | Output |
|---|---|---|---|---|
| app/ingestion/processor.py | upload_to_gcs | Uploads a file or JSON payload to GCS | file path or dict, bucket name, blob path | GCS object uploaded |
| app/ingestion/processor.py | process_file | Orchestrates the full per-file workflow | file path, filename, source type | Raw upload, parsed text, chunks, JSON upload, embeddings, Qdrant indexing |
| app/ingestion/processor.py | run_universal_ingestion | Scans a base directory, creates or wipes the Qdrant collection, and starts processing | base directory, optional source type, wipe flag | Processed data for all discovered files |
| app/ingestion/processor.py | process_directory | Iterates through files in a given directory | directory path, source type | Calls process_file for each file |
| app/ingestion/chunking/splitter.py | chunk_text | Splits long text into semantically meaningful paragraph-based chunks | full text string | list of chunk strings |
| app/ingestion/loaders/pdf.py | parse_pdf | Extracts text from PDF files using Google Document AI | PDF file path | extracted text |
| app/ingestion/loaders/pdf.py | process_document_chunk | Sends a PDF byte chunk to Document AI | PDF bytes, processor name | OCR/text result |
| app/ingestion/loaders/html.py | parse_html | Strips HTML noise and extracts readable text | HTML file path | cleaned text |
| app/ingestion/loaders/text.py | parse_text | Reads plain text content from a file | text file path | file contents |
| app/ingestion/loaders/office.py | parse_office | Extracts text from DOCX/PPTX files using Unstructured | office document file path | extracted text |
| app/services/retrieval/embedding.py | get_embedding_model | Loads the Vertex AI embedding model once | none | embedding model |
| app/services/retrieval/embedding.py | embed_query | Embeds a single query string | query text | embedding vector |
| app/services/retrieval/embedding.py | embed_texts | Embeds a list of chunks in batches | list of text chunks | list of embedding vectors |
| app/config.py | Settings | Loads environment variables and config values | environment | settings object |

---

## 4. File-type handling

| File type | Parser used | Notes |
|---|---|---|
| PDF | parse_pdf | Uses Google Document AI; large PDFs are split into 15-page chunks |
| HTML / HTM | parse_html | Uses BeautifulSoup to remove scripts/styles and keep readable text |
| TXT | parse_text | Simple file read |
| DOCX / PPTX | parse_office | Uses Unstructured to partition office documents |

---

## 5. Storage behavior

| Storage target | Path pattern | Purpose |
|---|---|---|
| GCS raw bucket | source_type/filename | Keeps the original uploaded file |
| GCS processed bucket | source_type/filename.json | Stores processed data with chunks |

---

## 6. Qdrant behavior

- The code checks whether the configured collection exists before processing.
- If the collection does not exist, it creates one with vector size 768 and cosine distance.
- Each chunk is upserted as a separate point with payload containing the text, source filename, source type, and raw GCS path.

---

## 7. Current implementation notes

- The embedding batch size is currently set to 50 in the code, even though the workflow description mentions 20.
- The code uses Qdrant, not QuadrantDB.
- The pipeline is driven by folder names such as true_data and noisy_data, which are mapped to source types true and noisy.

"""End-to-end ingestion pipeline that reads source files, parses them, chunks text, stores artifacts in GCS, creates embeddings, and indexes them in Qdrant."""

import os
import sys
import uuid
import json
import logfire
import vertexai

# Ensure repository root is on sys.path when running directly
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from typing import List
from google.cloud import storage
from qdrant_client import QdrantClient
from qdrant_client.http import models

# Import local modules
from app.config import settings
from app.services.retrieval.embedding import embed_texts
from app.ingestion.loaders.pdf import parse_pdf
from app.ingestion.loaders.html import parse_html
from app.ingestion.loaders.text import parse_text
from app.ingestion.chunking.splitter import chunk_text

# Initialize Logfire with the Enterprise Ingestion Service Name
logfire.configure(service_name = "enterprise-ingestion-service")

# Initialize Vertex AI for Embeddings
vertexai.init(project = settings.PROJECT_ID, location = settings.LOCATION)

# Initialize GCS Client
storage_client = storage.Client(project = settings.PROJECT_ID)

# Initialize Qdrant Client
qdrant_client = QdrantClient(
    url = settings.QDRANT_URL,
    api_key = settings.QDRANT_API_KEY
)

# Upload either a raw file or processed JSON payload to the configured GCS bucket.
def upload_to_gcs(data, bucket_name: str, destination_blob_name: str, is_json: bool = False):
    """
    Upload a file or JSON data to GCS
    """
    with logfire.span("☁️ GCS Upload", bucket = bucket_name, blob = destination_blob_name):
        try:
            # It stores the bucket name = "RAW/" or "PROCESSED/"
            bucket = storage_client.bucket(bucket_name)
            # It has the file path name = "true_data/cronjobs.docx"
            blob = bucket.blob(destination_blob_name)
            # If the file type is json, then upload
            if is_json:
                blob.upload_from_string(json.dumps(data), content_type = "application/json")
            else:
                blob.upload_from_filename(data)
            logfire.info(f"✅ Upload to {bucket_name}")

        except Exception as e:
            logfire.error(f"❌ GCS Upload Failed: {e}")

# Here evrything is happening - Parsing the file, then chunking, embedding, and then indxing file - finally stored in Qdrant DB
def process_file(file_path: str, filename: str, source_type: str):
    """
    Orchestrates the parsing, chunking, embedding, and indexing of a single file.
    """
    with logfire.span("🚀 Processing File", file=filename, source=source_type):
        try:
            # 1. Upload RAW File to GCS ("true_data/monitor_job.docx")
            raw_gcs_path = f"{source_type}/{filename}"
            upload_to_gcs(file_path, settings.RAW_BUCKET, raw_gcs_path)

            # 2. Parse the file into plain text based on its extension.
            ext = filename.lower().split(".")[-1]
            if ext == "pdf":
                full_text = parse_pdf(file_path)
            elif ext in ["html","htm"]:
                full_text = parse_html(file_path)
            elif ext == "txt":
                full_text = parse_text(file_path)
            elif ext in ["docx", "pptx"]:
                from app.ingestion.loaders.office import parse_office
                full_text = parse_office(file_path)
            else:
                logfire.warning(f"⏩ Skipping unsupported file type: {filename}")
                return

            # If the extracted text is empty, then show warning
            if not full_text or not full_text.strip():
                logfire.warning(f"⚠️ No text extracted from {filename}")
                return
            
            # 3. Chunking the text extracted above
            chunks = chunk_text(full_text)
            if not chunks:
                return
            
            # 4. Upload PROCESSED metadata to GCS and store them as JSON
            processed_data = {"filename": filename, "chunks": chunks, "source_type": source_type}
            processed_gcs_path = f"{source_type}/{filename}.json"
            upload_to_gcs(processed_data, settings.PROCESSED_BUCKET, processed_gcs_path, is_json = True)

            # 5. Create embeddings for each chunk and upsert them into Qdrant.
            with logfire.span("🧠 Vectorizing and Indexing"):
                embeddings = embed_texts(chunks)
                points = []
                for i, (chunk, vector) in enumerate(zip(chunks, embeddings)):
                    points.append(models.PointStruct(
                        id=str(uuid.uuid4()),
                        vector=vector,
                        payload={
                            "text": chunk,
                            "source": filename,
                            "source_type": source_type,
                            "raw_gcs_path": f"gs://{settings.RAW_BUCKET}/{raw_gcs_path}"
                        }
                    ))
                
                qdrant_client.upsert(
                    collection_name=settings.QDRANT_COLLECTION,
                    points=points
                )
                logfire.info(f"✨ Indexed {len(points)} points to Qdrant")

        except Exception as e:
            logfire.info(f"💥 Failed to process {filename}: {e}")

def run_universal_ingestion(base_dir: str, explicit_source_type: str = None, wipe: bool = False):
    """
    Automatically scans the directory.-- DATA/ is the base_directory
    If it has subfolders, maps them to source_types.
    If it has no subfolders, uses the explicit_source_type or infers from the folder name.
    """
    with logfire.span("🌍 Universal Ingestion Started", base_directory=base_dir):
        # Handling Collection Wipe - If collection exists, then delete it
        if wipe:
            with logfire.span("🧹 Wiping Collection"):
                if qdrant_client.collection_exists(settings.QDRANT_COLLECTION):
                    qdrant_client.delete_collection(settings.QDRANT_COLLECTION)
                    logfire.info(f"🗑️ Collection {settings.QDRANT_COLLECTION} deleted")
            
        # Ensure Collection Exists - We create a new collection and pass the Embedding size of embeded_data
        if not qdrant_client.collection_exists(settings.QDRANT_COLLECTION):
            qdrant_client.create_collection(
                collection_name = settings.QDRANT_COLLECTION,
                vectors_config = models.VectorParams(size = 768, distance = models.Distance.COSINE)
            )
            logfire.info(f"🆕 Created Collection {settings.QDRANT_COLLECTION}")
        
        # Scan for Subfolders - It helps to find where exactly the file is, it's kind of metadata
        # DATA/TRUE/1.pdf, 2.pdf, 3.txt,etc. Nowif we know metadata as TRUE, it's easy to find the files
        subdirs = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]
        
        # DATA/ has hey.txt, hii.pdf. means it has no folders in it, then find the base directory name
        if not subdirs:
            # If no subdirs, use explicit type or infer from the base directory name
            if explicit_source_type:
                source_type = explicit_source_type
            else:
                base_name = os.path.basename(os.path.normpath(base_dir)).lower()
                # If the file name contains, true or noise, then name source_type as true or noise, else general
                source_type = "true" if "true" in base_name else "noisy" if "noisy" in base_name else "general"
            
            logfire.info(f"📂 No subdirectories found, processing {base_dir} as '{source_type}'")
            # Finally Process the files in DATA/ folder
            process_directory(base_dir, source_type)
        else:
            # Loop throgh each subfolders and extract the source_type
            for subdir in subdirs:
                source_type = "true" if "true" in subdir.lower() else "noisy" if "noisy" in subdir.lower() else subdir
                dir_path = os.path.join(base_dir, subdir)
                # Finally process the files in the directory
                process_directory(dir_path, source_type)


def process_directory(dir_path: str, source_type: str):
    """
    Processes all files in a specific directory.
    """
    with logfire.span("📁 Scanning Directory", path=dir_path, source=source_type):
        files = [f for f in os.listdir(dir_path) if os.path.isfile(os.path.join(dir_path, f))]
        logfire.info(f"🔍 Found {len(files)} files")

        for filename in files:
            file_path = os.path.join(dir_path, filename)
            # Now finally we process the file here - we do all, parsing, chunking, embedding, and loading to qdrant db
            process_file(file_path, filename, source_type)

# It is the main entry point of the code
if __name__ == "__main__":
    # Usage: python -m app.ingestion.processor [dir_path] [source_type] [--wipe]
    wipe_requested = "--wipe" in sys.argv
    clean_args = [a for a in sys.argv if a != "--wipe"]
    
    # Default to DATA/ if no path provided
    target_dir = clean_args[1] if len(clean_args) > 1 else "DATA"
    explicit_type = clean_args[2] if len(clean_args) > 2 else None
    
    if not os.path.exists(target_dir):
        print(f"Error: Path {target_dir} does not exist.")
        sys.exit(1)
        
    run_universal_ingestion(target_dir, explicit_source_type=explicit_type, wipe=wipe_requested)
    logfire.info("🏁 Universal Ingestion Job Completed")

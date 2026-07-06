"""PDF parsing utilities that use Google Document AI to extract text from PDF documents."""

import io
import logfire
from pypdf import PdfReader, PdfWriter
from google.cloud import documentai
from app.config import settings


#                 PDF File
#                    │
#                    ▼
#           PdfReader(file_path)
#                    │
#                    ▼
#          Count Total Pages
#                    │
#          ┌─────────┴─────────┐
#          │                   │
#      ≤ MAX_PAGES        > MAX_PAGES
#          │                   │
#  Read entire PDF        Split into chunks
#          │                   │
#          ▼                   ▼
#  Process with          Chunk 1 → Document AI
#  Document AI           Chunk 2 → Document AI
#          │             Chunk 3 → Document AI
#          │                    │
#          └────────────┬────────┘
#                       ▼
#             Combine Extracted Text
#                       │
#             Check for Empty Output
#              │                  │
#          Warning             Success Log
#                       │
#                       ▼
#               Return `full_text`


client = documentai.DocumentProcessorServiceClient()
MAX_PAGES_PER_REQUEST = 15

def parse_pdf(file_path: str):
    """
    Parses PDF using Google Cloud Document AI.
    Automatically splits large PDFs into 15-page chunks to bypass synchronous API limits.
    """
    with logfire.span("📄 Document AI Parsing", filename=file_path):
        try:
            # Just Reads the PDF, doesn't extracts anything now. Just reads - Page 1,2,3,etc
            reader = PdfReader(file_path)
            total_pages = len(reader.pages)
            logfire.info(f"Total pages: {total_pages}")

            # Document AI Processor (OCR Model) End-Point path
            name = client.processor_path(
                settings.PROJECT_ID,
                settings.GCP_DOC_AI_LOCATION,
                settings.GCP_DOC_AI_PROCESSOR_ID
            )

            full_text = ""
            
            # If total pages <= 15, then process them all at once - read binary
            if total_pages <= MAX_PAGES_PER_REQUEST:
                with open(file_path, "rb") as f:
                    image_content = f.read()
                full_text = process_document_chunk(image_content, name)

            else:
                # Split large PDFs into smaller page batches so Document AI can process them reliably.
                logfire.info(f"PDF exceeds {MAX_PAGES_PER_REQUEST} pages. Splitting into chunks...")

                # (0,52 total length,15 page step) - 1,15,30,45
                for i in range(0, total_pages, MAX_PAGES_PER_REQUEST):
                    writer = PdfWriter()
                    # if i = 45, then min(60,52) = 52, then in next steps it takes Page 46,47,....52
                    chunk_end = min(i + MAX_PAGES_PER_REQUEST, total_pages)

                for page_num in range(i, chunk_end):
                    writer.add_page(reader.pages[page_num])

                # Write chunk into bytes - stores into temporary RAM, instead of saving it in disk
                with io.BytesIO() as bytes_stream:
                    writer.write(bytes_stream)
                    chunk_bytes = bytes_stream.getvalue()

                with logfire.span(f"Processing pages {i+1} to {chunk_end}"):
                    # Now pass the chunked byte into document ai service to add in chunk_text
                    # and then append in full_text (Page 1-15 pass and add to full_text, then add page 16-30)
                    chunk_text = process_document_chunk(chunk_bytes, name)
                    full_text += chunk_text + "\n"

            # If OCR returns "    " or "", remove whitespaces - resulting in empty string
            if not full_text.strip():
                logfire.warning(f"⚠️ Document AI returned empty text for {file_path}")
            else:
                logfire.info(f"✅ Document AI successfully parsed {len(full_text)} characters") 

            return full_text      

        except Exception as e:
            logfire.error(f"❌ Document AI Parse Failed: {e}")
            logfire.info(f"💡 Ensure the Processor ID is correct and the API is enabled.")
            raise e

# Document AI - OCR Parsing - image_content: PDF content in binary format, name: Document AI Processor path
def process_document_chunk(image_content: bytes, name: str) -> str:
    """Helper function to send a specific byte chunk to Document AI"""
    # Doc AI takes a packages instead of Byte form, so we pass RawDocument,
    # We pass PDF Byte data and tell that this is PDF type data using mime_type
    raw_document = documentai.RawDocument(
        content = image_content,
        mime_type = "application/pdf"
    )

    # now actual request will be sent to DocAI
    request = documentai.ProcessRequest(
        name = name,
        raw_document = raw_document
    )

    # It sends the request over the internet to Google Document AI.
    result = client.process_document(request = request)
    return result.document.text

#                     PDF Bytes
#                         │
#                         ▼
#         RawDocument(content(pdf bytes), mime_type)
#                         │
#                         ▼
#              ProcessRequest(name, document)
#                         │
#                         ▼
#       client.process_document(request)
#                         │
#                         ▼
#             Google Document AI Server
#                         │
#         ┌───────────────┴────────────────┐
#         │                                │
#         ▼                                ▼
#       OCR                     Layout Analysis
#         │                                │
#         └───────────────┬────────────────┘
#                         ▼
#                 Document Object
#         ┌───────────┬───────────┬───────────┐
#         │           │           │           │
#       Text       Tables      Pages     Paragraphs
#         │
#         ▼
# result.document.text
#         │
#         ▼
# Return String








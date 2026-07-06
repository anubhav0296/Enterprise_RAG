"""Office document parser for DOCX and PPTX files using the Unstructured library."""

import logfire
from unstructured.partition.auto import partition

def parse_office(file_path: str):
    """
    Parses Office documents (.docx, .pptx) using the Unstructured library.
    Unlike PDFs, these formats are structured and lightweight, so they are processed locally.
    """
    with logfire.span("📄 Office Document Parsing", filename=file_path):
        try:
            # Unstructured automatically detects if it's docx or pptx
            # It returns Structured elements - Resume(Title, NarrativeText, ListItem)
            elements = partition(filename=file_path)

            # Use List Comprehension to store structured element as list 
            # Extracts the string from Title, NarrativeText, ListItem and stores them with \n
            # This text is now ready to be sent to RAG Pipeline
            full_text = "\n".join([str(el) for el in elements])
            
            # If the full_text is empty then show warning else show parsing successful
            if not full_text.strip():
                logfire.warning(f"⚠️ Unstructured returned empty text for {file_path}")
            else:
                logfire.info(f"✅ Successfully parsed {len(full_text)} characters")

            return full_text
        except Exception as e:
            logfire.error(f"❌ Office Parse Failed: {e}")
            raise e
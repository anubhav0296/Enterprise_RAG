"""HTML parsing utilities that clean web content and extract readable text for RAG."""

from bs4 import BeautifulSoup
import logfire

def parse_html(file_path: str):
    """
    Parses HTML content using BeautifulSoup.
    Cleans scripts, styles, and extracts readable text for RAG.
    """
    with logfire.span("📄 HTML Parsing", filename= file_path):
        try:
            # Open the file and store the content in content variable
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            
            # Parse the html content into text format
            soup = BeautifulSoup(content, "html.parser")

            # 1. Remove junk (Scripts, Styles, Metadata)
            for script in soup(["script", "style", "meta", "noscript"]):
                script.decompose()

            # 2. Extract Text
            text = soup.get_text(separator="\n")

            # 3. Clean Whitespace (Collapse multiple newlines)
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split(" "))
            text_clean = "\n".join(chunk for chunk in chunks if chunk)

            return text_clean
        except Exception as e:
            logfire.error(f"❌ HTML Parsing Failed: {e}")
            raise e
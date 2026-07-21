from .models import DocChunk
from .quick_text import text_to_chunks
from .tables import extract_table_chunks

def parse_pdf(path: str) -> list[DocChunk]:
    chunks = text_to_chunks(path)       # 段落块 pymupdf 解析
    chunks += extract_table_chunks(path) # 表格块 pdfplumber 解析
    return chunks


__all__ = ["parse_pdf", "DocChunk"]
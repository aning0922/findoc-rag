# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportOptionalMemberAccess=false

from app.rag.chunk import fixed_chunk
from app.rag.parse.quick_text import page_body_text
import pymupdf

path, pno = "data/京东方A 2025年报.pdf", 4
with pymupdf.open(path) as doc:
    text = page_body_text(doc[pno])
    chunks = fixed_chunk(text, size=20, overlap=3)
    print(chunks)

from app.rag.parse import parse_pdf
from app.rag.chunk import chunk_docment, save_chunks

blocaks = parse_pdf("data/京东方A 2025年报.pdf", backend="mineru", mineru_out="./mineru_out")
chunks = chunk_docment(blocaks)
print(f"粗块数: {len(chunks)} + 精块数: {len(chunks)}")
save_chunks(chunks, "./data/京东方A 2025年报_chunks.jsonl")
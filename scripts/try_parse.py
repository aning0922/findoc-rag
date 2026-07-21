from app.rag.parse import parse_pdf

chunks = parse_pdf("data/成都华微电子2025年报.pdf")
print(f"总块数：{len(chunks)}")
print(f"表格块：{sum(1 for c in chunks if c.type == 'table')}")
print(f"段落块：{sum(1 for c in chunks if c.type == 'paragraph')}")
for c in chunks[:3]:
    print(f"    [{c.type}] p{c.page}: {c.text[:40]}...")

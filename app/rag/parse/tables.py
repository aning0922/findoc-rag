import pdfplumber
from .models import DocChunk


def table_to_md(table: list[list[str | None]]) -> str:
    """pdfplumber 的表格(行列嵌套 list)→ 合法 Markdown 表格。
    单元格里的换行 / 竖线会破坏表格,先清洗;各行列数不齐就补空。"""

    def clean(cell: str | None) -> str:
        return (cell or "").replace("\n", " ").replace("|", "\\|").strip()

    rows = [[clean(c) for c in row] for row in table]
    if not rows:
        return ""
    ncol = max(len(r) for r in rows)
    rows = [r + [""] * (ncol - len(r)) for r in rows]  # 补齐每行列数
    header = "| " + " | ".join(rows[0]) + " |"
    sep = "| " + " | ".join(["---"] * ncol) + " |"
    body = ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join([header, sep] + body)


def extract_table_chunks(path: str, page_no: int | None = None) -> list[DocChunk]:
    """抽取表格并转换为DocChunk列表，表格为table类型，table_md为表格的Markdown格式"""
    chunks: list[DocChunk] = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            if page_no is not None and i != page_no:
                continue
            for t in page.extract_tables():
                md = table_to_md(t)
                summary = f"第{i}页表格，{len(t)}行，{len(t[0])}列"
                chunks.append(
                    DocChunk(text=summary, page=i, type="table", source_file=path, table_md=md)
                )

    return chunks


if __name__ == "__main__":
    path = "data/京东方A 2025年报.pdf"
    chunks = extract_table_chunks(path, 29)
    for c in chunks:
        print(c.text)
        print(c.table_md)  # ⚠️ 直接打 table_md 才看得到真实换行;print(列表) 会把 \n 显示成转义符
        print("-" * 40)

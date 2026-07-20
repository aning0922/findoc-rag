# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
from typing import cast
from .models import DocChunk
import pymupdf

SCANNED_CHAR_THRESHOLD = 20  # 一页文字少于这么多字符 -> 判扫描页(图片，没有文字层)


def page_text(page: pymupdf.Page) -> str:
    # get_text() 有多种返回(str/list/dict),默认取纯文本;cast 成 str 才能 .strip()
    return cast(str, page.get_text())


def is_scanned_page(page: pymupdf.Page) -> bool:
    return len(page_text(page).strip()) < SCANNED_CHAR_THRESHOLD


def extract_text_fast(path: str) -> list[str]:
    """逐页抽纯文本,返回每页文本组成的列表"""
    pages: list[str] = []
    with pymupdf.open(path) as doc:
        for i in range(doc.page_count):
            pages.append(page_text(doc[i]))
    return pages


def text_to_chunks(path: str) -> list[DocChunk]:
    """抽取文本并转换为DocChunk列表"""
    chunks: list[DocChunk] = []
    with pymupdf.open(path) as doc:
        for i in range(doc.page_count):
            page = doc[i]
            if is_scanned_page(page):
                continue
            txt = page_text(page).strip()
            if txt:
                chunks.append(DocChunk(text=txt, page=i + 1, type="paragraph", source_file=path))
    return chunks


if __name__ == "__main__":
    path = "data/京东方A 2025年报.pdf"
    chunks = text_to_chunks(path)
    print(chunks)
    with pymupdf.open(path) as doc:
        for block in doc[11].get_text("blocks"):
            x0, y0, x1, y1, text, block_no, block_type = block
            if block_type == 0:
                print(block_no, repr(text[:30]))
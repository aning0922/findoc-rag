# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
from typing import cast

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


if __name__ == "__main__":
    path = "data/京东方A 2025年报.pdf"
    with pymupdf.open(path) as doc:
        for i in range(doc.page_count):
            page = doc[i]
            n = len(page_text(page).strip())
            print(f"第{i + 1}页：{n}字符， 扫描页={is_scanned_page(page)}")

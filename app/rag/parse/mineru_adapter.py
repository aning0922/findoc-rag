import json
from pathlib import Path
from typing import Literal
from pydantic import BaseModel
from .models import DocChunk


class _MineruItem(BaseModel):
    """Mineru 适配器模型，对应单个文档块
    Args:
        type: 块类型，对应 DocChunk.type
        text: 文本内容，对应 DocChunk.text
        text_level: 文本级别，对应 DocChunk.text_level
        page_idx: 页码，对应 DocChunk.page
        table_body: 表格内容，对应 DocChunk.table_body
        table_caption: 表格标题，对应 DocChunk.table_caption
    """

    type: str
    text: str = ""
    text_level: int | None = None
    page_idx: int = 0
    table_body: str = ""
    table_caption: list[str] = []


def parse_mineru_output(out_dir: str, source_file: str) -> list[DocChunk]:
    """解析 Mineru 输出目录中的内容列表文件，转换为 DocChunk 列表
    Args:
        out_dir: Mineru 输出目录
        source_file: 源文件路径
    Returns:
        DocChunk 列表
    """
    matches = list(Path(out_dir).rglob("*_content_list.json"))
    if not matches:
        raise FileNotFoundError(f"没在{out_dir}找到 *_content_list.json 文件")
    raw: list[object] = json.loads(matches[0].read_text(encoding="utf-8"))
    items = [_MineruItem.model_validate(x) for x in raw]

    chunks: list[DocChunk] = []
    for el in items:
        page = el.page_idx + 1
        if el.type == "table":
            caption = "".join(el.table_caption)
            chunks.append(
                DocChunk(
                    text=caption or f"第{page}页表格",
                    page=page,
                    type="table",
                    source_file=source_file,
                    table_md=el.table_body,
                )
            )
        elif el.type == "text" and el.text.strip():
            kind: Literal["title", "paragraph"] = "title" if el.text_level == 1 else "paragraph"
            chunks.append(
                DocChunk(text=el.text.strip(), page=page, type=kind, source_file=source_file)
            )

    return chunks

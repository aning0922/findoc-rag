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

    type: Literal["table", "text"]
    text: str = ""
    text_level: int | None = None
    page_idx: int
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
    content = matches[0].read_text(encoding="utf-8")
    json_data = json.loads(content)
    if not isinstance(json_data, list):
        raise ValueError("json 没有解析出list")
    items: list[_MineruItem] = []
    for raw in json_data:
        item = _MineruItem.model_validate(raw)
        if item.text_level is not None and item.text.strip() == "":
            raise ValueError("标题为空")
        if item.type == "table" and item.table_body.strip() == "":
            raise ValueError("表格内容为空")
        items.append(item)

    section_path: dict[int, str] = {}
    chunks: list[DocChunk] = []
    for el in items:
        page = el.page_idx + 1
        if el.type == "table":
            caption = "".join(el.table_caption).strip()
            if not caption:
                caption = f"第{page}页表格"

            chunks.append(
                DocChunk(
                    text=caption + "\n" + el.table_body,
                    page=page,
                    type="table",
                    source_file=source_file,
                    table_md=el.table_body,
                    section="/".join([v for _, v in sorted(section_path.items())])
                    if len(section_path) > 0
                    else "",
                    chunk_id="",
                )
            )
        elif el.type == "text" and el.text.strip():
            if el.text_level is not None:
                section_path = {k: v for k, v in section_path.items() if k < el.text_level}
                section_path[el.text_level] = el.text.strip()
                chunks.append(
                    DocChunk(
                        text=el.text.strip(),
                        page=page,
                        type="title",
                        source_file=source_file,
                        table_md="",
                        section="/".join([v for _, v in sorted(section_path.items())])
                        if len(section_path) > 0
                        else "",
                        chunk_id="",
                    )
                )
            else:
                chunks.append(
                    DocChunk(
                        text=el.text.strip(),
                        page=page,
                        type="paragraph",
                        source_file=source_file,
                        section="/".join([v for _, v in sorted(section_path.items())])
                        if len(section_path) > 0
                        else "",
                        chunk_id="",
                    )
                )

    return chunks

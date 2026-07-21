from typing import Literal
from pydantic import BaseModel, Field


class DocChunk(BaseModel):
    text: str = Field(..., description="检索用文本，表哥这块放标题+摘要")
    page: int = Field(ge=1)
    type: Literal["paragraph", "table", "title"]
    source_file: str = Field(..., description="源文件路径")
    table_md: str | None = Field(default=None, description="给LLM用，非表格为None")
    section: str = Field(default="", description="章节")
    chunk_id: str = Field(default="", description="唯一，分块时填 uuid")

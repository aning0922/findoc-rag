from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.documents.models import DocumentStatus, FailureStage


class HealthResponse(BaseModel):
    """health接口返回的最小进程存活信息。"""

    status: Literal["ok"]


class DocumentResponse(BaseModel):
    """对外展示文档状态，不包含存储定位和本机基础设施信息。"""

    model_config = ConfigDict(from_attributes=True)

    document_id: str
    source_file: str
    status: DocumentStatus
    failed_stage: FailureStage | None
    error_code: str | None
    safe_error_message: str | None
    created_at: datetime
    updated_at: datetime


class DocumentUploadResponse(DocumentResponse):
    """上传请求结果，额外说明是否命中已有相同内容。"""

    duplicate: bool

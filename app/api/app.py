from typing import Annotated

from fastapi import (
    FastAPI,
    File,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse

from app.api.schemas import (
    ChatRequest,
    DocumentResponse,
    DocumentUploadResponse,
    HealthResponse,
)
from app.api.sse import stream_chat_sse
from app.chat.service import ChatService, DocumentNotReadyError
from app.documents.models import (
    DocumentNotFoundError,
    DocumentStateConflictError,
    DocumentUploadResult,
    DocumentTooLargeError,
    InvalidDocumentError,
)
from app.documents.service import (
    DEFAULT_MAX_UPLOAD_BYTES,
    DocumentService,
)


def _to_upload_response(
    result: DocumentUploadResult,
) -> DocumentUploadResponse:
    """把内部上传结果转换为不暴露存储字段的API响应。"""
    document_payload = DocumentResponse.model_validate(
        result.record,
    ).model_dump()

    return DocumentUploadResponse.model_validate(
        {
            **document_payload,
            "duplicate": result.duplicate,
        }
    )


def create_app(
    document_service: DocumentService,
    *,
    chat_service: ChatService | None = None,
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
) -> FastAPI:
    """创建包含health、文档处理和可选可信聊天接口的FastAPI应用

    Args:
        document_service: 已注入基础设施依赖的文档应用服务。
        max_upload_bytes: 路由读取上传内容时使用的字节上限。

    Returns:
        可供测试或uvicorn运行的FastAPI应用。

    Raises:
        ValueError: max_upload_bytes不是正整数。
    """
    if max_upload_bytes <= 0:
        raise ValueError("max_upload_bytes 必须是正整数")

    app = FastAPI(title="FinDoc RAG API")

    @app.get(
        "/health",
        response_model=HealthResponse,
    )
    async def health() -> HealthResponse:
        """返回进程存活状态，不等待后台文档任务。"""
        return HealthResponse(status="ok")

    @app.post(
        "/documents",
        response_model=DocumentUploadResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def upload_document(
        file: Annotated[
            UploadFile,
            File(description="带文本层的PDF文件"),
        ],
    ) -> DocumentUploadResponse:
        """读取受限大小的PDF内容并提交给文档应用服务。"""
        try:
            # 多读一个字节，才能区分“刚好达到上限”和“超过上限”。
            content = await file.read(max_upload_bytes + 1)
        finally:
            await file.close()

        try:
            result = await document_service.upload_document(
                source_file=file.filename or "",
                content=content,
            )
        except DocumentTooLargeError as exc:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=str(exc),
            ) from exc
        except InvalidDocumentError as exc:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=str(exc),
            ) from exc

        return _to_upload_response(result)

    @app.get(
        "/documents",
        response_model=list[DocumentResponse],
    )
    async def list_documents() -> list[DocumentResponse]:
        """列出服务端固定workspace中的文档状态。"""
        records = await document_service.list_documents()
        return [DocumentResponse.model_validate(record) for record in records]

    @app.get(
        "/documents/{document_id}",
        response_model=DocumentResponse,
    )
    async def get_document(
        document_id: str,
    ) -> DocumentResponse:
        """查询一个文档的当前处理状态。"""
        try:
            record = await document_service.get_document(document_id)
        except DocumentNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文档不存在",
            ) from exc

        return DocumentResponse.model_validate(record)

    @app.post(
        "/documents/{document_id}/retry",
        response_model=DocumentResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def retry_document(
        document_id: str,
    ) -> DocumentResponse:
        """仅把failed文档重新排队并尝试派发。"""
        try:
            record = await document_service.retry_document(document_id)
        except DocumentNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文档不存在",
            ) from exc
        except DocumentStateConflictError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="只有处理失败的文档可以重试",
            ) from exc

        return DocumentResponse.model_validate(record)

    @app.post("/chat")
    async def chat(
        payload: ChatRequest,
        request: Request,
    ) -> StreamingResponse:
        """对通过HTTP前置检查的聊天请求返回SSE响应。

        输入：只包含document_id和query的浏览器请求。
        输出：通过前置检查后返回text/event-stream。
        失败：文档不存在返回404，未ready返回409，未注入聊天服务返回503。
        边界：不执行检索或引用验证，只连接ChatService和SSE传输层。
        """
        if chat_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="聊天服务未启用",
            )
        try:
            prepared = await chat_service.prepare(
                document_id=payload.document_id, query=payload.query
            )
        except DocumentNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文档不存在",
            ) from exc
        except DocumentNotReadyError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="只有处理成功的文档可以聊天",
            ) from exc
        return StreamingResponse(
            stream_chat_sse(chat_service, prepared, request.is_disconnected),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app

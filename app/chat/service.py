import asyncio
from dataclasses import dataclass
from typing import Protocol

from app.documents.models import DocumentRecord, DocumentStatus
from app.rag.retriever import SearchFilters, TrustedContext
from app.rag.service import RAGOutcome


class DocumentReader(Protocol):
    """定义聊天准备阶段所需的最小文档读取能力。

    输入：服务端收到的document_id。
    输出：属于固定workspace的DocumentRecord。
    失败：文档不存在或不属于固定workspace时抛出DocumentNotFoundError。
    """

    async def get_document(self, document_id: str) -> DocumentRecord:
        """读取当前固定workspace中的一条文档记录。"""
        ...


class RAGAnswerer(Protocol):
    """定义聊天执行阶段所需的同步可信RAG能力。

    输入：问题、可信workspace上下文和服务端过滤条件。
    输出：成功、正常拒答或系统失败三种RAG终态。
    失败边界：本协议不负责SSE编码，也不承诺线程取消。
    """

    def answer(
        self,
        query: str,
        *,
        context: TrustedContext,
        filters: SearchFilters | None = None,
    ) -> RAGOutcome:
        """同步执行可信问答，并返回一个领域终态。"""
        ...


class DocumentNotReadyError(RuntimeError):
    """文档存在且属于当前 workspace，但状态不是 ready"""


@dataclass(frozen=True)
class PreparedChat:
    """服务端准备完成的不可变聊天输入，保存 query、可信 context 和服务端过滤条件"""

    query: str
    context: TrustedContext
    filters: SearchFilters | None = None

    def __post_init__(self) -> None:
        """校验 query 和 context 非空；filters 类型正确"""
        if not isinstance(self.query, str) or not self.query.strip():
            raise ValueError("query 必须是非空字符串")
        if not isinstance(self.context, TrustedContext):
            raise TypeError("context 必须是 TrustedContext")
        if self.filters is not None and not isinstance(self.filters, SearchFilters):
            raise TypeError("filters 必须是 SearchFilters 或 None")


class ChatService:
    """负责前置检查和调用同步 RAGService，不负责 SSE framing 或终态事件映射"""

    def __init__(self, *, document_service: DocumentReader, rag_service: RAGAnswerer) -> None:
        """保存服务端文档读取依赖和同步可信RAG依赖。

        Args:
            document_service: 固定workspace的文档读取器。
            rag_service: 同步RAG执行器。

        Returns:
            ChatService: 可准备并执行可信聊天的服务对象。

        边界：构造阶段不查询文档，也不调用RAG。
        """
        self._document_service = document_service
        self._rag_service = rag_service

    async def prepare(self, *, document_id: str, query: str) -> PreparedChat:
        """准备一次聊天请求的输入。

        Args:
            document_id: 文档唯一标识符。
            query: 用户问题。

        Returns:
            PreparedChat: 准备完成的聊天输入。

        失败：文档不存在时保留DocumentNotFoundError，未ready时抛出
        DocumentNotReadyError，输入非法时保留PreparedChat校验异常。
        边界：workspace和document_id过滤都从服务端DocumentRecord恢复。
        """
        document = await self._document_service.get_document(document_id)
        if document.status != DocumentStatus.READY:
            raise DocumentNotReadyError(f"文档 {document_id} 状态不是 ready")
        return PreparedChat(
            query=query,
            context=TrustedContext(workspace_id=document.workspace_id),
            filters=SearchFilters(document_id=document.document_id),
        )

    async def answer(self, prepared: PreparedChat) -> RAGOutcome:
        """执行一次聊天请求。

        Args:
            prepared: 准备完成的聊天输入。

        Returns:
            RAGOutcome: 聊天请求的结果。

        失败：同步RAG意外抛出的异常从工作线程传播给调用者。
        边界：通过asyncio.to_thread离开event loop，但不承诺客户端断开后取消线程。
        """
        return await asyncio.to_thread(
            self._rag_service.answer,
            prepared.query,
            context=prepared.context,
            filters=prepared.filters,
        )

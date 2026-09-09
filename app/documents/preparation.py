"""为聊天与 Agent 复用单文档任务的前置检查，不执行检索或模型。"""

from dataclasses import dataclass
from typing import Protocol

from app.documents.models import DocumentRecord, DocumentStatus
from app.rag.retriever import SearchFilters, TrustedContext


class DocumentReader(Protocol):
    """读取服务端固定 workspace 的文档；不存在或越界时抛出 DocumentNotFoundError。"""

    async def get_document(self, document_id: str) -> DocumentRecord:
        """接收待查证的文档编号，返回已检查归属的服务端记录。"""
        ...


class DocumentNotReadyError(RuntimeError):
    """文档属于当前 workspace，但尚未 ready，不能进入任务执行。"""


@dataclass(frozen=True)
class PreparedDocumentTask:
    """保存任务问题和服务端恢复的范围；数据对象本身不查询文档或认证。

    输入：问题、可信上下文和服务端过滤条件。
    输出：供聊天或 Agent 使用的不可变准备结果。
    失败：问题为空或范围外层类型错误时拒绝构造。
    边界：保留既有聊天输入的可选 filters 合同；preparer 成功时必有单文档过滤。
    """

    query: str
    """用户问题，不作为授权指令。"""
    context: TrustedContext
    """从已查证记录恢复的 workspace。"""
    filters: SearchFilters | None = None
    """服务端过滤条件；共享准备入口始终设置唯一 document_id。"""
    source_file: str | None = None
    """核准记录中的逻辑文件名；供 Agent 交叉核对证据，不替代 document_id。"""

    def __post_init__(self) -> None:
        """保留原聊天输入校验；不把类型检查当作归属或 ready 查证。"""
        if not isinstance(self.query, str) or not self.query.strip():
            raise ValueError("query 必须是非空字符串")
        if not isinstance(self.context, TrustedContext):
            raise TypeError("context 必须是 TrustedContext")
        if self.filters is not None and not isinstance(self.filters, SearchFilters):
            raise TypeError("filters 必须是 SearchFilters 或 None")
        if self.source_file is not None and (
            not isinstance(self.source_file, str) or not self.source_file.strip()
        ):
            raise ValueError("source_file 必须是非空字符串或 None")


class DocumentTaskPreparer:
    """复用文档归属查询，检查 ready 并恢复单文档任务范围。

    输入：构造时提供固定 workspace 的文档服务；调用时提供文档编号和问题。
    输出：PreparedDocumentTask，范围只取自服务端返回的记录。
    失败：保留文档不可用异常；未 ready 或问题非法时前置失败。
    边界：不创建 Run，不执行 RAG、工具或模型，不复制文档归属规则。
    """

    def __init__(self, *, document_service: DocumentReader) -> None:
        """保存已绑定服务端 workspace 的文档读取依赖，构造时不查询。"""
        self._document_service = document_service

    async def prepare(self, *, document_id: str, query: str) -> PreparedDocumentTask:
        """先查证文档和 ready，再返回问题及记录中的范围；失败直接向调用方传播。"""
        document = await self._document_service.get_document(document_id)
        if document.status != DocumentStatus.READY:
            raise DocumentNotReadyError(f"文档 {document_id} 状态不是 ready")
        return PreparedDocumentTask(
            query=query,
            context=TrustedContext(workspace_id=document.workspace_id),
            filters=SearchFilters(document_id=document.document_id),
            source_file=document.source_file,
        )

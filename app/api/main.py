from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from app.api.app import create_app
from app.documents.fast_pdf_parser import parse_fast_pdf_bytes
from app.documents.in_process_dispatcher import InProcessTaskDispatcher
from app.documents.local_object_store import LocalObjectStore
from app.documents.processor import DocumentProcessor
from app.documents.service import DocumentService
from app.documents.sqlite_repository import SQLiteDocumentRepository
from app.rag.ingest import ReplaceResult, replace_document_rows
from app.rag.store import ensure_document_collection, get_client


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNTIME_ROOT = PROJECT_ROOT / "data" / "runtime"
RUNTIME_COLLECTION_NAME = "findoc_runtime_documents_v1"
DEMO_WORKSPACE_ID = "demo"
RUNTIME_DATA_VERSION = "runtime-v1"


def _lazy_bge_embed(texts: list[str]) -> list[list[float]]:
    """在后台worker首次需要向量时才加载真实bge-m3模型。

    Args:
        texts: 已完成解析和切块的文本列表。

    Returns:
        与texts顺序和数量对齐的1024维向量。

    Raises:
        Exception: 模型加载或向量计算失败，由processor转换成安全索引失败。
    """
    from app.rag.embed import embed

    return embed(texts)


def _build_runtime_indexer(
    database_path: Path,
    collection_name: str,
) -> Callable[[str, list[dict[str, Any]]], ReplaceResult]:
    """建立只写入runtime Milvus数据库和collection的索引函数。

    Args:
        database_path: 独立于冻结数据的runtime Milvus Lite路径。
        collection_name: runtime上传文档专用collection名称。

    Returns:
        可注入DocumentProcessor的document级replace函数。
    """

    def index_document(
        document_id: str,
        rows: list[dict[str, Any]],
    ) -> ReplaceResult:
        """按document_id替换runtime索引，并返回最终ID核验结果。"""
        client = get_client(str(database_path))
        try:
            ensure_document_collection(
                client,
                collection_name,
            )
            return replace_document_rows(
                client,
                collection_name,
                document_id,
                rows,
            )
        finally:
            client.close()

    return index_document


def create_runtime_app(
    runtime_root: Path = DEFAULT_RUNTIME_ROOT,
) -> FastAPI:
    """组装单进程文档上传应用及其独立runtime基础设施。

    Args:
        runtime_root: SQLite、对象文件和runtime Milvus的内部根目录。

    Returns:
        已绑定固定demo workspace和单进程dispatcher的FastAPI应用。

    Notes:
        SQLite记录可跨重启保存，但dispatcher任务只存在于当前进程内；
        本函数今天不扫描或恢复悬空任务。
    """
    repository = SQLiteDocumentRepository(
        runtime_root / "documents.db",
    )
    object_store = LocalObjectStore(
        runtime_root / "objects",
    )
    index_document = _build_runtime_indexer(
        runtime_root / "milvus.db",
        RUNTIME_COLLECTION_NAME,
    )

    processor = DocumentProcessor(
        repository=repository,
        object_store=object_store,
        parser=parse_fast_pdf_bytes,
        embedder=_lazy_bge_embed,
        index_document=index_document,
        data_version=RUNTIME_DATA_VERSION,
    )
    dispatcher = InProcessTaskDispatcher(
        processor.process,
    )
    document_service = DocumentService(
        repository=repository,
        object_store=object_store,
        dispatcher=dispatcher,
        workspace_id=DEMO_WORKSPACE_ID,
    )

    return create_app(document_service)


app = create_runtime_app()

from collections.abc import Mapping
from typing import Any

import pytest

from app.rag.retriever import (
    Retriever,
    RetrieverDataError,
    SearchHit,
    TrustedContext,
    SearchFilters,
    build_filter_expression,
)

TRUSTED_CONTEXT = TrustedContext(workspace_id="WS-A")


class MustNotSearchStore:
    def search(
        self, query_vector: list[float], *, top_k: int, filter_expression: str
    ) -> list[Mapping[str, Any]]:
        """确保当前测试场景不会调用 store"""
        raise AssertionError("非法输入时不应调用 store")


def must_not_embed(texts: list[str]) -> list[list[float]]:
    """确保非法输入不会触发 embedding"""
    raise AssertionError(f"非法输入时不应调用 embedder: {texts}")


@pytest.mark.parametrize(
    ("query", "top_k", "expected_error"),
    [
        ("", 5, ValueError),
        ("   \n", 5, ValueError),
        (None, 5, TypeError),
        ("营业收入", 0, ValueError),
        ("营业收入", -1, ValueError),
        ("营业收入", 2.5, TypeError),
        ("营业收入", True, TypeError),
    ],
)
def test_invalid_input_fails_before_dependencies(
    query: Any, top_k: Any, expected_error: type[Exception]
) -> None:
    """
    非法输入时，不调用 embedder 和 store，直接抛出异常。
    """
    retriever = Retriever(must_not_embed, MustNotSearchStore())

    with pytest.raises(expected_error):
        retriever.retrieve(query, context=TRUSTED_CONTEXT, top_k=top_k)


class FakeSuccessStore:
    def search(
        self, query_vector: list[float], *, top_k: int, filter_expression: str
    ) -> list[Mapping[str, Any]]:
        """返回一条字段完整的固定检索结果。"""
        assert query_vector == [0.1, 0.2]
        assert top_k == 2
        assert filter_expression == 'workspace_id == "WS-A"'

        return [
            {
                "score": 0.91,
                "chunk_id": "C-REV",
                "text": "2025年营业收入为100亿元",
                "page": 7,
                "source_file": "demo.pdf",
                "type": "paragraph",
                "section": "主要财务数据",
                "table_md": None,
            }
        ]


def test_success_uses_injected_dependencies_and_returns_search_hits() -> None:
    """
    使用注入的 embedder 和 store 成功返回 SearchHit 列表。
    """

    def fake_embedder(texts: list[str]) -> list[list[float]]:
        """验证标准化查询并返回固定查询向量"""
        assert texts == ["营业收入是多少？"]
        return [[0.1, 0.2]]

    retriever = Retriever(fake_embedder, FakeSuccessStore())

    actual = retriever.retrieve("  营业收入是多少？  ", context=TRUSTED_CONTEXT, top_k=2)

    assert actual == [
        SearchHit(
            score=0.91,
            chunk_id="C-REV",
            text="2025年营业收入为100亿元",
            page=7,
            source_file="demo.pdf",
            type="paragraph",
            section="主要财务数据",
            table_md=None,
        )
    ]


def fake_single_vector(texts: list[str]) -> list[list[float]]:
    """为单个合法查询返回一个固定的非空查询向量"""
    assert texts == ["营业收入"]
    return [[0.1, 0.2]]


class FakeEmptyStore:
    def search(
        self, query_vector: list[float], *, top_k: int, filter_expression: str
    ) -> list[Mapping[str, Any]]:
        """模拟一次正常完成但没有找到候选结果的 store 搜索"""
        return []


class BrokenStore:
    def search(
        self, query_vector: list[float], *, top_k: int, filter_expression: str
    ) -> list[Mapping[str, Any]]:
        """模拟底层向量数据库连接失败"""
        raise ConnectionError("offline")


class MissingPageStore:
    def search(
        self, query_vector: list[float], *, top_k: int, filter_expression: str
    ) -> list[Mapping[str, Any]]:
        """返回一条缺少关键 page 字段的损坏检索结果"""
        return [
            {
                "score": 0.91,
                "chunk_id": "C-REV",
                "text": "2025年营业收入为100亿元",
                "source_file": "demo.pdf",
                "type": "paragraph",
                "section": "主要财务数据",
                "table_md": None,
            }
        ]


def test_empty_embedder_result_raises_data_error_before_store() -> None:
    """embedder 未返回查询向量时，应在调用 store 前报告数据契约错误"""

    def empty_embedder(texts: list[str]) -> list[list[float]]:
        """模拟 embedder 错误地返回空向量列表"""
        assert texts == ["营业收入"]
        return []

    retriever = Retriever(empty_embedder, MustNotSearchStore())

    with pytest.raises(RetrieverDataError, match="一个非空向量"):
        retriever.retrieve("营业收入", context=TRUSTED_CONTEXT)


def test_empty_store_result_returns_empty_list() -> None:
    """store 正常返回空结果时，Retriever 应返回空列表而不是抛出异常"""
    retriever = Retriever(fake_single_vector, FakeEmptyStore())
    actual = retriever.retrieve("营业收入", context=TRUSTED_CONTEXT)
    assert actual == []


def test_missing_page_raises_data_error() -> None:
    """store hit 缺少关键 page 字段时，应报告明确的数据契约错误"""
    retriever = Retriever(fake_single_vector, MissingPageStore())
    with pytest.raises(RetrieverDataError, match="page"):
        retriever.retrieve("营业收入", context=TRUSTED_CONTEXT)


def test_store_exception_is_not_converted_to_empty_result() -> None:
    """store 连接失败时，应保留底层系统异常，不能伪装成空结果"""
    retriever = Retriever(fake_single_vector, BrokenStore())
    with pytest.raises(ConnectionError, match="offline"):
        retriever.retrieve("营业收入", context=TRUSTED_CONTEXT)


def test_build_filter_expression_combines_trusted_workspace_and_source_file() -> None:
    """过滤表达式必须组合可信， workspace 和允许选择的 source_file"""
    context = TrustedContext(workspace_id="WS-A")
    filters = SearchFilters(source_file="demo.pdf")

    actual = build_filter_expression(context, filters)

    assert actual == 'workspace_id == "WS-A" and source_file == "demo.pdf"'


def test_build_filter_expression_keeps_workspace_when_source_file_is_absent() -> None:
    """没有业务过滤时，表达式仍必须保留可信workspace 条件"""
    context = TrustedContext(workspace_id="WS-A")
    filters = SearchFilters()

    actual = build_filter_expression(context, filters)

    assert actual == 'workspace_id == "WS-A"'


class FakeStore:
    def search(
        self, query_vector: list[float], *, top_k: int, filter_expression: str
    ) -> list[Mapping[str, Any]]:
        """返回一条字段完整的固定检索结果。"""
        assert query_vector == [0.1, 0.2]
        assert top_k == 2
        assert filter_expression == 'workspace_id == "WS-A" and source_file == "demo.pdf"'
        return [
            {
                "score": 0.91,
                "chunk_id": "C-REV",
                "text": "2025年营业收入为100亿元",
                "page": 7,
                "source_file": "demo.pdf",
                "type": "paragraph",
                "section": "主要财务数据",
                "table_md": None,
            }
        ]


def test_legal_source_file_filter_is_combined_with_trusted_workspace() -> None:
    """合法 source_file 必须与可信 workspace 一起传给 store"""

    def fake_embedder(texts: list[str]) -> list[list[float]]:
        """验证标准化查询并返回固定查询向量"""
        assert texts == ["营业收入是多少？"]
        return [[0.1, 0.2]]

    context = TrustedContext(workspace_id="WS-A")
    filters = SearchFilters(source_file="demo.pdf")

    retriever = Retriever(fake_embedder, FakeStore())
    actual = retriever.retrieve("营业收入是多少？", context=context, top_k=2, filters=filters)
    assert actual == [
        SearchHit(
            score=0.91,
            chunk_id="C-REV",
            text="2025年营业收入为100亿元",
            page=7,
            source_file="demo.pdf",
            type="paragraph",
            section="主要财务数据",
            table_md=None,
        )
    ]


class FakeNonexistentSourceStore:
    def search(
        self,
        query_vector: list[float],
        *,
        top_k: int,
        filter_expression: str,
    ) -> list[Mapping[str, Any]]:
        """确认不存在的 source_file 与可信 workspace 一起传入 store。"""
        assert query_vector == [0.1, 0.2]
        assert top_k == 2
        assert filter_expression == ('workspace_id == "WS-A" and source_file == "不存在.pdf"')
        return []


def test_nonexistent_source_file_filter_returns_empty_list() -> None:
    """不存在合法的 source_file 条件产生空结果而不是系统异常"""

    def fake_embedder(texts: list[str]) -> list[list[float]]:
        """验证标准化查询并返回固定查询向量"""
        assert texts == ["营业收入是多少？"]
        return [[0.1, 0.2]]

    context = TrustedContext(workspace_id="WS-A")
    filters = SearchFilters(source_file="不存在.pdf")

    retriever = Retriever(fake_embedder, FakeNonexistentSourceStore())
    actual = retriever.retrieve("营业收入是多少？", context=context, top_k=2, filters=filters)
    assert actual == []


def test_user_cannot_override_trusted_workspace() -> None:
    """用户提交的 workspace 不得覆盖服务端可信 workspace"""

    filters: Any = {
        "workspace_id": "WS-B",
        "source_file": "demo.pdf",
    }

    retriever = Retriever(must_not_embed, MustNotSearchStore())
    with pytest.raises(TypeError, match="filters"):
        retriever.retrieve("营业收入是多少？", context=TRUSTED_CONTEXT, top_k=2, filters=filters)


class WorkspaceStore:
    def search(
        self, query_vector: list[float], *, top_k: int, filter_expression: str
    ) -> list[Mapping[str, Any]]:
        """验证仅使用可信 workspace 和允许的 source_file，未命中时返回空列表"""
        assert query_vector == [0.1, 0.2]
        assert top_k == 2
        assert filter_expression == 'workspace_id == "WS-A" and source_file == "已归档.pdf"'
        return []


def test_gate_ignores_user_workspace_and_returns_empty_for_missing_source() -> None:
    """用户提交的 workspace 不得覆盖服务端可信 workspace"""

    def fake_embedder(texts: list[str]) -> list[list[float]]:
        """验证标准化查询并返回固定查询向量"""
        assert texts == ["营业收入是多少？"]
        return [[0.1, 0.2]]

    user_payload = {
        "workspace_id": "WS-B",
        "source_file": "已归档.pdf",
    }
    source_file = user_payload.get("source_file")
    assert isinstance(source_file, str)
    trusted_context = TrustedContext(workspace_id="WS-A")
    filters = SearchFilters(source_file=source_file)
    retriever = Retriever(fake_embedder, WorkspaceStore())
    actual = retriever.retrieve(
        "营业收入是多少？", context=trusted_context, top_k=2, filters=filters
    )
    assert actual == []

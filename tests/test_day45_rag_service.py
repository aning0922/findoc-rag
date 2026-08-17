import pytest
from app.rag.retriever import SearchFilters, SearchHit, TrustedContext
from app.rag.service import (
    Citation,
    CitationValidationError,
    ContextBudgetError,
    RAGService,
    build_numbered_context,
    validate_and_build_citations,
)
from tests.test_day44_rag_service import FakeLLMClient, FakeRetriever


def test_build_numbered_context_returns_numbered_text_and_immutable_mapping() -> None:
    """输入两条可完整容纳的有序 SearchHit；
    输出包含连续 [1]、[2] 标签的证据文本，以及指向同一批 SearchHit 的只读编号映射；
    若文本、编号关系或外部写入映射的 TypeError 不符合合同，则测试失败。
    """
    hits = [
        SearchHit(
            text="hit1",
            chunk_id="chunk_id_1",
            page=1,
            source_file="source_file_1",
            type="paragraph",
            score=1.0,
        ),
        SearchHit(
            text="hit2",
            chunk_id="chunk_id_2",
            page=2,
            source_file="source_file_2",
            type="paragraph",
            score=2.0,
        ),
    ]
    numbered_context = build_numbered_context(hits, max_evidence_chars=100)
    assert numbered_context.text == "[1]:hit1 [2]:hit2"
    assert numbered_context.hits_by_number == {1: hits[0], 2: hits[1]}
    with pytest.raises(TypeError):
        numbered_context.hits_by_number[3] = hits[0]  # type: ignore[index]


def test_build_numbered_context_stops_before_over_budget_hit_without_dangling_number() -> None:
    """输入两条有序 SearchHit，并把字符预算设置为只够第一条最终渲染证据块；
    输出只能包含 [1] 及其映射，不得出现 [2] 或第二条 SearchHit；
    若预算外证据进入文本或权威映射，则测试失败。
    """
    hits = [
        SearchHit(
            text="hit1",
            chunk_id="chunk_id_1",
            page=1,
            source_file="source_file_1",
            type="paragraph",
            score=1.0,
        ),
        SearchHit(
            text="hit2",
            chunk_id="chunk_id_2",
            page=2,
            source_file="source_file_2",
            type="paragraph",
            score=2.0,
        ),
    ]
    max_evidence_chars = len("[1]:hit1")
    numbered_context = build_numbered_context(hits, max_evidence_chars=max_evidence_chars)
    assert numbered_context.text == "[1]:hit1"
    assert numbered_context.hits_by_number == {1: hits[0]}


def test_build_numbered_context_raises_when_first_rendered_hit_exceeds_budget() -> None:
    """输入一条 SearchHit，并把字符预算设置为小于其带 [1] 标签后的完整渲染长度；
    函数没有成功输出，而应抛出 ContextBudgetError；
    若返回空 NumberedContext、截断证据或静默成功，则测试失败。
    """
    hits = [
        SearchHit(
            text="hit1",
            chunk_id="chunk_id_1",
            page=1,
            source_file="source_file_1",
            type="paragraph",
            score=1.0,
        ),
    ]
    with pytest.raises(ContextBudgetError):
        build_numbered_context(hits, max_evidence_chars=2)


def test_validate_and_build_citations_maps_out_of_order_numbers_to_server_metadata() -> None:
    """输入包含编号1和2的 NumberedContext，以及先引用 [2]、后引用 [1] 的模型文本；
    输出 Citation 顺序必须是2、1，且各自的 source_file、page、chunk_id只来自对应 SearchHit；
    若按原始hits下标、编号排序或模型文本中的自报元数据生成引用，则测试失败。
    """
    hits = [
        SearchHit(
            text="hit1",
            chunk_id="chunk_id_1",
            page=1,
            source_file="source_file_1",
            type="paragraph",
            score=1.0,
        ),
        SearchHit(
            text="hit2",
            chunk_id="chunk_id_2",
            page=2,
            source_file="source_file_2",
            type="paragraph",
            score=2.0,
        ),
    ]
    numbered_context = build_numbered_context(hits, max_evidence_chars=100)
    citations = validate_and_build_citations(
        model_output="hit1 [2] hit2 [1]", numbered_context=numbered_context
    )
    assert citations == (
        Citation(number=2, source_file="source_file_2", page=2, chunk_id="chunk_id_2"),
        Citation(number=1, source_file="source_file_1", page=1, chunk_id="chunk_id_1"),
    )
    with pytest.raises(CitationValidationError):
        validate_and_build_citations(
            model_output="hit1 [3] hit2 [1]", numbered_context=numbered_context
        )


def test_validate_and_build_citations_deduplicates_by_first_appearance() -> None:
    """输入引用顺序为 [2]、[1]、[2] 的模型文本和包含编号1、2的 NumberedContext；
    输出只能包含两个 Citation，顺序稳定为2、1；
    若保留重复项、使用无序集合结果或改成编号排序，则测试失败。
    """
    hits = [
        SearchHit(
            text="hit1",
            chunk_id="chunk_id_1",
            page=1,
            source_file="source_file_1",
            type="paragraph",
            score=1.0,
        ),
        SearchHit(
            text="hit2",
            chunk_id="chunk_id_2",
            page=2,
            source_file="source_file_2",
            type="paragraph",
            score=0.5,
        ),
    ]
    numbered_context = build_numbered_context(hits, max_evidence_chars=100)
    citations = validate_and_build_citations(
        model_output="hit2 [2] hit1 [1] hit2 [2]", numbered_context=numbered_context
    )
    assert citations == (
        Citation(number=2, source_file="source_file_2", page=2, chunk_id="chunk_id_2"),
        Citation(number=1, source_file="source_file_1", page=1, chunk_id="chunk_id_1"),
    )


def test_validate_and_build_citations_rejects_unknown_number() -> None:
    """输入只包含编号1、2的权威映射，但模型文本声明引用 [99]；
    函数没有成功输出，而应抛出 CitationValidationError；
    若忽略非法编号、返回部分Citation或生成伪造元数据，则测试失败。
    """
    hits = [
        SearchHit(
            text="hit1",
            chunk_id="chunk_id_1",
            page=1,
            source_file="source_file_1",
            type="paragraph",
            score=1.0,
        ),
        SearchHit(
            text="hit2",
            chunk_id="chunk_id_2",
            page=2,
            source_file="source_file_2",
            type="paragraph",
            score=2.0,
        ),
    ]
    numbered_context = build_numbered_context(hits, max_evidence_chars=100)
    with pytest.raises(CitationValidationError):
        validate_and_build_citations(model_output="hit1 [99]", numbered_context=numbered_context)


def test_validate_and_build_citations_rejects_answer_without_citation() -> None:
    """输入非空答案正文，但文本中没有任何受支持的 [n] 引用；
    函数没有成功输出，而应抛出 CitationValidationError；
    若返回空Citation序列并把答案视为成功，则测试失败。
    """
    hits = [
        SearchHit(
            text="hit1",
            chunk_id="chunk_id_1",
            page=1,
            source_file="source_file_1",
            type="paragraph",
            score=1.0,
        ),
    ]
    numbered_context = build_numbered_context(hits, max_evidence_chars=100)
    with pytest.raises(CitationValidationError):
        validate_and_build_citations(model_output="hit1", numbered_context=numbered_context)


def test_validate_and_build_citations_rejects_citation_without_answer_body() -> None:
    """输入仅包含空白和合法 [1] 的模型文本；
    移除引用标记后答案正文为空，因此应抛出 CitationValidationError；
    若只有引用也能成为正式答案，则测试失败。
    """
    hits = [
        SearchHit(
            text="hit1",
            chunk_id="chunk_id_1",
            page=1,
            source_file="source_file_1",
            type="paragraph",
            score=1.0,
        ),
    ]
    numbered_context = build_numbered_context(hits, max_evidence_chars=100)
    with pytest.raises(CitationValidationError):
        validate_and_build_citations(model_output="[1]", numbered_context=numbered_context)


def test_rag_service_rejects_unknown_citation_without_reclassifying_generation() -> None:
    """Retriever返回非空证据，FakeLLMClient正常返回带[99]的非空模型草稿；
    RAGService应原样抛出CitationValidationError，且LLM恰好调用1次；
    若非法引用被包装成GenerationError或返回正式RAGResult，则测试失败。
    """
    search_hits = [
        SearchHit(
            score=0.9,
            chunk_id="C-REV",
            text="2025年营业收入为100亿元",
            page=7,
            source_file="demo.pdf",
            type="paragraph",
            section="主要财务数据",
            table_md=None,
        ),
    ]
    query = "营业收入是多少？"
    trusted_context = TrustedContext(workspace_id="W-SA")
    search_filters = SearchFilters(source_file="demo.pdf")
    top_k = 5
    fake_retriever = FakeRetriever(hits=search_hits)
    fake_llm = FakeLLMClient(response="2025年营业收入为100亿元 [99]")
    service = RAGService(fake_retriever, fake_llm, max_evidence_chars=500)
    with pytest.raises(CitationValidationError):
        service.answer(query, context=trusted_context, top_k=top_k, filters=search_filters)
    assert len(fake_retriever.calls) == 1
    assert len(fake_llm.prompts) == 1
    assert query in fake_llm.prompts[0]


def test_rag_service_skips_llm_when_first_evidence_exceeds_context_budget() -> None:
    """Retriever返回一条非空SearchHit，但服务字符预算小于其带[1]标签后的完整渲染长度；
    RAGService应抛出ContextBudgetError，并保持LLM调用0次；
    若把它伪装成NoEvidenceError、截断证据或继续调用模型，则测试失败。
    """
    search_hits = [
        SearchHit(
            score=0.9,
            chunk_id="C-REV",
            text="2025年营业收入为100亿元",
            page=7,
            source_file="demo.pdf",
            type="paragraph",
            section="主要财务数据",
            table_md=None,
        ),
    ]
    query = "营业收入是多少？"
    trusted_context = TrustedContext(workspace_id="W-SA")
    search_filters = SearchFilters(source_file="demo.pdf")
    top_k = 5
    fake_retriever = FakeRetriever(hits=search_hits)
    fake_llm = FakeLLMClient(response="2025年营业收入为100亿元")
    service = RAGService(fake_retriever, fake_llm, max_evidence_chars=5)
    with pytest.raises(ContextBudgetError):
        service.answer(query, context=trusted_context, top_k=top_k, filters=search_filters)
    assert len(fake_retriever.calls) == 1
    assert len(fake_llm.prompts) == 0

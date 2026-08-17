from dataclasses import dataclass
import re
from typing import Mapping, Protocol
from types import MappingProxyType

from app.rag.retriever import Retriever, SearchHit, TrustedContext, SearchFilters


class GenerationError(RuntimeError):
    """generation 阶段因超时、调用失败或无有效内容而失败，不能作为空证据或成功结果处理"""


class RetrievalError(RuntimeError):
    """RAG 控制层报告 retrieval 阶段失败的异常"""


class NoEvidenceError(RuntimeError):
    """最小 evidence gate 未通过时抛出的领域错误"""


class ContextBudgetError(RuntimeError):
    """上下文预算不足时抛出的领域错误"""


class CitationValidationError(RuntimeError):
    """引用校验失败时抛出的领域错误"""


@dataclass(frozen=True)
class NumberedContext:
    """职责：绑定实际发送给模型的编号证据文本和服务端权威映射。
    输入来源：预算选择后的有序 SearchHit。
    输出用途：text 用于 prompt，hits_by_number 用于引用验证。
    失败方式：对象只由成功构建产生；预算失败由 build_numbered_context 先抛出。
    """

    text: str
    hits_by_number: Mapping[int, SearchHit]


def build_numbered_context(hits: list[SearchHit], *, max_evidence_chars: int) -> NumberedContext:
    """构建 numbered context
    Args:
        hits: Retriever 返回的有序结果
        max_evidence_chars: 最终渲染证据区域的字符数
    Returns:
        NumberedContext：文本和不可变编号映射
    Raises:
        TypeError：预算是 bool 或非整数
        ValueError：整数预算小于 1
        ContextBudgetError：无法容纳第一条完整渲染证据
    """
    if isinstance(max_evidence_chars, bool) or not isinstance(max_evidence_chars, int):
        raise TypeError("max_evidence_chars 必须是正整数")
    if max_evidence_chars < 1:
        raise ValueError("max_evidence_chars 必须是正整数")
    text: str = ""
    hits_by_number: dict[int, SearchHit] = {}
    for index, hit in enumerate(hits, start=1):
        if text == "":
            candidate_text = f"[{index}]:{hit.text}"
        else:
            candidate_text = text + f" [{index}]:{hit.text}"
        if len(candidate_text) > max_evidence_chars:
            break
        text = candidate_text
        hits_by_number[index] = hit
    if len(hits_by_number) == 0:
        raise ContextBudgetError("上下文预算不足，无法构建 numbered context")

    return NumberedContext(text=text, hits_by_number=MappingProxyType(hits_by_number))


@dataclass(frozen=True)
class Citation:
    """服务端生成的不可变可信引用。

    输入来源：number 是模型声明并经本次编号映射验证通过的局部编号；
    source_file、page、chunk_id 只来自该编号对应的 SearchHit。
    输出用途：把正式答案中的 [n] 映射到服务端保存的来源、页码和稳定 chunk。
    失败方式：编号不存在或引用合同不成立时，由
    validate_and_build_citations 先抛出 CitationValidationError，
    不构造 Citation；模型没有填写引用元数据的入口。
    """

    number: int
    source_file: str
    page: int
    chunk_id: str


def validate_and_build_citations(
    model_output: str, numbered_context: NumberedContext
) -> tuple[Citation, ...]:
    """校验并构建引用
    Args:
        model_output: 模型输出
        numbered_context: 编号上下文
    Returns:
        tuple[Citation, ...]: 引用
    Raises:
        TypeError: model_output 必须是字符串
        ValueError: model_output 必须是非空字符串
        CitationValidationError: model_output 必须包含至少一个编号引用
        CitationValidationError: model_output 必须包含答案主体
        CitationValidationError: 编号为非法编号，不存在
    """
    if not isinstance(model_output, str):
        raise TypeError("model_output 必须是字符串")
    if not model_output.strip():
        raise ValueError("model_output 必须是非空字符串")
    citation_pattern = r"\[([0-9]+)\]"
    number_texts = re.findall(citation_pattern, model_output)
    if not number_texts:
        raise CitationValidationError("model_output 必须包含至少一个编号引用")
    numbers = [int(number_text) for number_text in number_texts]
    answer_body = re.sub(citation_pattern, "", model_output).strip()
    if not answer_body.strip():
        raise CitationValidationError("model_output 必须包含答案主体")
    for number in numbers:
        if number not in numbered_context.hits_by_number:
            raise CitationValidationError(f"编号 {number} 为非法编号，不存在")
    final_numbers = list(dict.fromkeys(numbers))
    citations: list[Citation] = []
    for number in final_numbers:
        citation = Citation(
            number=number,
            source_file=numbered_context.hits_by_number[number].source_file,
            page=numbered_context.hits_by_number[number].page,
            chunk_id=numbered_context.hits_by_number[number].chunk_id,
        )
        citations.append(citation)
    return tuple(citations)


@dataclass(frozen=True)
class RAGResult:
    """输入：经过引用验证的答案和服务端 Citation。
    输出：唯一允许离开 RAGService的正式成功对象。
    失败：内容为空或 Citation 序列为空时不得成为成功结果
    """

    content: str
    citations: tuple[Citation, ...]

    def __post_init__(self) -> None:
        """校验正式成功结果的答案和引用均非空；
        内容非法时抛出 GenerationError，引用序列为空时抛出 CitationValidationError。
        """
        if not isinstance(self.content, str) or not self.content.strip():
            raise GenerationError("content 必须是非空字符串")
        if not self.citations:
            raise CitationValidationError("citations 必须是非空序列")


class LLMClient(Protocol):
    """定义控制层所依赖的可替换非流式模型调用边界；
    具体实现接收 prompt、返回未验证的非空生成内容，
    并在超时或调用失败时抛出异常
    """

    def generate(self, prompt: str) -> str:
        """使用控制层构造好的 prompt 执行一次非流式生成；
        输入是非空 prompt，输出是未经过引用验证的非空文本，
        失败时由具体实现抛出异常

        Args:
            prompt: 控制层构造好的 prompt
        Returns:
            未经过引用验证的生成内容
        Raises:
            超时或调用失败时由具体实现抛出异常
        """
        ...


class RAGService:
    """协调可信非流式 RAG 成功链。

    依次协调现有 Retriever、空证据闸门、预算内编号 Context、
    LLMClient.generate 和引用验证。
    只有模型答案正文非空、至少包含一个引用且所有编号均存在时，
    才返回带服务端 Citation 的唯一正式 RAGResult。

    TrustedContext 只传给 Retriever，不进入模型 prompt。
    本服务不负责真实模型客户端实现、正式用户拒答、API 或 SSE。
    """

    def __init__(
        self,
        retriever: Retriever,
        llm_client: LLMClient,
        max_evidence_chars: int,
    ) -> None:
        """初始化 RAG 控制层及固定证据字符预算。

        Args:
            retriever: 现有检索器，接收 query、TrustedContext 和业务过滤条件，
                返回有序 SearchHit 列表；失败由 answer 转换为 RetrievalError。
            llm_client: 非流式模型调用边界，接收 prompt 并返回不可信原始字符串；
                调用失败由 answer 转换为 GenerationError。
            max_evidence_chars: 单次请求允许进入模型的最终渲染证据区域字符数；
                只约束编号证据文本，不代表完整 prompt 或真实 token 窗口。
        """
        self._retriever = retriever
        self._llm_client = llm_client
        self._max_evidence_chars = max_evidence_chars

    def answer(
        self,
        query: str,
        *,
        context: TrustedContext,
        top_k: int = 5,
        filters: SearchFilters | None = None,
    ) -> RAGResult:
        """执行一次非流式可信 RAG 请求。

        Args:
            query: 用户问题；传给 Retriever，并作为问题文本进入模型 prompt。
            context: 服务端认证后产生的可信 workspace 上下文；
                只传给 Retriever，不进入模型 prompt。
            top_k: Retriever 最多返回的候选证据数量。
            filters: 用户允许选择的业务检索过滤条件，不包含可信 workspace。

        Returns:
            唯一正式 RAGResult；content 保留已验证的内联 [n]，
            citations 保存按首次引用顺序生成的服务端可信引用。

        Raises:
            RetrievalError: Retriever 调用失败，并保留底层异常 cause。
            NoEvidenceError: Retriever 成功执行但返回空证据列表。
            ContextBudgetError: 非空检索结果中，第一条完整渲染证据也无法进入预算。
            GenerationError: LLMClient 调用失败、超时，或没有返回有效非空字符串。
            CitationValidationError: 模型草稿无引用、无答案正文，或包含不存在的编号。
        """
        try:
            search_hits = self._retriever.retrieve(
                query, context=context, top_k=top_k, filters=filters
            )
        except Exception as exc:
            raise RetrievalError(f"检索失败: {exc}") from exc

        if not search_hits:
            raise NoEvidenceError("没有检索到证据")

        numbered_context = build_numbered_context(
            search_hits, max_evidence_chars=self._max_evidence_chars
        )
        prompt = (
            "请只依据下面带编号的证据回答问题，不要引入证据以外的信息。\n"
            "答案中的每个事实性结论都必须使用内联 [n] 标明证据编号。\n"
            "只返回答案正文和引用编号，不要返回或猜测 source_file、page、chunk_id。\n\n"
            f"问题：{query}\n\n"
            f"证据：\n{numbered_context.text}"
        )
        try:
            content = self._llm_client.generate(prompt)

        except Exception as exc:
            raise GenerationError(f"生成失败: {exc}") from exc

        if not isinstance(content, str) or not content.strip():
            raise GenerationError("content 必须是非空字符串")

        citations: tuple[Citation, ...] = validate_and_build_citations(content, numbered_context)
        return RAGResult(content=content, citations=citations)

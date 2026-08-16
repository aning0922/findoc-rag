from dataclasses import dataclass
from typing import Protocol

from app.rag.retriever import Retriever, TrustedContext, SearchFilters


class GenerationError(RuntimeError):
    """generation 阶段因超时、调用失败或无有效内容而失败，不能作为空证据或成功结果处理"""


class RetrievalError(RuntimeError):
    """RAG 控制层报告 retrieval 阶段失败的异常"""


class NoEvidenceError(RuntimeError):
    """最小 evidence gate 未通过时抛出的领域错误"""


@dataclass(frozen=True)
class RAGResult:
    """Day44 最小 RAG 成功结果；接收并保存未经引用校验的非空生成内容，内容非法时抛出 GenerationError"""

    content: str

    def __post_init__(self) -> None:
        """校验生成内容是否为非空字符串，非法时抛出 GenerationError"""
        if not isinstance(self.content, str) or not self.content.strip():
            raise GenerationError("content 必须是非空字符串")


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
    """协调现有 Retriever、最小 evidence gate、prompt 构造和 LLMClient；
    成功返回未经引用校验的 RAGResult，检索失败、空证据或生成失败时抛出对应异常，
    不负责正式引用校验和拒答策略
    """

    def __init__(self, retriever: Retriever, llm_client: LLMClient) -> None:
        """初始化 RAGService
        Args:
            retriever: 检索器
            llm_client: LLM 客户端
        """
        self._retriever = retriever
        self._llm_client = llm_client

    def answer(
        self,
        query: str,
        *,
        context: TrustedContext,
        top_k: int = 5,
        filters: SearchFilters | None = None,
    ) -> RAGResult:
        """执行 RAG 服务
        Args:
            query: 查询词
            context: 可信的上下文
            top_k: 返回的搜索结果数量
            filters: 业务过滤条件
        Returns:
            RAG 结果
        Raises:
            RetrievalError: 检索失败
            NoEvidenceError: 没有检索到证据
            GenerationError: 生成失败
        """
        try:
            search_hits = self._retriever.retrieve(
                query, context=context, top_k=top_k, filters=filters
            )
        except Exception as exc:
            raise RetrievalError(f"检索失败: {exc}") from exc

        if not search_hits:
            raise NoEvidenceError("没有检索到证据")

        hits_text = "\n\n---\n\n".join([hit.text for hit in search_hits])
        prompt = f"请根据下面提供的证据回答问题，不要引入证据以外的信息:\n\n问题：{query}\n\n证据：{hits_text}"

        try:
            content = self._llm_client.generate(prompt)
        except Exception as exc:
            raise GenerationError(f"生成失败: {exc}") from exc

        return RAGResult(content=content)

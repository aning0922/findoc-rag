import os
from collections.abc import Mapping
from typing import Self

from openai import APITimeoutError, Client


class OpenAICompatibleLLMClient:
    """将现有 LLMClient Protocol 适配到同步 OpenAI 兼容 Chat Completions。

    本类只负责调用注入的 SDK client 并原样返回模型正文；
    不解析领域 JSON、不判断拒答、不构造 Citation 或 RAGOutcome。
    SDK 超时被规范化为内置 TimeoutError；
    其他供应商异常原样传播，由 RAGService 映射为系统失败。
    """

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Self:
        """从显式映射或当前进程环境创建同步 OpenAI 兼容模型适配器。

        Args:
            env: 可选的字符串配置映射；为 None 时读取 os.environ。
                显式传入映射主要用于离线测试和受控配置构造。

        Returns:
            保存模型名并持有已配置同步 SDK client 的适配器。

        Raises:
            KeyError: 必填配置缺失。
            ValueError: 超时无法转换为数字。
            SDK 构造异常: API key、base_url 或 timeout 不被 SDK 接受。

        边界:
            本方法不加载 .env、不打印或返回 API key，也不调用模型接口。
        """
        if env is None:
            env = os.environ
        return cls(
            model=env["LLM_MODEL"],
            client=Client(
                api_key=env["LLM_API_KEY"],
                base_url=env["LLM_BASE_URL"],
                timeout=float(env["LLM_TIMEOUT_SECONDS"]),
            ),
        )

    def __init__(self, model: str, client: Client) -> None:
        """初始化同步模型适配器。

        Args:
            model: 每次 Chat Completions 调用使用的模型名称。
            client: 已配置认证信息、base_url 和超时的 OpenAI 兼容 SDK client。

        边界:
            本构造路径不读取环境变量，也不访问网络，便于普通 pytest 注入 fake。
        """
        self.model = model
        self.client = client

    def generate(self, prompt: str) -> str:
        """执行一次同步非流式生成并返回未经验证的原始模型正文。

        Args:
            prompt: RAGService 已构造完成的非空业务提示词。

        Returns:
            首个 choice 的 message.content；供应商返回 None 时转换为空字符串，
            由 RAGService 归类为 empty_model_output。

        Raises:
            TimeoutError:
                SDK 调用超时时抛出，并保留原始 APITimeoutError 为 cause。
            其他 SDK 异常:
                网络、鉴权、额度等异常原样传播，由 RAGService 统一映射。

        边界:
            不解析或修复 JSON、Markdown、拒答协议和引用编号。
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model, messages=[{"role": "user", "content": prompt}], stream=False
            )
        except APITimeoutError as exc:
            raise TimeoutError("模型调用超时") from exc
        if response.choices[0].message.content is None:
            return ""
        return response.choices[0].message.content

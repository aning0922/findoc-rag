from unittest.mock import MagicMock, patch

import httpx
import pytest
from openai import APITimeoutError

from app.rag.openai_compatible_llm import OpenAICompatibleLLMClient


def test_generate_uses_injected_sync_client_and_returns_raw_content() -> None:
    """输入为注入的同步 OpenAI 兼容 SDK client、固定模型名和完整 prompt；
    预期 generate 只发起一次非流式 Chat Completions 调用，并原样返回
    首个 choice 的 message.content；
    若读取真实环境、访问网络、修改模型正文或调用错误的模型与 prompt，
    说明真实模型适配器的依赖注入或透明传输合同被破坏。
    """
    model = "test-model"
    prompt = "请只依据编号证据回答问题。"
    raw_content = '{"decision":"answer","content":"营业收入为100亿元 [1]"}'
    sdk_client = MagicMock()
    sdk_response = MagicMock()
    sdk_response.choices = [MagicMock()]
    sdk_response.choices[0].message.content = raw_content
    sdk_client.chat.completions.create.return_value = sdk_response
    llm_client = OpenAICompatibleLLMClient(
        model=model,
        client=sdk_client,
    )
    result = llm_client.generate(prompt)
    assert result == raw_content

    sdk_client.chat.completions.create.assert_called_once_with(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        stream=False,
    )


def test_generate_normalizes_sdk_timeout_to_builtin_timeout_error() -> None:
    """输入为在 Chat Completions 调用时抛出 APITimeoutError 的注入 SDK client；
    预期 generate 将其规范化为内置 TimeoutError，并保留原异常为 cause；
    若原始 SDK 异常直接逃逸或被转换成普通返回值，
    RAGService 将无法稳定映射 llm_timeout 系统终态。
    """
    prompt = "请依据证据回答问题。"
    request = httpx.Request(
        "POST",
        "https://example.invalid/v1/chat/completions",
    )
    sdk_timeout = APITimeoutError(request=request)
    sdk_client = MagicMock()
    sdk_client.chat.completions.create.side_effect = sdk_timeout
    llm_client = OpenAICompatibleLLMClient(
        model="test-model",
        client=sdk_client,
    )
    with pytest.raises(TimeoutError) as exc_info:
        llm_client.generate(prompt)
    assert exc_info.value.__cause__ is sdk_timeout
    sdk_client.chat.completions.create.assert_called_once_with(
        model="test-model",
        messages=[{"role": "user", "content": prompt}],
        stream=False,
    )
    assert str(exc_info.value) == "模型调用超时"


def test_from_env_builds_configured_sync_client_without_network() -> None:
    """输入为包含模型、base_url、测试 API key 和超时的内存环境配置；
    预期 from_env 使用这些值构造同步 SDK client，并返回持有该 client
    和模型名的 OpenAICompatibleLLMClient，构造期间不调用模型接口；
    若读取真实环境、忽略配置、泄露密钥或发起模型调用，
    说明真实配置入口与离线测试边界被破坏。
    """
    env: dict[str, str] = {
        "LLM_MODEL": "test-model",
        "LLM_BASE_URL": "https://example.invalid/v1",
        "LLM_API_KEY": "test-api-key",
        "LLM_TIMEOUT_SECONDS": "12.5",
    }
    with patch("app.rag.openai_compatible_llm.Client") as client_class:
        sdk_client = client_class.return_value
        llm_client = OpenAICompatibleLLMClient.from_env(env)
        client_class.assert_called_once_with(
            api_key="test-api-key",
            base_url="https://example.invalid/v1",
            timeout=12.5,
        )
        assert llm_client.model == "test-model"
        assert llm_client.client is sdk_client
        sdk_client.chat.completions.create.assert_not_called()
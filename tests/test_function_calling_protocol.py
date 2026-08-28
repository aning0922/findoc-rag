import json
from copy import deepcopy
from pydantic import BaseModel, ConfigDict
import pytest

from app.agent.tool_loop import (
    LoopFailure,
    LoopFailureType,
    LoopSuccess,
    ToolErrorType,
    ToolExecutionContext,
    ToolSpec,
    run_tool_loop,
)
from app.rag.retriever import SearchFilters, TrustedContext

Message = dict[str, object]

FakeToolExecutionContext = ToolExecutionContext(
    trusted_context=TrustedContext(
        workspace_id="WS-A",
    ),
    filters=SearchFilters(
        source_file="demo.pdf",
        document_id="DOC-7",
    ),
)


class ScriptedFakeModel:
    """按预设顺序返回assistant消息，并记录每次收到的消息快照。

    输入：
        responses是有限的assistant响应序列；
        complete接收当前累计messages。
    输出：
        每次complete返回下一条预设assistant消息。
    正常路径：
        记录messages快照，消费一条响应并推进游标。
    失败：
        预设响应已耗尽时明确抛错。
    责任边界：
        只模拟模型响应和记录输入，不解析参数、不执行工具、不控制loop。
    """

    def __init__(self, responses: list[Message]) -> None:
        self._responses = responses
        self._cursor = 0
        self.received_messages: list[list[Message]] = []

    def complete(self, messages: list[Message]) -> Message:
        """接收当前消息历史并返回下一条预设assistant消息。"""
        self.received_messages.append(deepcopy(messages))
        if self._cursor >= len(self._responses):
            raise RuntimeError("scripted fake预设响应已耗尽")
        response = self._responses[self._cursor]
        self._cursor += 1
        return response


def lookup_demo_item(execution_context: ToolExecutionContext, item_id: str) -> dict[str, object]:
    """根据样品ID返回样品标签。

    输入：
        execution_context：工具执行上下文，ToolExecutionContext对象
        item_id：样品 ID，字符串
    输出：
        包含item_id和label的dict[str, str]。
    正常路径：
        找到ID为item_id的样品，返回其标签。
    失败：
        item_id不是A-7时抛出LookupError
    责任边界：
        工具只处理已交给它的业务参数，不解析assistant消息，也不决定授权和loop终止。
    """
    if item_id != "A-7":
        raise LookupError(f"未找到ID为{item_id}的样品")
    return {"item_id": item_id, "label": "蓝色样品"}


def test_scripted_fake_records_tool_call_and_result_message_sequence() -> None:
    """输入为一次用户消息和两条预设assistant响应；
    预期应用依次追加assistant工具请求、关联同一tool_call_id的工具结果和最终回答，
    且fake模型保存的两次messages快照顺序正确、互不污染；
    若工具被重复执行、消息顺序错误、ID不匹配或脚本没有有限结束，则测试失败。
    """

    tool_request: Message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_001",
                "type": "function",
                "function": {"name": "lookup_demo_item", "arguments": '{"item_id":"A-7"}'},
            }
        ],
    }
    final_response: Message = {"role": "assistant", "content": "条目A-7是蓝色样品。"}

    fake_model = ScriptedFakeModel([tool_request, final_response])
    messages: list[Message] = [
        {"role": "user", "content": "条目A-7是什么？"},
    ]

    first_assistant_message = fake_model.complete(messages)

    messages.append(first_assistant_message)

    raw_tool_calls = first_assistant_message.get("tool_calls")
    assert isinstance(raw_tool_calls, list)
    assert len(raw_tool_calls) == 1
    tool_call = raw_tool_calls[0]
    assert isinstance(tool_call, dict)
    function_call = tool_call.get("function")
    assert isinstance(function_call, dict)
    arguments = function_call.get("arguments")
    assert isinstance(arguments, str)
    parsed_arguments = json.loads(arguments)
    assert isinstance(parsed_arguments, dict)
    item_id = parsed_arguments.get("item_id")
    assert isinstance(item_id, str)
    tool_name = function_call.get("name")
    assert tool_name == "lookup_demo_item"

    tool_result = lookup_demo_item(FakeToolExecutionContext, item_id)
    tool_call_id = tool_call.get("id")
    assert isinstance(tool_call_id, str)
    tool_result_json = json.dumps(tool_result, ensure_ascii=False)
    tool_message: Message = {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": tool_result_json,
    }
    messages.append(tool_message)
    second_assistant_message = fake_model.complete(messages)
    messages.append(second_assistant_message)

    assert len(fake_model.received_messages) == 2

    # 第一次模型调用前，历史中只有user消息。
    assert fake_model.received_messages[0] == messages[:1]

    # 第二次模型调用前，历史中已有user、assistant.tool_calls和tool。
    assert fake_model.received_messages[1] == messages[:3]

    # 同一个调用ID完成关联。
    assert tool_call_id == "call_001"

    # 工具结果确实被序列化后回填。
    assert json.loads(tool_result_json) == tool_result

    # 第二次响应是预设最终回答。
    assert second_assistant_message == final_response

    # 最终累计顺序正确。
    assert [message["role"] for message in messages] == [
        "user",
        "assistant",
        "tool",
        "assistant",
    ]


class LookupDemoItemArguments(BaseModel):
    """fake工具的严格参数schema。

    输入：
        模型arguments解析得到的JSON对象。
    输出：
        只包含字符串item_id的已校验参数对象。
    输出：
        包含item_id和label的dict[str, object]。
    正常路径：
        item_id存在且类型为字符串。
    失败：
        缺少item_id、类型错误或出现额外字段时校验失败。
    责任边界：
        只校验fake工具业务参数，不决定工具授权、执行或loop终止。
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    item_id: str


def test_registry_binds_allowed_tool_name_to_schema_and_callable() -> None:
    """输入为唯一允许的fake工具名、严格Pydantic参数schema和Python函数对象；
    预期registry使用工具名作为key，并通过ToolSpec同时保存schema与callable；
    若registry保存的是函数调用结果、字符串函数名、错误schema，
    或模型可以通过未注册名称获得callable，则allowlist责任边界被破坏；
    本测试只验证可信注册关系，不解析模型消息、不执行工具，也不控制loop。
    """
    registry = {
        "lookup_demo_item": ToolSpec(
            arguments_schema=LookupDemoItemArguments,
            handler=lookup_demo_item,
        )
    }

    tool_spec = registry["lookup_demo_item"]
    assert tool_spec.arguments_schema is LookupDemoItemArguments
    assert tool_spec.handler is lookup_demo_item
    assert "unknown_tool" not in registry


def test_run_tool_loop_executes_allowed_tool_and_returns_final_answer() -> None:
    """验证允许的单工具调用能够形成完整成功闭环。

    输入：
        一条用户消息、依次返回工具请求与最终文本的scripted fake，
        以及只注册lookup_demo_item的allowlist。
    输出：
        loop执行工具一次，使用原tool_call_id回填结果，并返回LoopSuccess。
    正常路径：
        消息依次形成user、assistant.tool_calls、tool和assistant final。
    失败：
        未执行注册工具、关联ID错误、消息顺序错误、未再次请求模型
        或没有有限返回最终回答时测试失败。
    责任边界：
        本测试只验证正常协议闭环，不覆盖非法参数、未知工具或执行异常。
    """
    received_execution_contexts: list[ToolExecutionContext] = []

    def recording_lookup_demo_item(
        execution_context: ToolExecutionContext,
        item_id: str,
    ) -> dict[str, object]:
        """记录服务端注入的执行上下文，再调用原fake业务函数。"""
        received_execution_contexts.append(execution_context)
        return lookup_demo_item(execution_context, item_id)

    user_message: Message = {"role": "user", "content": "条目A-7是什么？"}
    tool_request: Message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_001",
                "type": "function",
                "function": {"name": "lookup_demo_item", "arguments": '{"item_id":"A-7"}'},
            }
        ],
    }
    final_response: Message = {"role": "assistant", "content": "条目A-7是蓝色样品。"}
    fake_model = ScriptedFakeModel([tool_request, final_response])
    messages: list[Message] = [user_message]
    registry = {
        "lookup_demo_item": ToolSpec(
            arguments_schema=LookupDemoItemArguments,
            handler=recording_lookup_demo_item,
        )
    }

    outcome = run_tool_loop(
        model=fake_model,
        messages=messages,
        registry=registry,
        execution_context=FakeToolExecutionContext,
    )

    assert isinstance(outcome, LoopSuccess)

    assert outcome.final_answer == "条目A-7是蓝色样品。"
    assert [message["role"] for message in outcome.messages] == [
        "user",
        "assistant",
        "tool",
        "assistant",
    ]
    assert received_execution_contexts == [FakeToolExecutionContext]
    tool_message = outcome.messages[2]
    assert tool_message["tool_call_id"] == "call_001"

    assert len(fake_model.received_messages) == 2
    assert [message["role"] for message in fake_model.received_messages[1]] == [
        "user",
        "assistant",
        "tool",
    ]


def test_run_tool_loop_rejects_invalid_json_without_executing_tool() -> None:
    """验证非法JSON参数在工具执行前被拒绝并形成可关联错误。

    输入：
        一条包含有效tool_call_id、已注册工具名和非法arguments JSON的工具请求。
    输出：
        loop使用原tool_call_id回填INVALID_ARGUMENTS，并返回工具失败终态。
    正常路径：
        应用解析ToolCall后在JSON解码阶段拒绝参数，不进入schema和工具执行。
    失败：
        非法参数被交给工具、错误类型不明确、关联ID改变
        或loop继续消费额外fake响应时测试失败。
    责任边界：
        本测试只覆盖JSON语法错误，不覆盖schema字段错误或工具内部异常。
    """

    user_message: Message = {"role": "user", "content": "条目A-7是什么？"}
    tool_request: Message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_bad_json",
                "type": "function",
                "function": {
                    "name": "lookup_demo_item",
                    "arguments": '{"item_id":',
                },
            }
        ],
    }
    fake_model = ScriptedFakeModel([tool_request])
    messages: list[Message] = [user_message]
    registry = {
        "lookup_demo_item": ToolSpec(
            arguments_schema=LookupDemoItemArguments,
            handler=lookup_demo_item,
        )
    }

    outcome = run_tool_loop(
        model=fake_model,
        messages=messages,
        registry=registry,
        execution_context=FakeToolExecutionContext,
    )

    assert isinstance(outcome, LoopFailure)
    assert outcome.failure_type is LoopFailureType.TOOL_ERROR

    assert outcome.tool_error is not None
    assert outcome.tool_error.error_type is ToolErrorType.INVALID_ARGUMENTS

    assert outcome.tool_error.tool_call_id == "call_bad_json"

    assert [message["role"] for message in outcome.messages] == [
        "user",
        "assistant",
        "tool",
    ]
    tool_message = outcome.messages[2]
    assert tool_message["tool_call_id"] == "call_bad_json"

    assert len(fake_model.received_messages) == 1

    tool_content = tool_message["content"]
    assert isinstance(tool_content, str)
    error_payload = json.loads(tool_content)

    assert error_payload["ok"] is False
    assert error_payload["error"]["type"] == "invalid_arguments"


@pytest.mark.parametrize(
    "arguments_json",
    [
        "{}",
        '{"item_id": 7}',
    ],
)
def test_run_tool_loop_rejects_arguments_that_violate_schema(
    arguments_json: str,
) -> None:
    """验证合法JSON仍必须通过严格工具参数schema。

    输入：
        分别缺少item_id和把item_id写成整数的两个合法JSON对象。
    输出：
        loop在工具执行前回填INVALID_ARGUMENTS，并形成工具失败终态。
    正常路径：
        JSON解码成功，但严格Pydantic schema拒绝缺字段或错误类型。
    失败：
        schema错误被交给工具、被自动类型转换、错误ID无法关联
        或loop没有有限停止时测试失败。
    责任边界：
        本测试只覆盖schema校验，不覆盖JSON语法错误或工具内部异常。
    """

    user_message: Message = {"role": "user", "content": "条目A-7是什么？"}
    tool_request: Message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_bad_schema",
                "type": "function",
                "function": {"name": "lookup_demo_item", "arguments": arguments_json},
            }
        ],
    }
    fake_model = ScriptedFakeModel([tool_request])
    messages: list[Message] = [user_message]
    registry = {
        "lookup_demo_item": ToolSpec(
            arguments_schema=LookupDemoItemArguments,
            handler=lookup_demo_item,
        )
    }

    outcome = run_tool_loop(
        model=fake_model,
        messages=messages,
        registry=registry,
        execution_context=FakeToolExecutionContext,
    )

    assert isinstance(outcome, LoopFailure)
    assert outcome.failure_type is LoopFailureType.TOOL_ERROR

    assert outcome.tool_error is not None
    assert outcome.tool_error.error_type is ToolErrorType.INVALID_ARGUMENTS
    assert outcome.tool_error.tool_call_id == "call_bad_schema"

    assert [message["role"] for message in outcome.messages] == [
        "user",
        "assistant",
        "tool",
    ]
    assert outcome.messages[2]["tool_call_id"] == "call_bad_schema"

    # schema失败后立即结束，没有再次请求模型。
    assert len(fake_model.received_messages) == 1


def test_run_tool_loop_rejects_unknown_tool_without_execution() -> None:
    """验证模型请求未注册工具时应用通过allowlist拒绝执行。

    输入：
        一条结构合法、ID有效，但工具名不在registry中的工具请求。
    输出：
        loop使用原tool_call_id回填UNKNOWN_TOOL，并形成工具失败终态。
    正常路径：
        应用完成ToolCall解析，在registry查找阶段拒绝未知名称。
    失败：
        未注册名称获得Python callable、错误无法关联
        或loop继续消费模型响应时测试失败。
    责任边界：
        本测试只验证registry授权边界，不覆盖参数schema或工具内部异常。
    """

    user_message: Message = {"role": "user", "content": "条目A-7是什么？"}
    tool_request: Message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_unknown",
                "type": "function",
                "function": {"name": "unknown_tool", "arguments": '{"item_id":"A-7"}'},
            }
        ],
    }
    fake_model = ScriptedFakeModel([tool_request])
    messages: list[Message] = [user_message]
    registry = {
        "lookup_demo_item": ToolSpec(
            arguments_schema=LookupDemoItemArguments,
            handler=lookup_demo_item,
        )
    }

    outcome = run_tool_loop(
        model=fake_model,
        messages=messages,
        registry=registry,
        execution_context=FakeToolExecutionContext,
    )

    assert isinstance(outcome, LoopFailure)
    assert outcome.failure_type is LoopFailureType.TOOL_ERROR

    assert outcome.tool_error is not None
    assert outcome.tool_error.error_type is ToolErrorType.UNKNOWN_TOOL
    assert outcome.tool_error.tool_call_id == "call_unknown"

    assert [message["role"] for message in outcome.messages] == [
        "user",
        "assistant",
        "tool",
    ]
    assert outcome.messages[2]["tool_call_id"] == "call_unknown"

    # 应用在第一次模型响应后就拒绝并停止。
    assert len(fake_model.received_messages) == 1

    content = outcome.messages[2]["content"]
    assert isinstance(content, str)
    payload = json.loads(content)

    assert payload["ok"] is False
    assert payload["error"]["type"] == "unknown_tool"


def test_run_tool_loop_returns_protocol_error_when_tool_call_id_is_missing() -> None:
    """验证缺失tool_call_id的请求形成不可关联协议失败。

    输入：
        一条包含工具名和arguments、但没有tool_call_id的assistant工具请求。
    输出：
        loop不执行工具、不追加tool消息，并返回PROTOCOL_ERROR。
    正常路径：
        应用保留原assistant响应用于诊断，在结构校验阶段立即停止。
    失败：
        应用伪造调用ID、构造ToolError、追加无法关联的tool消息
        或继续请求模型时测试失败。
    责任边界：
        本测试只覆盖调用ID缺失，不覆盖已有有效ID后的工具处理错误。
    """

    user_message: Message = {"role": "user", "content": "条目A-7是什么？"}
    tool_request: Message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "type": "function",
                "function": {"name": "lookup_demo_item", "arguments": '{"item_id":"A-7"}'},
            },
        ],
    }
    fake_model = ScriptedFakeModel([tool_request])
    messages: list[Message] = [user_message]
    registry = {
        "lookup_demo_item": ToolSpec(
            arguments_schema=LookupDemoItemArguments,
            handler=lookup_demo_item,
        )
    }

    outcome = run_tool_loop(
        model=fake_model,
        messages=messages,
        registry=registry,
        execution_context=FakeToolExecutionContext,
    )

    assert isinstance(outcome, LoopFailure)
    assert outcome.failure_type is LoopFailureType.PROTOCOL_ERROR

    # 协议错误不是可关联的工具错误。
    assert outcome.tool_error is None

    # assistant原始错误响应可以保留用于诊断，但不能伪造tool响应。
    assert [message["role"] for message in outcome.messages] == [
        "user",
        "assistant",
    ]
    assert all(message["role"] != "tool" for message in outcome.messages)

    # 第一次响应后立即结束。
    assert len(fake_model.received_messages) == 1


def test_run_tool_loop_rejects_repeated_tool_call_id_without_reexecution() -> None:
    """验证相同tool_call_id再次出现时工具不会被重复执行。

    输入：
        scripted fake连续返回两条具有相同ID、工具名和参数的工具请求。
    输出：
        第一次调用成功执行，第二次形成DUPLICATE_TOOL_CALL并失败停止。
    正常路径：
        loop通过processed_call_ids识别已处理的调用身份，回填关联错误。
    失败：
        工具执行两次、重复ID被静默接受、错误分类混淆
        或scripted fake继续运行时测试失败。
    责任边界：
        本测试只覆盖相同调用ID，不覆盖新ID请求相同操作。
    """
    call_count = 0

    def counting_lookup_demo_item(
        execution_context: ToolExecutionContext, item_id: str
    ) -> dict[str, object]:
        """记录fake工具执行次数并返回样品查询结果。

        输入：
            已通过schema校验的字符串item_id。
        输出：
            lookup_demo_item返回的结构化样品结果。
        正常路径：
            每次真正执行时递增call_count，然后调用fake业务工具。
        失败：
            item_id不存在时沿用lookup_demo_item的LookupError。
        责任边界：
            只记录工具函数执行次数，不解析消息、不判断重复或控制loop。
        """
        nonlocal call_count
        call_count += 1
        return lookup_demo_item(execution_context, item_id)

    registry = {
        "lookup_demo_item": ToolSpec(
            arguments_schema=LookupDemoItemArguments,
            handler=counting_lookup_demo_item,
        )
    }

    user_message: Message = {"role": "user", "content": "条目A-7是什么？"}
    first_request: Message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_duplicate",
                "type": "function",
                "function": {
                    "name": "lookup_demo_item",
                    "arguments": '{"item_id":"A-7"}',
                },
            }
        ],
    }

    second_request = deepcopy(first_request)

    fake_model = ScriptedFakeModel([first_request, second_request])
    messages: list[Message] = [user_message]
    outcome = run_tool_loop(
        model=fake_model,
        messages=messages,
        registry=registry,
        execution_context=FakeToolExecutionContext,
    )

    assert isinstance(outcome, LoopFailure)
    assert outcome.failure_type is LoopFailureType.TOOL_ERROR

    assert outcome.tool_error is not None
    assert outcome.tool_error.error_type is ToolErrorType.DUPLICATE_TOOL_CALL
    assert outcome.tool_error.tool_call_id == "call_duplicate"

    # 第一次请求执行成功，第二次相同ID没有再次执行。
    assert call_count == 1

    # fake只返回了两条请求，loop在第二条处停止。
    assert len(fake_model.received_messages) == 2

    assert [message["role"] for message in outcome.messages] == [
        "user",
        "assistant",  # 第一次工具请求
        "tool",  # 第一次成功结果
        "assistant",  # 第二次重复ID请求
        "tool",  # DUPLICATE_TOOL_CALL错误
    ]
    assert outcome.messages[-1]["tool_call_id"] == "call_duplicate"


def test_run_tool_loop_rejects_new_id_for_repeated_operation_without_reexecution() -> None:
    """验证新ID重复相同操作时工具不会再次执行。

    输入：
        scripted fake连续请求相同工具和参数，但第二次使用新的tool_call_id。
    输出：
        第一次调用成功，第二次形成REPEATED_OPERATION并失败停止。
    正常路径：
        新ID通过processed_call_ids检查，随后由规范化操作指纹识别重复操作。
    失败：
        第二次操作被执行、被误报为DUPLICATE_TOOL_CALL、
        错误回填到第一次ID或loop继续运行时测试失败。
    责任边界：
        本测试覆盖新调用身份下的同构操作，不覆盖相同ID重复。
    """
    call_count = 0

    def counting_lookup_demo_item(
        execution_context: ToolExecutionContext, item_id: str
    ) -> dict[str, object]:
        """记录fake工具执行次数并返回样品查询结果。

        输入：
            已通过schema校验的字符串item_id。
        输出：
            lookup_demo_item返回的结构化样品结果。
        正常路径：
            每次真正执行时递增call_count，然后调用fake业务工具。
        失败：
            item_id不存在时沿用lookup_demo_item的LookupError。
        责任边界：
            只记录工具函数执行次数，不解析消息、不判断重复或控制loop。
        """
        nonlocal call_count
        call_count += 1
        return lookup_demo_item(execution_context, item_id)

    registry = {
        "lookup_demo_item": ToolSpec(
            arguments_schema=LookupDemoItemArguments,
            handler=counting_lookup_demo_item,
        )
    }

    user_message: Message = {"role": "user", "content": "条目A-7是什么？"}
    first_request: Message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_first",
                "type": "function",
                "function": {
                    "name": "lookup_demo_item",
                    "arguments": '{"item_id":"A-7"}',
                },
            }
        ],
    }

    second_request: Message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_second",
                "type": "function",
                "function": {
                    "name": "lookup_demo_item",
                    "arguments": '{"item_id":"A-7"}',
                },
            }
        ],
    }

    fake_model = ScriptedFakeModel([first_request, second_request])
    messages: list[Message] = [user_message]
    outcome = run_tool_loop(
        model=fake_model,
        messages=messages,
        registry=registry,
        execution_context=FakeToolExecutionContext,
    )

    assert isinstance(outcome, LoopFailure)
    assert outcome.failure_type is LoopFailureType.TOOL_ERROR

    assert outcome.tool_error is not None
    assert outcome.tool_error.error_type is ToolErrorType.REPEATED_OPERATION

    # 错误应关联第二次被拒绝的新请求。
    assert outcome.tool_error.tool_call_id == "call_second"

    # 第一条执行，第二条相同操作被拦截。
    assert call_count == 1

    assert len(fake_model.received_messages) == 2

    assert [message["role"] for message in outcome.messages] == [
        "user",
        "assistant",
        "tool",
        "assistant",
        "tool",
    ]

    assert outcome.messages[-1]["tool_call_id"] == "call_second"


def test_run_tool_loop_maps_tool_exception_to_safe_tool_error() -> None:
    """验证fake工具异常被映射为安全且可关联的工具错误。

    输入：
        一条结构、工具名和参数schema均合法，但会使fake工具抛出LookupError的请求。
    输出：
        loop使用原tool_call_id回填TOOL_EXECUTION_ERROR，并形成工具失败终态。
    正常路径：
        应用执行已注册工具，捕获内部异常并只返回稳定安全错误。
    失败：
        原始异常逃出loop、敏感异常文本被回填、关联ID改变
        或异常后继续请求模型时测试失败。
    责任边界：
        本测试只覆盖工具执行异常，不覆盖协议解析、registry或schema失败。
    """

    user_message: Message = {"role": "user", "content": "条目A-7是什么？"}
    tool_request: Message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_tool_failure",
                "type": "function",
                "function": {
                    "name": "lookup_demo_item",
                    "arguments": '{"item_id":"B-9"}',
                },
            }
        ],
    }
    fake_model = ScriptedFakeModel([tool_request])
    messages: list[Message] = [user_message]
    registry = {
        "lookup_demo_item": ToolSpec(
            arguments_schema=LookupDemoItemArguments,
            handler=lookup_demo_item,
        )
    }

    outcome = run_tool_loop(
        model=fake_model,
        messages=messages,
        registry=registry,
        execution_context=FakeToolExecutionContext,
    )

    assert isinstance(outcome, LoopFailure)
    assert outcome.failure_type is LoopFailureType.TOOL_ERROR

    assert outcome.tool_error is not None
    assert outcome.tool_error.error_type is ToolErrorType.TOOL_EXECUTION_ERROR
    assert outcome.tool_error.tool_call_id == "call_tool_failure"

    assert [message["role"] for message in outcome.messages] == [
        "user",
        "assistant",
        "tool",
    ]
    assert outcome.messages[-1]["tool_call_id"] == "call_tool_failure"

    # 工具异常后立即形成失败终态，不继续请求模型。
    assert len(fake_model.received_messages) == 1

    content = outcome.messages[-1]["content"]
    assert isinstance(content, str)
    payload = json.loads(content)

    assert payload["ok"] is False
    assert payload["error"]["type"] == "tool_execution_error"
    assert payload["error"]["message"] == "工具执行异常"

    # 不向模型泄露工具抛出的原始异常细节。
    assert "未找到ID为B-9的样品" not in content

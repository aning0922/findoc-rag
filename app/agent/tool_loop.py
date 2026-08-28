from dataclasses import dataclass
from enum import StrEnum
import json

from collections.abc import Callable, Mapping
from pydantic import BaseModel, ValidationError
from typing import Protocol

from app.rag.retriever import SearchFilters, TrustedContext

Message = dict[str, object]


class LoopFailureType(StrEnum):
    """整个loop处理过程中形成的明确失败。

    输入：
        应用在协议解析、工具调用、结果回填或最终回答阶段识别出的失败类别。
    输出：
        供loop终态和自动测试比较的稳定字符串枚举值。
    正常路径：
        应用只能从当前有限枚举中选择一个明确失败类型。
    失败：
        未定义的字符串不能直接作为合法LoopFailureType使用。
    责任边界：
        只定义错误类别，不保存错误说明、messages或tool_error，
        也不决定loop是否继续。
    """

    PROTOCOL_ERROR = "protocol_error"
    """协议错误"""
    TOOL_ERROR = "tool_error"
    """工具错误"""


class ToolErrorType(StrEnum):
    """工具调用失败的稳定机器码集合。

    输入：
        应用在参数解析、registry查找、重复检测或工具执行阶段识别出的失败类别。
    输出：
        供ToolError、loop终态和自动测试比较的稳定字符串枚举值。
    正常路径：
        应用只能从当前有限枚举中选择一个明确错误类型。
    失败：
        未定义的字符串不能直接作为合法ToolErrorType使用。
    责任边界：
        只定义错误类别，不保存错误说明、tool_call_id或原始异常，
        也不决定loop是否继续。
    """

    INVALID_ARGUMENTS = "invalid_arguments"
    """无效的参数"""
    UNKNOWN_TOOL = "unknown_tool"
    """未知的工具"""
    DUPLICATE_TOOL_CALL = "duplicate_tool_call"
    """重复的工具调用"""
    REPEATED_OPERATION = "repeated_operation"
    """重复的操作"""
    TOOL_EXECUTION_ERROR = "tool_execution_error"
    """工具执行错误"""


@dataclass(frozen=True)
class ToolCall:
    """应用从单个assistant.tool_calls项提取出的工具调用申请。

    输入：
        模型生成且仍不可信的tool_call_id、工具名和原始arguments字符串。
    输出：
        为registry查找、JSON解析、schema校验和结果回填提供稳定字段。
    正常路径：
        三个字段均为非空字符串时构造不可变ToolCall。
    失败：
        字段类型错误时抛出TypeError；字段为空或只有空白时抛出ValueError。
    责任边界：
        只保证最低结构成立；不保证arguments是合法JSON，
        不查询registry，不判断授权，也不执行Python工具函数。
    """

    tool_call_id: str
    tool_name: str
    arguments_json: str

    def __post_init__(self) -> None:
        """校验ToolCall的最低结构不变量。

        输入：
            当前ToolCall中的tool_call_id、tool_name和arguments_json。
        输出：
            校验成功时不返回值，允许不可变ToolCall完成构造。
        正常路径：
            三个字段均为非空且非纯空白字符串。
        失败：
            字段不是字符串时抛出TypeError；
            字段为空或只有空白时抛出ValueError。
        责任边界：
            不解析arguments_json，不验证业务schema，
            不检查工具是否注册或调用是否授权。
        """
        if not isinstance(self.tool_call_id, str):
            raise TypeError("tool_call_id 只能是非空字符串")
        if not self.tool_call_id.strip():
            raise ValueError("tool_call_id 只能是非空字符串")
        if not isinstance(self.tool_name, str):
            raise TypeError("tool_name 只能是非空字符串")
        if not self.tool_name.strip():
            raise ValueError("tool_name 只能是非空字符串")
        if not isinstance(self.arguments_json, str):
            raise TypeError("arguments_json 只能是非空字符串")
        if not self.arguments_json.strip():
            raise ValueError("arguments_json 只能是非空字符串")


@dataclass(frozen=True)
class ToolResult:
    """一次工具成功执行后形成的关联结果。

    输入：
        原ToolCall的tool_call_id，以及工具成功返回的结构化output。
    输出：
        为具有相同tool_call_id的tool消息提供可序列化成功内容。
    正常路径：
        关联ID有效，output为能够序列化成JSON的字典时构造不可变ToolResult。
    失败：
        ID类型或内容非法、output不是字典，或者output不能序列化为JSON时拒绝构造。
    责任边界：
        只表示一次工具执行成功；不包含工具错误，
        不生成最终assistant回答，也不决定整个loop已经成功。
    """

    tool_call_id: str
    output: dict[str, object]

    def __post_init__(self) -> None:
        """校验ToolResult的关联ID和输出序列化边界。

        输入：
            当前ToolResult中的tool_call_id和output。
        输出：
            校验成功时不返回值，允许ToolResult完成构造。
        正常路径：
            tool_call_id为非空字符串，output为可JSON序列化的字典。
        失败：
            ID或output类型错误时抛出TypeError；
            ID为空白或output无法JSON序列化时抛出ValueError。
        责任边界：
            不修改工具输出，不生成tool消息，
            不验证最终模型回答，也不控制下一轮模型调用。
        """
        if not isinstance(self.tool_call_id, str):
            raise TypeError("tool_call_id 只能是非空字符串")
        if not self.tool_call_id.strip():
            raise ValueError("tool_call_id 只能是非空字符串")
        if not isinstance(self.output, dict):
            raise TypeError("output 只能是字典")
        try:
            json.dumps(self.output, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("output 必须能序列化为JSON") from exc


@dataclass(frozen=True)
class ToolError:
    """一次可关联工具请求在处理过程中形成的明确失败。

    输入：
        原ToolCall的有效tool_call_id、稳定错误类型和安全错误说明。
    输出：
        为错误回填、loop失败终态和自动测试提供结构化失败信息。
    正常路径：
        ID和说明均为非空字符串，error_type属于ToolErrorType时构造不可变ToolError。
    失败：
        字段类型错误、ID为空白或错误说明为空白时拒绝构造。
    责任边界：
        只表示能够关联到有效tool_call_id的失败；
        缺失或无法匹配ID属于外层协议失败，不能靠本对象编造关联ID。
    """

    tool_call_id: str
    error_type: ToolErrorType
    message: str

    def __post_init__(self) -> None:
        """校验ToolError的关联ID、机器码和安全说明。

        输入：
            当前ToolError中的tool_call_id、error_type和message。
        输出：
            校验成功时不返回值，允许ToolError完成构造。
        正常路径：
            ID和说明为非空字符串，错误类型为ToolErrorType成员。
        失败：
            字段类型错误时抛出TypeError；
            ID或说明为空白时抛出ValueError。
        责任边界：
            不保存或暴露traceback，不执行重试，
            也不自行决定整个loop是否继续。
        """
        if not isinstance(self.tool_call_id, str):
            raise TypeError("tool_call_id 只能是非空字符串")
        if not self.tool_call_id.strip():
            raise ValueError("tool_call_id 只能是非空字符串")
        if not isinstance(self.error_type, ToolErrorType):
            raise TypeError("error_type 只能是非空枚举值")
        if not isinstance(self.message, str):
            raise TypeError("message 只能是非空字符串")
        if not self.message.strip():
            raise ValueError("message 只能是非空字符串")


@dataclass(frozen=True)
class LoopSuccess:
    """整个受控loop正常结束后形成的成功终态。

    输入：
        模型返回的非空最终回答，以及应用累计的完整messages轨迹。
    输出：
        为调用者提供最终回答和停止时的可检查消息记录。
    正常路径：
        最终回答为非空字符串，messages为字典消息组成的tuple时构造成功终态。
    失败：
        最终回答类型错误或为空白、messages不是tuple或包含非字典元素时拒绝构造。
    责任边界：
        只表示loop按协议正常停止；
        不保证模型最终文本天然正确，也不执行引用或业务真值校验。
    """

    final_answer: str
    messages: tuple[dict[str, object], ...]

    def __post_init__(self) -> None:
        """校验LoopSuccess的最终回答和消息轨迹。

        输入：
            当前LoopSuccess中的final_answer和messages。
        输出：
            校验成功时不返回值，允许成功终态完成构造。
        正常路径：
            final_answer为非空字符串，messages为只含字典消息的tuple。
        失败：
            字段类型错误时抛出TypeError；
            final_answer为空或只有空白时抛出ValueError。
        责任边界：
            不解析messages内部协议，不重新调用模型或工具，
            也不验证最终回答的业务真值。
        """
        if not isinstance(self.final_answer, str):
            raise TypeError("final_answer 只能是非空字符串")
        if not self.final_answer.strip():
            raise ValueError("final_answer 只能是非空字符串")
        if not isinstance(self.messages, tuple):
            raise TypeError("messages 只能是元组")
        if not all(isinstance(msg, dict) for msg in self.messages):
            raise TypeError("messages 只能是字典元组")


@dataclass(frozen=True)
class LoopFailure:
    """整个受控loop无法安全继续时形成的失败终态。

    输入：
        loop失败类别、安全错误说明、停止时的messages，
        以及工具失败时对应的可选ToolError。
    输出：
        为调用者和自动测试提供明确、不可变的失败结果。
    正常路径：
        协议失败不携带ToolError；工具失败必须携带ToolError。
    失败：
        基础字段类型或内容非法，或者failure_type与tool_error组合不一致时拒绝构造。
    责任边界：
        只记录loop停止原因；不把失败伪装成最终回答，
        不生成新的关联ID，也不执行自动重试。
    """

    failure_type: LoopFailureType
    message: str
    messages: tuple[dict[str, object], ...]
    tool_error: ToolError | None = None

    def __post_init__(self) -> None:
        """校验LoopFailure的错误类别、说明、轨迹和组合关系。

        输入：
            当前LoopFailure中的failure_type、message、messages和tool_error。
        输出：
            校验成功时不返回值，允许失败终态完成构造。
        正常路径：
            协议失败对应None，工具失败对应有效ToolError。
        失败：
            字段类型错误时抛出TypeError；
            message为空白或失败类别与tool_error组合冲突时抛出ValueError。
        责任边界：
            不修复协议、不执行工具、不调用模型，
            也不决定后续请求是否重新开始新loop。
        """
        if not isinstance(self.failure_type, LoopFailureType):
            raise TypeError("failure_type 只能是非空枚举值")
        if not isinstance(self.message, str):
            raise TypeError("message 只能是非空字符串")
        if not self.message.strip():
            raise ValueError("message 只能是非空字符串")
        if not isinstance(self.messages, tuple):
            raise TypeError("messages 只能是元组")
        if not all(isinstance(msg, dict) for msg in self.messages):
            raise TypeError("messages 只能是字典元组")
        if not isinstance(self.tool_error, ToolError | None):
            raise TypeError("tool_error 只能是ToolError或None")
        if self.failure_type is LoopFailureType.TOOL_ERROR and self.tool_error is None:
            raise ValueError("工具失败终态必须包含tool_error")
        if self.failure_type is LoopFailureType.PROTOCOL_ERROR and self.tool_error is not None:
            raise ValueError("协议失败终态不能包含tool_error")


@dataclass(frozen=True)
class ToolSpec:
    """应用注册的可信工具定义。

    输入：
        应用启动时提供的Pydantic参数schema和Python callable。
    输出：
        registry命中工具名后，用于参数校验和执行的可信定义。
    正常路径：
        arguments_schema是BaseModel子类，handler是可调用对象。
        handler会接收可信执行上下文＋schema 校验后的模型参数
    失败：
        schema不是BaseModel类型或handler不可调用时拒绝构造。
    责任边界：
        只绑定校验规则与函数实现；不读取模型消息，
        不决定授权，不执行loop，也不允许模型动态注册工具。
    """

    arguments_schema: type[BaseModel]
    handler: Callable[..., dict[str, object]]

    def __post_init__(self) -> None:
        """校验registry条目的schema和callable边界。

        输入：
            当前ToolSpec中的arguments_schema和handler。
        输出：
            校验成功时不返回值，允许可信工具定义完成构造。
        正常路径：
            arguments_schema是BaseModel子类，handler是可调用对象。
        失败：
            schema不是class、不是BaseModel子类或handler不可调用时抛出TypeError。
        责任边界：
            不实例化参数schema，不执行handler，
            也不读取或修改registry中的其他工具。
        """
        if not isinstance(self.arguments_schema, type):
            raise TypeError("arguments_schema 只能是一个class")
        if not issubclass(self.arguments_schema, BaseModel):
            raise TypeError("arguments_schema 只能是BaseModel的子类")
        if not callable(self.handler):
            raise TypeError("handler 必须是可调用对象")


LoopOutcome = LoopSuccess | LoopFailure
ToolRegistry = Mapping[str, ToolSpec]


class ToolCallingModel(Protocol):
    """接收当前消息历史并返回一条assistant消息。

    输入：
        应用当前累计的messages。
    输出：
        一条仍不可信的assistant消息。
    正常路径：
        返回最终文本或单个function tool call。
    失败：
        fake剧本耗尽或模型调用失败时抛出异常。
    责任边界：
        只生成响应，不执行工具、不查询registry，也不控制loop终止。
    """

    def complete(self, messages: list[Message]) -> Message: ...


def _finish_with_protocol_error(*, error_message: str, messages: list[Message]) -> LoopFailure:
    """形成不可关联的协议失败终态。

    输入：
        非空的安全错误说明，以及应用当前维护的messages。
    输出：
        保存当前消息快照的PROTOCOL_ERROR类型LoopFailure。
    正常路径：
        当assistant结构非法或缺少有效tool_call_id时直接停止loop。
    失败：
        本函数不接收ToolError；调用方应保证错误说明为非空字符串。
    责任边界：
        只形成协议失败终态，不追加tool消息、不伪造tool_call_id，
        也不执行、回填或重试任何工具。
    """
    return LoopFailure(
        failure_type=LoopFailureType.PROTOCOL_ERROR,
        message=error_message,
        messages=tuple(messages),
    )


def _finish_with_tool_error(
    *,
    tool_error: ToolError,
    messages: list[Message],
) -> LoopFailure:
    """回填一次可关联工具错误并形成loop失败终态。

    输入：
        具有有效关联ID的ToolError和当前可变messages。
    输出：
        追加错误tool消息后的LoopFailure。
    正常路径：
        使用相同tool_call_id序列化错误内容并停止loop。
    失败：
        ToolError自身不合法时应在进入本函数前拒绝构造。
    责任边界：
        只完成错误回填和失败终止；不重试模型或工具，
        也不处理缺失ID的协议错误。
    """
    messages.append(
        {
            "role": "tool",
            "tool_call_id": tool_error.tool_call_id,
            "content": json.dumps(
                {
                    "ok": False,
                    "error": {
                        "type": tool_error.error_type.value,
                        "message": tool_error.message,
                    },
                },
                ensure_ascii=False,
            ),
        }
    )

    return LoopFailure(
        failure_type=LoopFailureType.TOOL_ERROR,
        message=tool_error.message,
        messages=tuple(messages),
        tool_error=tool_error,
    )


@dataclass(frozen=True)
class ToolExecutionContext:
    """工具执行上下文。

    输入：
        可信上下文和搜索过滤器。
    输出：
        为工具执行提供可信上下文和搜索过滤器。
    正常：
        trusted_context是TrustedContext对象，filters是SearchFilters对象或None。
    失败：
        trusted_context不是TrustedContext对象或filters不是SearchFilters对象或None时拒绝构造。
    责任边界：
        只校验两个字段的外层类型；
        workspace和过滤字段的内部不变量由TrustedContext和SearchFilters负责；
        不执行认证、授权或业务工具。
    """

    trusted_context: TrustedContext
    filters: SearchFilters | None

    def __post_init__(self) -> None:
        """校验ToolExecutionContext的边界。

        输入：
            当前ToolExecutionContext中的trusted_context和filters。
        输出：
            校验成功时不返回值，允许ToolExecutionContext完成构造。
        正常路径：
            trusted_context是TrustedContext对象，filters是SearchFilters对象或None。
        失败：
            trusted_context不是TrustedContext对象或filters不是SearchFilters对象或None时拒绝构造。
        责任边界：
            只校验两个字段的外层类型；
            workspace和过滤字段的内部不变量由TrustedContext和SearchFilters负责；
            不执行认证、授权或业务工具。
        """
        if not isinstance(self.trusted_context, TrustedContext):
            raise TypeError("trusted_context 只能是一个TrustedContext对象")
        if not isinstance(self.filters, SearchFilters | None):
            raise TypeError("filters 只能是一个SearchFilters对象或None")


def run_tool_loop(
    *,
    model: ToolCallingModel,
    messages: list[Message],
    registry: ToolRegistry,
    execution_context: ToolExecutionContext,
) -> LoopOutcome:
    """运行fake单工具受控loop并返回明确终态。

    输入：
        model是有限scripted fake；
        messages是应用维护的当前消息历史；
        registry是应用持有的唯一工具allowlist。
        execution_context是工具执行上下文，ToolExecutionContext对象
    输出：
        正常最终文本形成LoopSuccess；
        协议或工具处理失败形成LoopFailure。
    正常路径：
        模型请求工具，应用校验、执行和回填后再次调用模型，
        最终在模型返回非空文本时成功停止。
    失败：
        assistant结构非法、ID缺失或重复、工具未知、参数非法、
        操作重复、工具执行异常或fake剧本耗尽时失败停止。
    责任边界：
        应用负责解析、allowlist、参数校验、执行、回填和终止；
        模型不能直接执行函数，也不能决定授权结果。
        execution_context只能由应用传入
    """
    processed_call_ids: set[str] = set()
    processed_operations: set[tuple[str, str]] = set()

    while True:
        try:
            assistant_message = model.complete(messages)
        except RuntimeError:
            return _finish_with_protocol_error(
                error_message="scripted fake预设响应已耗尽",
                messages=messages,
            )
        if not isinstance(assistant_message, dict):
            return _finish_with_protocol_error(
                error_message="模型返回的assistant消息不是字典",
                messages=messages,
            )

        messages.append(assistant_message)

        if not assistant_message:
            return _finish_with_protocol_error(
                error_message="模型返回的assistant消息为空",
                messages=messages,
            )

        role = assistant_message.get("role")
        if role != "assistant":
            return _finish_with_protocol_error(
                error_message="模型返回消息的role必须是assistant",
                messages=messages,
            )

        content = assistant_message.get("content")
        tool_calls = assistant_message.get("tool_calls")

        if isinstance(content, str) and content.strip():
            if tool_calls is None:
                return LoopSuccess(
                    final_answer=content,
                    messages=tuple(messages),
                )
            return _finish_with_protocol_error(
                error_message="assistant最终文本不能同时携带tool_calls",
                messages=messages,
            )

        has_no_final_content = content is None or (isinstance(content, str) and not content.strip())

        if has_no_final_content and isinstance(tool_calls, list) and len(tool_calls) == 1:
            # 下一步才解析tool_calls[0]
            tool_call_dict = tool_calls[0]
            if not isinstance(tool_call_dict, dict):
                return _finish_with_protocol_error(
                    error_message="模型返回的assistant消息的tool_call必须是字典",
                    messages=messages,
                )
            function = tool_call_dict.get("function")
            if not isinstance(function, dict):
                return _finish_with_protocol_error(
                    error_message="模型返回的assistant消息的tool_call的function必须是字典",
                    messages=messages,
                )
            tool_type = tool_call_dict.get("type")
            if tool_type != "function":
                return _finish_with_protocol_error(
                    error_message="模型返回的assistant消息的tool_call的type必须是function",
                    messages=messages,
                )
            tool_call_id = tool_call_dict.get("id")
            if not isinstance(tool_call_id, str) or not tool_call_id.strip():
                return _finish_with_protocol_error(
                    error_message="模型返回的assistant消息的tool_call的function的id必须是字符串",
                    messages=messages,
                )
            function_name = function.get("name")
            if not isinstance(function_name, str) or not function_name.strip():
                return _finish_with_protocol_error(
                    error_message="模型返回的assistant消息的tool_call的function的name必须是字符串",
                    messages=messages,
                )
            function_arguments = function.get("arguments")
            if not isinstance(function_arguments, str) or not function_arguments.strip():
                return _finish_with_protocol_error(
                    error_message="模型返回的assistant消息的tool_call的function的arguments必须是字符串",
                    messages=messages,
                )
            try:
                tool_call = ToolCall(
                    tool_call_id=tool_call_id,
                    tool_name=function_name,
                    arguments_json=function_arguments,
                )
            except (TypeError, ValueError):
                return _finish_with_protocol_error(
                    error_message="tool call必要字段不符合结构合同",
                    messages=messages,
                )

            if tool_call.tool_call_id in processed_call_ids:
                return _finish_with_tool_error(
                    tool_error=ToolError(
                        tool_call_id=tool_call.tool_call_id,
                        error_type=ToolErrorType.DUPLICATE_TOOL_CALL,
                        message="tool call ID重复",
                    ),
                    messages=messages,
                )
            processed_call_ids.add(tool_call.tool_call_id)
            tool_spec = registry.get(tool_call.tool_name)
            if tool_spec is None:
                return _finish_with_tool_error(
                    tool_error=ToolError(
                        tool_call_id=tool_call.tool_call_id,
                        error_type=ToolErrorType.UNKNOWN_TOOL,
                        message="工具未知",
                    ),
                    messages=messages,
                )
            try:
                parsed_arguments = json.loads(tool_call.arguments_json)
                if not isinstance(parsed_arguments, dict):
                    return _finish_with_tool_error(
                        tool_error=ToolError(
                            tool_call_id=tool_call.tool_call_id,
                            error_type=ToolErrorType.INVALID_ARGUMENTS,
                            message="tool call arguments必须是一个字典",
                        ),
                        messages=messages,
                    )
            except json.JSONDecodeError:
                return _finish_with_tool_error(
                    tool_error=ToolError(
                        tool_call_id=tool_call.tool_call_id,
                        error_type=ToolErrorType.INVALID_ARGUMENTS,
                        message="tool call arguments不能序列化为JSON",
                    ),
                    messages=messages,
                )
            try:
                validated_arguments = tool_spec.arguments_schema.model_validate(parsed_arguments)
            except ValidationError:
                return _finish_with_tool_error(
                    tool_error=ToolError(
                        tool_call_id=tool_call.tool_call_id,
                        error_type=ToolErrorType.INVALID_ARGUMENTS,
                        message="tool call arguments不符合schema",
                    ),
                    messages=messages,
                )
            operation_key = (
                tool_call.tool_name,
                validated_arguments.model_dump_json(),
            )
            if operation_key in processed_operations:
                return _finish_with_tool_error(
                    tool_error=ToolError(
                        tool_call_id=tool_call.tool_call_id,
                        error_type=ToolErrorType.REPEATED_OPERATION,
                        message="tool call操作重复",
                    ),
                    messages=messages,
                )
            processed_operations.add(operation_key)

            try:
                output = tool_spec.handler(execution_context, **validated_arguments.model_dump())
                tool_result = ToolResult(
                    tool_call_id=tool_call.tool_call_id,
                    output=output,
                )
            except Exception:
                return _finish_with_tool_error(
                    tool_error=ToolError(
                        tool_call_id=tool_call.tool_call_id,
                        error_type=ToolErrorType.TOOL_EXECUTION_ERROR,
                        message="工具执行异常",
                    ),
                    messages=messages,
                )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_result.tool_call_id,
                    "content": json.dumps(
                        {"ok": True, "output": tool_result.output},
                        ensure_ascii=False,
                    ),
                }
            )
            continue
        return _finish_with_protocol_error(
            error_message="assistant必须返回非空最终文本或单个tool call",
            messages=messages,
        )

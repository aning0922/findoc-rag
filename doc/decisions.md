# 分块决策(FinDoc)

> Day43证据更新:2026-08-14 ｜ legacy与v2并存 ｜ 当前仍保持`400/60`，不根据同12题结果开放式调参

## 当前实现

- **正文策略**:使用`RecursiveCharacterTextSplitter.from_tiktoken_encoder`,由`cl100k_base`计数token,按中文分隔符优先级寻找边界;不用可能劈碎中文字符的`TokenTextSplitter`。
- **当前参数**:`chunk_size=400`,`chunk_overlap=60`。这是现有生产基线,不是Day38证明的最优配置。
- **表格策略**:当前保持原子块,检索`text`包含表格标题/表体,`table_md`保留原始payload用于引用;表格不进入正文splitter。
- **metadata**:`section`由adapter按标题level与原始顺序首次确定;精块只复制`source_file/page/section/table_md/type`,再生成稳定`chunk_id`。

## Day38固定样本实验

固定样本为京东方A 2025年报raw 782-787,不排除元素。size对照固定`overlap=10`,overlap对照固定`size=400`;splitter、tokenizer、分隔符、adapter、表格和metadata策略不变。完整结果见[`day38_b_results.json`](../experiments/day38_b_results.json)。

| 配置 | 最终块数 | 正文token P50/P95/max | 正文覆盖率 | 重复非空白字符 | 表格超限 |
|---|---:|---:|---:|---:|---:|
| 200/10 | 10 | 125/165.2/178 | 1.0000 | 0 | 1 |
| 400/10 | 5 | 321/374.55/378 | 1.0000 | 0 | 1 |
| 800/10 | 4 | 287/688.4/733 | 1.0000 | 0 | 0 |
| 400/60 | 5 | 321/374.55/378 | 1.0000 | 0 | 1 |

## 能得出与不能得出的结论

- size增大时,本样本的块数减少,正文长度上升,分层抽查中的孤立句号块由`2/3 → 1/3 → 0/3`;这只是结构行为,不能直接等同于检索质量。
- `400/10`与`400/60`的块内容、来源区间、长度和稳定ID完全相同,所以本样本没有观察到overlap 60带来的重复或边界改善;不能推广成overlap普遍无效。
- 陌生迁移实验[`day38_c4_overlap_transfer.py`](../experiments/day38_c4_overlap_transfer.py)中,同样的递归token splitter在`size=8`时把`overlap 0→3`表现为`3→5`块、重复非空白字符`0→12`;实际overlap必须看最终块与来源span,不能只看配置值。
- 原子表格为751 token,在size 200/400时超过配置上限但仍完整保留;这是检索单元过大的风险,不是正文splitter或存储失败。
- Day38没有查询、相关性标签、embedding或向量检索结果。Day43已修复v2上游表格text/section并完成同12题对照，但样本仍小且没有参数实验；**400/60继续保留为当前基线，后续扩展题集并预注册实验后再决定是否调整。**

## 已知边界

- 完全重复正文目前只用同payload组内出现序号区分;缺少adapter提供的真实稳定来源定位时,不能证明重复块各自对应哪个物理位置。
- `duplicate_chars`实验字段实际统计非空白原文位置的重复覆盖;覆盖率1.0与重复0都不能证明边界自然。
- 当前分层抽查规则在运行前固定,但配置对审核者可见,因此不是匿名盲评。

## Day42检索评测决策

- `eval/day42_questions.jsonl`固定为本次唯一12题评测集；10题可回答、2题无答案，相关ID从源PDF和原始chunk确认，不根据Top 5事后标注。
- `eval/day42_baseline.json`保留旧7,451-row collection的诚实结果：Hit@1 `0.20`、Hit@5 `0.40`、MRR `0.27`，探索性P50/P95为`54.44/194.75 ms`。
- baseline期间冻结模型、collection、`top_k=5`、COSINE和检索实现；发现badcase后不调参、不覆盖结果、不在评测过程中重灌数据。
- Q8证明旧表格表体只存在于`table_md`而未进入embedding text会造成精确数字召回错误。Day43/第8周优先做上游修复检查和版本化重建，再分析剩余召回错误或讨论分块参数。
- 12题、可复现baseline和陌生Gate已满足Day42结束条件；题量未达到20～30不阻塞进入Day43。第8周扩展到约25题，第11周扩展到30～50题并增加未参与调试的holdout集。

## Day43 数据v2决策

- 旧7,451行`findoc`、旧JSONL和`eval/day42_baseline.json`作为历史对照只读保留；新数据使用`day43_data_v2`、独立JSONL目录、manifest和`findoc_day43_v2`，不原地迁移。
- 固定demo workspace为`demo-financial-reports`；三份源文档各有稳定且不同的`document_id`。`chunk_id`继续由内容与稳定来源定位生成，document级替换不得影响其他文档。
- 表格检索`text`由caption和HTML可见单元格组成，`table_md`原样保留HTML用于后续引用展示；不展开`rowspan/colspan`，复杂表格后置。
- `header/footer/page_number`跳过且计数；空正文和完全空表壳按原因跳过；未知类型、非合同表格格式和无法解析的表体显式失败，不静默伪装成正文。
- v2共5,269行，真实表格退化计数、HTML残留、缺失/错配`table_md`和section污染均为0；旧`findoc`前后保持7,451行。
- 同12题对照固定bge-m3、COSINE、`top_k=5`、Retriever和指标函数。结果为Hit@1 `0.20→0.20`、Hit@5 `0.40→0.50`、MRR `0.27→0.3333`，只记录不据此调参。
- Q8说明v2已消除“不同表格只有同一弱文本”的结构缺陷，但相关表格仍未进入Top 5；这属于后续检索诊断，不回滚上游修复，也不在Day43引入hybrid/rerank。

## 可信问答SSE与runtime浏览器链决策（2026-08-26）

### 数据与身份边界

- Day46冻结评测资产继续只读保留：`eval/trusted_rag_baseline_v1.json`的SHA-256为`ce997a7e880cff87ee08c24c48ef6472a88abb1f36cd1b1fcad21af0be6c141d`，`findoc_day43_v2`仍为5,269行。
- 浏览器上传只写入`data/runtime/`下的SQLite、LocalObjectStore和`findoc_runtime_documents_v1`；上传后的聊天也只查询该runtime collection，不把冻结评测库拼接成伪全链。
- 聊天请求只接受`document_id`和`query`。服务端按固定`demo` workspace读取`DocumentRecord`、检查`ready`，再从记录恢复`TrustedContext`并构造`document_id`过滤。
- `source_file`是可重复、可重命名的展示元数据，不作为稳定文档身份；浏览器不得提交workspace、source_file或任意Milvus过滤表达式。

### SSE与终态边界

- 事件名冻结为`status/final_answer/citation/usage/error/done`；SSE只做传输和领域终态映射，不复制检索、Prompt、拒答或引用校验逻辑。
- 请求在开始流响应前失败时使用HTTP状态：不存在文档为404，未ready为409，聊天依赖未启用为503。开始流后只发送SSE领域终态。
- 成功顺序为`status → final_answer → citation* → done(success)`；`final_answer`只来自已经通过引用校验的`RAGResult`，引用字段只来自服务端验证后的`number/source_file/page/chunk_id`。
- `RefusalResult`是正常业务终态，只发送拒答状态和`done(refusal)`，不发送答案、引用或error。`SystemErrorResult`只发送安全code/message和`done(error)`，不得泄露`raw_error`。
- 当前LLMClient没有真实token usage，因此只保留`usage`合同，不发送固定0或伪造数字。模型原始token不逐字直通，也不能作为可信答案提前展示。
- 客户端只在收到唯一且匹配的`done`后提交答案或拒答。正常EOF缺少done、残余不完整帧、未知事件、done后额外事件或`reader.read()`抛错都进入前端安全错误状态，已经暂存的候选答案必须丢弃。

### 阻塞、断开与运行时生命周期

- `RAGService.answer`保持同步；`ChatService`通过`asyncio.to_thread`离开event loop。health可继续响应，但客户端断开不代表已经进入worker线程的同步工作被取消，本阶段不增加取消基础设施。
- 浏览器使用`fetch`发送POST JSON并读取`ReadableStream`；原生`EventSource`只适合GET且不能直接提交本次JSON请求。网络chunk不等于SSE帧，前端必须保留残余buffer直到遇到结尾双换行。
- runtime应用不得使用`uvicorn --reload`，因为重载会丢失内存dispatcher任务。SQLite和对象内容可持久化，但`queued/parsing/indexing`任务不会自动恢复；真实调试留下两条`indexing`记录，未伪装为ready。
- 本机真实集成中，Milvus Lite/gRPC与BGE首次初始化曾出现进程退出码139和fork/keepalive提示。runtime在创建任何Milvus/gRPC客户端前先完成一次不入库的BGE预热；已有collection在应用重启后显式`load_collection`再提供搜索。一次完整启动曾瞬时退出139，受控重试后成功完成已有ready文档的正常拒答，因此不能宣称该环境问题已被稳定消除。

### 真实证据与延期范围

- 真实文本层PDF已完成`上传 → parsing → indexing → ready → 真实BGE → runtime Milvus → 真实LLM/RAG → SSE → 浏览器答案 → 3条可验证引用 → done`。同一ready文档的范围外问题已完成`RefusalResult → done(refusal)`浏览器验证。
- 自动质量门为后端`263 passed`、5条底层SWIG弃用警告、Ruff通过、mypy检查34个源码文件通过；前端6个SSE测试、TypeScript/Vite build和oxlint通过。真实smoke与自动测试证据分开记录，不把单次演示描述为公开benchmark或生产稳定性。
- P1/P2明确延期：CSS美化、多页面/Router、复杂状态库或组件库、Markdown/HTML富文本、PDF预览、对话持久化、Prompt A/B、token逐字直通、后台任务恢复、Redis、S3、PostgreSQL、可靠队列、登录、多用户权限与生产部署。

## Agent 单文档任务合同（装配前约定）

本节定义待实现的本地 Agent 任务边界，不表示 runtime、用户结果校验、结果持久化或 HTTP 入口已经接通。现有 RAG 入口和离线 Agent 评测保持原行为。

### 1. 用户输入与服务端范围

- 用户输入草案仅为 `document_id: str` 与 `query: str`，均须非空；用户提交的是待验证的文档编号及任务文字，不直接提交 messages、workspace、role、任意过滤器、授权结论或执行预算。额外的控制字段应拒绝，不能成为可信上下文。
- 服务端按配置的固定 `demo` workspace 查询文档记录，核实归属与 `ready` 状态，再从记录恢复 workspace 和本次唯一 document 过滤。不存在或不属于该 workspace 的文档统一视为不可用，未 ready 的文档不能进入执行；这些是前置请求失败，不伪装为“文档中没有答案”的业务拒答。
- 本次任务只允许查证已核准的单份文档。任务文字、检索内容或模型都不能扩大范围；改查另一份文档必须重新提交并通过服务端校验。固定 demo 资源绑定不等于已认证的多用户授权。
- 可复用路径见 [ChatService.prepare](../app/chat/service.py) 和 [DocumentService.get_document](../app/documents/service.py)。[ToolExecutionContext](../app/agent/tool_loop.py)仅携带范围并检查外层类型，本身不执行认证、归属查询或 ready 检查。

### 2. 真实工具与模型决策

- 首次真实装配只开放 `search_finance_docs`，绑定现有真实 Retriever 和已核准范围；模型可决定检索词及 `top_k`（1—5），程序负责工具白名单、严格 schema、范围和执行校验。模型可见参数保持现有 `query/top_k`，不增加 workspace、role、document 过滤或授权字段。
- `calculate_financial_metric` 保留已有实现与评测用途，但不进入此次真实装配的工具清单。上传 PDF 的检索文字尚未接通可信数值、期间、单位及来源确认链；不能让模型填写的数字或 [eval_fixtures](../app/agent/eval_fixtures.py) 的预置事实代替真实文档事实。
- 现有 [build_finance_tool_registry](../app/agent/finance_tools.py) 同时注册两个工具，不能将其原样当作此次真实装配的最终工具清单。真实装配不导入评测依赖；本节不修改旧 factory、不新建 loop、不新增第三个业务工具。
- 明确要求财务计算的请求属于当前能力范围外，应给出能力限制的拒答，不把模型心算包装成已验证的计算工具结果。即使来源文字可读，也不提前宣称计算链可用。

### 3. 用户结果与各层成功

| 用户输出草案 | 发布条件与字段边界 |
|---|---|
| `answered`：答案及引用 | 候选输出通过结构与证据检查；引用非空且映射到本次核准文档的实际证据，页码和来源由程序恢复。引用合法仍不自动证明语义正确 |
| `refusal`：明确原因及安全说明 | 正常完成必要检查后证据不足，或明确超出当前能力范围。空检索只支持“本次证据不足”，不能宣称整份文档或外部世界一定没有答案 |
| `system_error`：稳定错误码及安全说明 | 工具、模型供应商、协议、结果校验或步骤耗尽等失败，不能包装成资料不足；不发布未经验证的候选答案或原始异常 |

- 调用申请、工具执行和运行终态分别判断；参数合法不能证明工具已执行，工具成功也不能证明最终回答可信。现有 [LoopSuccess](../app/agent/tool_loop.py) 不是用户 `answered`，必须经过后续结果校验；正式拒答也不伪造为 ToolError。
- 现有 [Run/Event](../app/agent/run_models.py) 和 [RunService](../app/agent/run_service.py) 只保存既有粗状态、协议终态和安全摘要；`final_answer_available` 不是可刷新用户答案。本节不新增结果模型、写入事务或 API，具体结果与引用验证、结果持久化分别后续实现。
- 原12题三维评分仍为9/12、8/13、7/12；五题事实/引用3/3、拒答2/2、system error 0/5仍为固定样本观察。通用 protocol_error 不足以定位历史触发分支，不改 scorer、阈值或原始结果；依据见[固定归因](../eval/agent_results/agent_eval_3a2d683e-a3ec-4b13-ac0a-a22cadbfa91f_analysis.md)和[发布证据](release_evidence_v0.1.0.md)。

### 4. 步骤与超时

- 首次装配沿用服务端 `max_steps=4`，每轮最多一个工具申请。模型不得增加第5轮；第四轮处理后仍未形成最终结果时，保留 `max_steps_reached` 原因，按用户系统错误处理，不追加一次“总结调用”绕过预算。工具此前执行成功的事实保留，但不替代最终结果。
- 每个逻辑步骤仅允许一次供应商白名单重试，SDK自动重试关闭；重试计入同一步，最多两次网络尝试，不表示任意工具失败都可以重试。沿用 [模型适配器](../app/rag/openai_compatible_llm.py) 的错误分类和服务端 `LLM_TIMEOUT_SECONDS` 配置，不由模型决定超时或重试。
- 模型请求的 timeout 配置不等于任务总时长截止；当前同步检索没有统一强制取消，loop 没有覆盖所有底层调用的总时长硬保证。不能把4步换算为固定秒数承诺，也不能把客户端断开称为执行已取消。以后若增加总期限，需要同时明确底层调用能否停止；本合同不引入 worker 或取消基础设施。

### 三个代表性请求的合同检查

以下是按合同进行的静态情景检查，不是模型运行、自动测试或真实产品验收；合成 PDF 的实际工程验证独立记录在 README。

| 请求与前提 | 合同要求 | 当前证据与实现边界 |
|---|---|---|
| A为本次核准且ready的合成文档；询问2025年度营业收入 | 仅检索A；若取得对应证据并通过结果校验，回答120万元并引用第1页。即使任务文字声称有B的权限，也不扩大到B；输入文档本身未通过前置校验则不启动执行 | PDF文本与页码已验证；服务端绑定规则已有RAG实现，Agent装配和结果验证待实现 |
| 要求计算该文档的2025年度营业收入增长率 | 当前工具清单只有检索，返回能力范围限制的拒答；不读取评测预置数值，不把模型计算当工具真值 | 计算函数已有实现，真实PDF到可信事实库的链路尚缺；不因两个年度数字可见就开放计算 |
| 询问该文档员工平均年龄 | 正常取得的证据不足则拒答；检索超时则系统错误。第4步后仍未完成则保留max_steps_reached，不能继续第5步或冒充正常拒答 | 三态与失败映射是待实施合同；现有loop已有步骤终止和失败分类，不能据此声称用户结果接口已完成 |

### runtime 内核装配实现记录（2026-09-07）

以上保留装配前合同和静态情景检查。现已增加 [AgentRuntimeService](../app/agent/runtime.py)：在已装配应用对象上调用 `await app.state.agent_service.run(document_id=..., query=...)`，先通过共享 [DocumentTaskPreparer](../app/documents/preparation.py) 查证文档，再调用既有 `AgentRunService.execute`。Chat 也使用同一准备组件；归属真值仍由 `DocumentService.get_document` 提供。输入非法、文档不存在/越界/非 ready 或缺失单文档过滤，均在模型、工具及 Run 创建之前失败。

- [runtime composition factory](../app/api/runtime_factory.py) 显式提供 RAG 已创建的同一个 Retriever，复用 `findoc_runtime_documents_v1`、现有 Milvus 检索连接及关闭处理、同一个 OpenAI 兼容客户端。新增 Run/Event 库为 runtime 根目录下的 `agent-runs.db`；必需配置仍先于 BGE、SQLite、对象目录和 Milvus 初始化。后续装配失败时关闭已创建的检索连接。[默认 ASGI 入口](../app/api/main.py)保留既有启动命令。
- `build_search_finance_tool_registry` 每次构造仅含搜索工具的独立表，复用既有 schema/handler；旧双工具 factory 复用该构造后再加入计算，保留离线行为。模型只能填写 `query/top_k`，核准范围从服务端准备结果进入 `ToolExecutionContext`，不从任务或资料文字恢复。runtime 不读取评测 fixture 或计算事实库。
- 服务端固定 `max_steps=4`，不增加总结轮；每步供应商重试和请求 timeout 沿用原合同。内部入口的文档准备是异步，后续 loop 和 Run 持久化同步占用调用线程；尚未接 HTTP 线程适配、后台执行或强制取消。
- 返回值仍为 `RecordedRunOutcome`，持久化内容仍是既有 Run/Event 安全摘要。loop success 和候选文本不等于已验证用户答案；计算能力限制的用户拒答映射、用户三态/引用验证、用户结果与终态同事务持久化、HTTP/UI 均待后续实现。

定向验证：`test_agent_runtime`、`test_runtime_startup`、`test_agent_run_service`、`test_finance_tools`、`test_document_preparation`、`test_chat_service`、`test_chat_api`、`test_sse` 共 **68 passed**，另有 5 条 SWIG 弃用警告；改动相关 Ruff、5 个相关源码文件 mypy 与 diff 检查通过。正式装配测试使用假模型/embedding/Milvus/文档存储、真实 Retriever/工具/loop/文档服务和临时 SQLite，覆盖资源复用、范围前置失败、单工具 schema、越权参数、步骤/重试边界及旧聊天回归。这些是接线和边界证据；未运行真实 Agent 依赖 smoke、付费模型、历史评测或向量重建，历史评分及原始资产保持不变。

### 内存用户结果与引用验证（2026-09-09）

本节收窄当前支持请求并记录结果验证实现；上文保留原合同与装配时点的事实。

- 输入仍只有 `document_id/query`。文档归属、ready 及单文档范围先于 Run；准备组件另保留记录中的文件名供交叉检查。当前仅完整匹配 `查询[0-9]{4}年度(营业收入|净利润|员工平均年龄)`，只忽略首尾空白，不忽略附加命令。支持某指标不证明文档含有该事实。其他表达均视为当前任务合同外，不宣称识别了任意自然语言意图，也不把所有未匹配请求称为计算请求。
- 候选沿用 RAG 的唯一 JSON 形状：`{"decision":"answer","content":"正文[n]"}` 或 `{"decision":"refuse"}`。新公开纯函数 `parse_answer_candidate` 复用原解析并额外拒绝重复字段；旧 RAG 解析和拒答路径保留。模型不能提交引用元数据、正式原因或额外字段。方括号在 Agent 候选正文中专用于无前导零的正整数引用。
- 每个 runtime 调用新建 `SearchEvidenceSession`，包装既有唯一搜索 handler。命中范围身份来自 store 实体：runtime 的 Milvus adapter 显式请求 `workspace_id/document_id`，Retriever 与工具保留实际返回值；旧 adapter 默认字段集合及旧离线命中缺省行为兼容。Agent 严格检查字段类型、计数、empty、核准 workspace/document/file；身份缺失时失败，不从过滤条件、文件名或模型内容补造文档身份。
- 每次搜索成功验证后向工具结果加入 `evidence_number`，编号按本次首次出现顺序递增。同一 chunk 重复出现复用编号，允许相关分数变化；正文、页码、来源或其他事实字段冲突时失败。整个返回验证通过才签发；本次结果快照与 loop 的 `trusted_tool_results` 按序核对，防止普通 messages、伪造结果或可变字典覆盖成为证据。之后构建 `NumberedContext` 并复用 `validate_and_build_citations`，引用非空、编号有效且来源属于本次核准证据才发布正文。
- 产品 `answered` 仅公开 `status/content/citations`；引用仅含 `number/source_file/page/chunk_id`。`refusal` 仅公开 `status/reason/message`；`system_error` 仅公开 `status/error_code/message`。说明由服务端生成，三态均不公开原始 messages、检索全文、内部指令、原始异常或校验失败的候选正文。对外字段由 `user_result.to_public()` 显式生成，不序列化整个运行对象。
- 证据不足拒答仅接受正常 loop 的 `refuse` 候选，且至少一次可信搜索、全部有效且为空。非空证据下仅有模型拒答声明返回 `unverified_refusal` 系统错误；这是可用性的保守限制，不表示非空结果必然足够。任务合同外的 `refuse` 候选可据服务端完整匹配结果形成 `capability_limit`；不执行搜索。此路径仍经过既有 loop，模型违约输出、强行调用工具或执行失败仍返回系统错误，不能用能力拒答覆盖失败。
- `AgentRuntimeService.run` 返回 `ValidatedRunOutcome`，继承原 `RecordedRunOutcome`，保留 `.run/.outcome` 并增加 `.user_result`。Run/Event 仍只记录 loop 终态和安全摘要，因此 loop 的 `success` 可能对应产品 `system_error`。用户结果只存在于本次调用内存中，不能刷新恢复；没有结果表、数据库迁移、用户结果终态事务或 HTTP/UI。既有 Run 存储异常仍按原接口传播，不伪造已经保存的用户结果。
- 保留单工具、四轮上限及配置 fail-fast；配置版本为 `runtime-search-result-v1`。不运行第二条 RAG 或模型生成链、不补检索、不注册计算。来源与编号校验不证明自然语言结论得到原文支持，语义质量仍需独立评测与人工核对。

验证命令：`uv run --frozen pytest tests/test_agent_user_result.py tests/test_agent_runtime.py tests/test_agent_run_service.py tests/test_finance_tools.py tests/test_document_preparation.py tests/test_evidence_gate.py tests/test_day45_rag_service.py tests/test_day46_rag_service.py tests/test_day41_retriever.py tests/test_chat_service.py tests/test_chat_api.py tests/test_sse.py tests/test_runtime_startup.py -q`：**183 passed、5 条 SWIG 弃用警告**。相关 Ruff、9 个源码文件 mypy 和 diff 检查通过。新用例覆盖非法/跨范围引用、同名跨文档身份、字段与来源冲突、全空/混合搜索、伪造证据、跨 Run 编号隔离、四类 loop 失败及白名单；正式装配替换重依赖、使用临时 SQLite。仅证明代码合同与装配边界，未执行付费模型、真实 Agent smoke、历史评测或向量库重建。

### 用户结果原子持久化（2026-09-09）

- runtime 将本次 `SearchEvidenceSession.validate` 注入 `AgentRunService.execute`；唯一 loop 完成后先验证，再调用仓储终结。模型、检索和验证均不持有 SQLite 终结写锁；没有第二条生成或检索链。`ValidatedRunOutcome` 移至 Run 服务定义，runtime 继续可引用该类型；整个对象仍含内部证据，不可直接公开。
- Run 非破坏性增加可空的 `document_id/user_result_version`。新产品 Run 在创建时写入服务端核准文档和 `agent-user-result-v1`，执行配置更新为 `runtime-search-result-v2`。`agent_user_results` 以 run_id 为主键，一次 Run 最多一份受限结果；workspace、文档和配置身份通过 Run 关联，结果 JSON 不接受模型自报身份。
- [result_storage.py](../app/agent/result_storage.py) 显式编码三态：answered 保存状态、已验证正文和 `number/source_file/page/chunk_id` 引用；refusal 仅状态和稳定原因；system_error 仅状态和稳定错误码。固定提示文案读取后生成，不保存原始候选、messages、prompt、工具全文、隐藏推理或原始异常；拒答/错误无正文及引用。反序列化拒绝未知版本、重复/额外键、非法类型、三态混合及正文/引用编号不一致，不把结构验证当作重新核证语义。
- `finalize_run` 同一 SQLite 连接和事务写结果、唯一结束事件、Run 状态/执行终态/结束时间/安全摘要。任意写入或序列化失败传播并回滚本次终结；原 running 与此前已提交工具事件可保留。重复终结一律状态冲突，不覆盖、不新增第二份结果，不提供隐式幂等成功或自动重跑。
- Run `status/terminal_status` 与 Event 类型保持执行层合同；`user_result_status` 明确记录产品层。LoopSuccess 可对应 answered、refusal 或产品验证 system_error；LoopFailure 必须对应同类安全系统错误。新产品摘要不使用旧 `final_answer_available` 旗标，旧离线路径保持原摘要和终态映射。
- `AgentRunService.get_user_result(workspace_id, run_id)` 委托仓储，在一个读快照中先查可信归属，再核验结果版本/结构、Run 与唯一结束事件的一致性。错误 workspace 和不存在均为相同 `AgentRunNotFoundError`；running 为 `AgentResultNotReadyError`，旧版/离线无产品合同为 `AgentResultNotStoredError`，新版本缺结果或记录损坏为安全的 `AgentResultIntegrityError`。返回元信息与 `user_result`，仅后者的 `to_public()` 是公开白名单；固定 demo 归属不等于认证。
- 迁移只增加两列与一表，不删除/重建 runtime 库、不修改历史终态、不回填答案。旧代码可以忽略新增字段，但不能识别新产品合同，禁止以旧写路径终结带结果版本的新 Run；代码回退不能视为支持新结果的读取/写入，应用应停写并保留扩展结构及记录，恢复兼容版本后处理。不实现自动降级迁移或历史回填平台。

定向验证：`uv run --frozen pytest tests/test_agent_run_repository.py tests/test_agent_run_service.py tests/test_agent_runtime.py tests/test_agent_user_result.py tests/test_runtime_startup.py tests/test_finance_tools.py -q`：**129 passed、5 条 SWIG 弃用警告**；相关 Ruff、5 个源码文件 mypy（`--follow-imports=silent`）通过。覆盖文件 SQLite 重开三态、读取零模型/检索、可信范围、真实触发器阻止三处写入、结果插入后的事件序列化失败、重复终结/序号、原两表结构扩展、损坏/非法载荷、禁止字段不落盘、验证时序与无写锁，以及前置失败零 Run 等回归。证据使用 fake 模型和重依赖替身，未触碰用户 runtime 库、调用付费模型、执行真实 Agent smoke、历史评测或向量重建；不代表全量测试、真实模型质量、HTTP/UI 或后台恢复已完成。

### Agent 同步创建与安全历史查询（2026-09-10）

[Agent HTTP 适配](../app/api/agent.py)通过 `create_app` 注入可选 runtime 与服务端固定 workspace；正式装配复用现有 Agent、Retriever、模型客户端和仓储。未启用 Agent 的应用仍可使用旧文档/聊天入口，Agent 端点返回安全 503；启用却缺少非空查询 workspace 则构造失败。固定 demo 仅证明资源绑定，不提供登录、多用户授权或公网生产保证。

| 接口 | 完成条件与公开响应 |
|---|---|
| `POST /agent/runs` | 仅接受严格非空字符串 `document_id/query`，额外 JSON 字段拒绝。文档准备、执行、结果验证与终态提交完成后返回 201；`run_id/document_id/user_result` 为唯一顶层白名单 |
| `GET /agent/runs/{run_id}` | 按服务器 workspace 委托 `AgentRunService.get_user_result`；200 返回与 POST 相同的身份/产品结果 DTO，不重新执行或修复性生成 |
| `GET /agent/runs/{run_id}/events` | 按同一可信范围委托 `list_events`；200 返回 `run_id/projection="history"/events`，按 sequence 排序 |

- POST 的 201 表示 Run 已创建且本次结果已提交，不代表产品 answered。`user_result.status` 可为 answered、refusal、system_error；均只从已校验结果的 `to_public()` 构造严格响应 DTO，不序列化内部 outcome 或任意数据库字段。拒答使用既有 `empty_retrieval/capability_limit` 原因，不新增业务类别。HTTP 输入结构合法但超出有限查询句式时，沿用现有能力限制流程；模型违约仍可能形成产品系统错误，不一律改成 422 或强制拒答。
- GET 的 workspace 只取服务端构造参数，不使用客户端 body/query/header 中的同名或类似字段。不存在与范围外的 Run（包括 Events）采用完全相同的 404 与 `agent_run_not_found`；文档不存在/越界统一 `document_not_found`，未 ready 为 `document_not_ready`，均在模型、检索和 Run 创建前失败。
- 错误响应统一为 `{"detail":{"code":"稳定错误码","message":"固定安全说明"}}`。请求结构非法为 422 `invalid_agent_request`；未 ready 文档为 409。结果未提交为 409 `agent_result_not_ready`，旧版/离线未存产品结果为 409 `agent_result_not_stored`，新版结果缺失/损坏/版本不支持为 500 `agent_result_integrity_error`。旧记录不能提示成等待即可恢复，running 也不承诺自动继续。
- SQLite 读写失败为 500 `agent_storage_error`，未知异常为 500 `agent_internal_error`，缺失 Agent 依赖为 503 `agent_unavailable`。不回显参数校验输入、异常正文、SQL、绝对路径或原始模型内容；数据库提交失败不得返回内存产品结果并声称已保存。安全错误外壳仅作用于 Agent 端点，不修改旧聊天/SSE 的错误合同。
- 每条公开 Event 只含 `sequence/execution_event_type/summary`，摘要按有限事件类型由服务器生成，不直通任何 payload；`run_succeeded` 摘要明确表示执行循环结束，产品结果以结果接口为准。历史投影不作为实时进度、精确工具耗时或副作用回放入口。
- `AgentRuntimeService.run` 保留异步文档准备，随后 `await asyncio.to_thread(self._run_prepared, prepared)`，将每次独立证据会话、同步 loop、验证与持久化整体移出事件循环。GET 同步 SQLite 读取也通过 `to_thread` 调度；仓储在每次操作中自行打开/关闭连接，不跨线程复用活跃连接。POST 仍等待工作完成，不返回 202，不承诺线程强制取消、任务总超时或重启续跑；客户端断开后线程可能继续工作，但没有耐久保证。
- 重复终结冲突不等于 POST 请求幂等。相同 POST 重发可能创建新 Run 并再次执行，客户端不得隐式自动重试并宣称不会重复。保留单文档、仅搜索、四轮、配置 fail-fast、有限查询与引用校验、原子提交及旧数据读取边界；不增加模型链、计算装配、worker 或 Agent SSE。

定向验证：`uv run --frozen pytest tests/test_agent_api.py tests/test_agent_runtime.py tests/test_agent_run_service.py tests/test_event_loop_boundary.py tests/test_chat_api.py tests/test_runtime_startup.py -q`：**98 passed、5 条 SWIG 弃用警告**；相关 Ruff、6 个相关源码文件 mypy（`--follow-imports=silent`）及 diff 检查通过。新增 HTTP 集成复用受控正式装配，保留真实文档准备、Retriever/工具/loop、结果验证及临时文件 SQLite，覆盖三态重开读回、前置零执行、范围、损坏/旧结果、真实提交/读库故障、零重跑、Events 白名单、重复 POST 和可选依赖。模型调用、提交及两类 GET 读取使用独立观察线程与受控屏障，验证在放行前 health 已响应且原请求未返回；原有直接阻塞/线程调度正反对照保留。未知异常外壳另有纯 stub 补充测试，不能替代接口集成。未调用真实模型、触碰用户 runtime 库、重跑历史评测或修改 UI；这些证据不证明真实模型质量、真实重依赖并发兼容性或完整产品验收。

### Runtime 隔离启动与浏览器集成观察（2026-09-14）

- 真实 composition 已移至无模块级装配的 [runtime_factory.py](../app/api/runtime_factory.py)。仅导入该模块不会读取 LLM 配置、预热 BGE、创建 SQLite／对象目录或打开 Milvus；显式隔离 Uvicorn factory 只接受必填绝对 `FINDOC_RUNTIME_ROOT`，并拒绝项目默认 runtime。`app.api.main:app` 仍在兼容入口中按默认目录装配，原启动命令和“配置校验→BGE 预热→存储／Milvus”顺序不变。
- [受控浏览器装配](../tests/support/controlled_agent_app.py)明确使用 fake embedding、检索 store 与 provider，但保留真实文档准备、Retriever、搜索工具、loop、用户结果验证、FastAPI 和文件 SQLite。营业收入、员工平均年龄、净利润三个任务分别形成 answered、`empty_retrieval` refusal 和已提交 `provider_error` system_error；三态在重建应用后均由同一 Run GET 读回。受控 Events SQLite 故障只使历史区失败，不撤下 answered；关闭后端后的提交显示请求级错误，不冒充产品 system_error。
- 浏览器受控 answered 为“2025年度营业收入为120万元。[1]”，引用受控资料第1页。刷新前后该 Run 只有一次 POST，刷新使用结果 GET 与 Events GET；这仍是跨层装配证据，不证明真实 embedding、Milvus 或模型质量。
- 隔离真实观察使用新生成的 `synthetic_finance_smoke_20260914.pdf`。文件经实际解析和两页渲染核对，第1页含2025年度营业收入120万元与2024年度100万元，第2页含员工12人且明确无年龄信息。浏览器上传经真实 parser、BGE 和 Milvus 到达 ready，文档 ID 为 `b7d280a9785cfbc2917fda87e4db5281e8462cc4247e22c518bf37cc50ac0e99`。
- 经当次授权只提交一次“查询2025年度营业收入”。配置的 `deepseek-v4-flash` 在第一个 provider attempt 返回 HTTP 401 鉴权失败；不可重试映射使实际网络尝试数为1。HTTP 201 只表示 Run 已提交；Run `fe168f2a-fcdd-4885-b60e-3d1258467082` 在独立 `agent-runs.db` 中保存执行终态 `provider_error`、产品 `system_error` 和唯一 `run_failed` Event，刷新 GET 原样读回且没有第二次 POST。未修复密钥或重跑。
- 因模型在调用搜索工具前失败，本次没有真实 answered、工具检索、事实核对或引用闭环证据，不能据 ready、HTTP 201 或受控三态宣称真实 Agent 路径已通过。关闭真实 runtime 时另观察到 Milvus Lite gRPC `too_many_pings` GOAWAY 日志，但此前上传、持久读取和有序关闭均完成；本次不扩展为基础设施排错。

凭据由用户在本地更新后，进行了另一次独立授权的有限续办；它创建新 Run，不修改或续跑上述401失败记录。

- 启动进程继续通过 `--env-file .env` 和必填绝对 `FINDOC_RUNTIME_ROOT` 使用同一隔离目录、ready 文档与 `deepseek-v4-flash`；没有重新生成、上传或摄取文档。调用前只核对配置来源、必填项存在性及安全的模型／主机／timeout，未打印密钥、执行连通探测或更换 provider。
- 浏览器只新增一次 POST“查询2025年度营业收入”。新 Run `aeb5ede6-77fe-4d89-b264-6ab88922fea0` 为执行 `success` 和产品 `answered`，保存正文“2025年度营业收入：120万元。[2]”及引用 `synthetic_finance_smoke_20260914.pdf` 第1页、chunk `5b2ed13fdb7e231496d11cf46d5d08fe2ec65d37bd32937b83dffc9719b800d1`；Events 按序为 `tool_requested/tool_succeeded/run_succeeded`。旧 Run `fe168f2a-fcdd-4885-b60e-3d1258467082` 仍为 `provider_error/system_error` 和唯一 `run_failed`，未被覆盖。
- 浏览器刷新后只观察到文档 GET、同一新 Run 的结果 GET 与 Events GET，没有第二次 POST；页面从保存记录恢复相同文档、正文和引用。当前适配器不保存完整 provider usage，成功 attempt 数未单独记录，因此不据 Events 编造精确计费次数。
- 服务关闭后的首次 Milvus 直接 query 因 collection 处于 `released` 而失败；按真实启动边界显式 `load_collection` 后，只读查询上述唯一 chunk 成功。索引记录的 workspace、document、source_file、page 均与本次 Run 一致，正文明确包含“2025年度营业收入：120万元”和“金额单位：万元”，因此引用不仅结构存在，也真实支持答案的事实、期间和单位。
- 本续办补齐了一个受限合成任务的真实上传→模型工具调用→检索→结果验证／持久化→浏览器展示→刷新 GET 闭环。它不证明其他问题或文档的泛化质量，也不提供生产级身份、多租户、后台耐久、费用 quota、发布 Gate 或最终部署能力。Milvus Lite 关闭时仍可观察到既有 `too_many_pings` GOAWAY 日志，本次闭环未受影响，未扩展基础设施范围。

本次定向验证：后端／API／受控装配／PDF组合 **97 passed、5 条 SWIG 弃用警告**；Node 24 前端 **42 passed**，oxlint、TypeScript/Vite build、相关 Ruff、2个 composition 源文件 mypy 与 `git diff --check` 通过。隔离改造首轮曾有 **34 passed、1 failed**：旧测试仍在兼容 `main` 模块替换已迁移的仓储符号；改为在真实 factory 所有者处替换后通过。上述结果不是全量测试，也不与历史98项相加。

## G1 同文档两期营业收入 Workflow 合同（2026-09-19）

### 范围与真值

- 输入范围由程序固定为服务端已核准的单一 `workspace_id/document_id`、营业收入和 2024/2025 两个期间。模型或文档文字不能改写这些范围。
- `RevenueCandidate` 是待核对的解释，不是计算真值。它保留范围、唯一候选引用、chunk、文件、页码、期间、`Decimal` 数值和可能尚未知的规范化单位。`source_ref` 标识单条候选事实，不等同于 `chunk_id`；同一 chunk 可同时支持两个期间。
- 只有操作者对当前完整候选发出明确确认动作，程序再次核对阶段后，才会创建现有 `FinancialFact`。调用方不能把候选原地改成已确认事实。
- 增长率真值只由现有 `CalculateFinancialMetricTool` 读取两条已确认事实后生成。模型不能提交裸数值、选择公式、覆盖结果或自报来源。

### 状态、步骤与合法转移

| 阶段 | 步骤输入 | 程序写入 | 唯一合法后继 |
|---|---|---|---|
| `collecting_candidates` | 已核准范围内的结构化候选 | 候选快照，或稳定失败码 | `awaiting_confirmation` 或 `failed` |
| `awaiting_confirmation` | 操作者对当前候选的明确确认 | 两条新建的 `FinancialFact` | `ready_for_calculation` |
| `ready_for_calculation` | 已确认事实 | 公式结果与两条来源，或计算拒绝码 | `completed` 或 `failed` |
| `completed` / `failed` | 无 | 无 | 终态，不允许继续转移 |

所有转移由项目函数返回新的不可变 `RevenueWorkflowState`。跳过确认、对终态继续执行或从错误阶段调用步骤属于程序员误用，抛出 `RevenueWorkflowTransitionError` 并不产生新状态。

### 固定程序规则与模型可选动作

- 程序固定：范围核对、期间齐全、候选冲突、单位兼容、确认准入、状态转移、公式、舍入、零分母、终态和步数上限。
- 模型可选：在后续真实事实链中可用于提出“哪段证据可能是营业收入”的候选，或把已确定结果组织成文本；不得确认事实、选冲突值、决定准入或代替程序计算。
- 本次纯 Python 变体不调用模型，因此不存在迭代调度。将来若编排器调用模型，超出固定步数必须进入 `step_limit` 失败终态，不能自行循环。

### 失败和拒绝出口

- 任一目标期间没有候选：`missing_candidate`。
- 当前最小变体中，任一期间出现多条候选：`candidate_conflict`，不让模型自动选择。相同值的多条证据如何合并留给 G2a 细化。
- 候选越出服务端核准的工作区或文档：`scope_mismatch`。
- 候选数量检查通过后，任一期单位不明：`unit_unknown`，不得确认或计算。两期规范化单位均已知但不一致：`unit_conflict`。
- 计算器拒绝期间顺序或零分母时，Workflow 保留现有 `FinancialMetricErrorCode` 值并进入 `failed`。

成功终态保留 `20.00 / PERCENT / revenue_growth_rate_v1` 等程序结果，以及两条已确认事实的 `source_ref/chunk_id/source_file/page`。它只证明状态与准入合同，不证明真实文档抽取、持久确认、模型质量或生产 runtime 已接通。

## 单文档营业收入候选抽取合同（2026-10-04）

### 入口、结构与能力边界

- `RevenueCandidateService.collect(document_id=...)` 复用 `DocumentTaskPreparer` 查证归属及 ready，再以固定两期营业收入问题调用真实 `Retriever`。输出为候选状态、原始命中和排除的非目标期间；不进入确认或计算步骤。这个本地服务尚未装配进 Agent 工具或新增 HTTP/UI 入口。
- 复用 `RevenueCandidate` 和 `RevenueWorkflowState`；指标固定为营业收入，期间固定为 2024/2025。候选的等待确认/失败由 Workflow 状态表达，候选对象本身始终未确认。`FinancialFact` 只校验可信数值记录结构，不能把创建对象当作操作者确认的证据。
- 最小新增 `RevenueEvidence` 保存实际命中全文、`chunk_id/source_file/page`、Python 字符位置 `start/end`、原始数字和单位；候选保存全部 evidence 及 `revenue_line_rule/v1` 抽取方法/版本。原有单处来源字段只展示 evidence 的第一处，不能当作合并候选的全部来源。空 evidence 仅兼容既有纯 Python 变体；真实抽取入口始终附证据。既有内存确认变体透传 evidence，不实现持久确认。
- 实际合成 PDF 的每条收入都是“YYYY年度营业收入：数字单位。”独立段落行，故采用整行有限规则。只支持这种年份/年度/指标写法及普通小数、合法千分位；不支持表格列对齐、科学计数法、跨片段单位推断或通用财报抽取。不支持的格式形成缺失候选，不静默截取数字前缀。
- 对当前固定完整年度收入例，先做规则抽取可避免手工重复录入。主要备选是操作者对真实命中选原文位置并标注期间/金额/单位；必须仍绑定检索证据，不允许输入脱离证据的裸数值。当前输入无需增加 LLM 抽取依赖。规则不自动判断母公司/合并口径、修订口径或文本真假，操作者仍需核对。

### 来源、单位与重复规则

- 身份必须来自 store 实体经 `MilvusSearchStore(include_scope_metadata=True)` 和 `Retriever` 实际传递；核准记录/过滤条件只用于比对，不用于补造命中身份。整个批次先核对 workspace/document/source_file；缺身份、非法来源字段或同 chunk 内容变化为 `source_invalid`，归属不符为 `scope_mismatch`。任一来源异常整体阻断，不保留部分候选冒充成功。
- 只从原文数字字符串构造 `Decimal`，去掉已通过规则验证的千分位逗号；明确“元/万元/亿元”分别乘以 1/10000/100000000，规范单位统一为 `CNY_YUAN`。局部 Decimal 精度随有效数字长度扩大，避免换算截断。原始文字/数字/单位不覆盖；单位缺失或不支持则保留原数且 `unit=None`，不从文档其他位置默认填入。
- 同来源同一处文字重复返回只保留一处证据，忽略 score 差异。已知单位的候选按期间、规范金额、单位合并，保留不同位置的全部证据；未知单位只能去除完全相同的证据，不能按裸数字合并。
- `source_ref` 由实际范围、固定指标、期间和排序后的 chunk/原文位置生成摘要。同 chunk 两个期间产生不同引用；排序只稳定展示，不依 score 选择真值。引用是候选标识，不能作为已确认标识或来源版本失效机制。
- 合并后交给既有 `record_revenue_candidates`：目标期间缺失为 `missing_candidate`；同时出现非目标期间且目标不足为 `period_mismatch`，保留 `excluded_periods`，不改写年份。两期齐全后，任一单位未知为 `unit_unknown`；同一期仍有多个已知金额为 `candidate_conflict`。这些失败不能确认或计算；完整唯一候选只到 `awaiting_confirmation`。

### 验证与限制

- `scripts/verify_revenue_candidates.py` 在全新数据目录中，经真实文档 ASGI 上传 API、真实 parser/BGE/Milvus、真实 Retriever，再调用候选服务；报告见 `artifacts/revenue-candidates/actual-candidates.json`。这是进程内 HTTP/业务链证据，不包含浏览器或 TCP 部署验收。
- 使用显式合成 PDF，文件及原始评测保留；复用现有 Linux ARM64 镜像和只读模型缓存，以离线、无网络容器执行，未挂载原业务数据卷。实际第 1 页命中同时支持 2024 的“100万元”和 2025 的“120万元”，规范值分别为 1000000/1200000 元，引用不同，来源身份/原文位置完整；确认事实为空、计算结果为 null。
- 定向与受影响回归共 123 passed（5 条既有 SWIG 弃用警告）；Ruff 和 3 个源码文件 mypy 通过。`tests/test_revenue_extraction.py` 明确标注手写 SearchHit、fake embedding/store，覆盖重复/多来源合并/冲突、未知单位、来源缺失/越界/变更、期间不足、格式限制及精确换算；它们不能替代上述真实工程证据。
- 候选确认持久化、来源版本失效和计算 runtime 接入仍未实现；现有 Agent runtime 仍只开放检索。

## 本地收入确认与持久事实计算合同（2026-10-05）

- `RevenueConfirmationService` 是独立本地应用入口。`preview` 只展示；`confirm`
  要求明确接受和操作者所见的完整快照摘要，再重新查证并收集候选，完全一致才保存。
  不能由等待确认状态、库中已有数字或仅相同 `source_ref` 推断接受。
- `RevenueSourceReader` 从服务端文档服务取得 workspace/document、`ready`、
  `content_sha256` 和 `attempt`，重新读取原 PDF 核对摘要，收集前后再次核对文档。
  当前候选来自当前抽取代码和真实 Retriever；完整快照包含两期金额、规范单位、
  全部原文证据及抽取方法/版本，不含检索分数。调用方只提交所见摘要，不提交版本真值。
- PDF 内容不同的正常上传产生不同 document_id；没有新增同 ID 替换 PDF 入口。
  实际文件缺失/内容与记录不符会阻断；`attempt` 只覆盖现有失败后重试。
  抽取规则修改必须同步维护 `EXTRACTION_VERSION`，重新收集还能发现当前候选内容变化。
  不证明全索引完整性，不提供 ready 文档通用重处理或并发外部文件修改的跨存储锁。
- `SQLiteRevenueConfirmationRepository` 与 documents 共用同一 SQLite 文件，增加
  `revenue_confirmations` 与 `confirmed_revenue_facts` 两表。`BEGIN IMMEDIATE`
  内重新核对当前文档，确认头和两期事实全部提交或回滚。相同仍有效的快照重复确认
  返回原确认 ID/时间；损坏的半组记录不会由重复确认静默修复。
- 确认保存单用户动作类型 `local_operator`；机械测试使用 `simulated_test` 并明确标注。
  两者不能通过重复确认相互冒充。没有认证、审批权限或通用审计系统。
- 金额以规范十进制 TEXT 保存，用 `Decimal` 读回；不经过 float。读回完整两期、
  结构验证和内容摘要验证均通过后，还必须与本次新查证的快照一致。
  历史确认保留，其可用性针对当前来源动态核对；不持久保存或复用计算结果。
- 一次计算专用的 SQLite 查询适配器实现现有 `FinancialFactRepository`，同时限制
  workspace/document/指标/source_ref。`calculate_confirmed_revenue_growth` 支持注入
  此查询，仍复用 `CalculateFinancialMetricTool` 的唯一公式和 `ROUND_HALF_UP` 两位舍入。
  原纯 Python 变体继续使用默认内存仓储；不能绕过本地服务来证明持久确认准入。
- 计算前重新查证、读库；返回结果前再次核对当前候选。缺确认、范围不符、期间/单位
  不合法、零分母、来源变化和记录损坏都不返回可用结果，不回退到历史成功值。
  成功结果包含确认 ID/时间/动作类型、版本、两条输入事实与全部原文证据。

本地入口（使用显式隔离的 ready 数据根，不读取默认 runtime 或 LLM 配置）：

```sh
PYTHONPATH=. python scripts/revenue_review.py preview \
  --runtime-root /absolute/isolated-runtime --document-id DOCUMENT_ID
PYTHONPATH=. python scripts/revenue_review.py confirm \
  --runtime-root /absolute/isolated-runtime --document-id DOCUMENT_ID
# 终端展示全部候选后，操作者输入 CONFIRM <本次所见的完整摘要>。
# 没有 --yes；重开进程计算只读取已保存确认，不创建新的确认。
PYTHONPATH=. python scripts/revenue_review.py calculate \
  --runtime-root /absolute/isolated-runtime --document-id DOCUMENT_ID \
  --confirmation-id CONFIRMATION_ID --output new-calculation-report.json
```

`tests/test_revenue_confirmation.py` 使用真实 SQLite/文档服务/抽取/计算，检索与
PDF bytes 为替身，确认是显式模拟。真实上传、实际检索、操作者确认和重开计算
须另外执行并保留当次报告，测试通过不能代替该人工链。现有 Agent runtime 仍仅检索。

当前验证证据：

- [真实候选](../artifacts/revenue-confirmation/actual-candidates.json)：新隔离数据根中
  实际 ASGI 上传合成 PDF，经 parser/BGE/Milvus/真实 Retriever 获取两期候选。
- [明确确认](../artifacts/revenue-confirmation/actual-confirmation.json)：操作者核对完整
  快照后明确输入绑定其摘要的 `CONFIRM` 指令，CLI 再查证，保存动作类型为
  `local_operator`；此步骤只保存确认，`result` 仍为 null。
- [重开计算](../artifacts/revenue-confirmation/actual-calculation.json)：确认进程退出，
  新 CLI 进程从 SQLite 读回同一确认 ID 和两条十进制 TEXT 金额，重新查证来源后
  复用原计算器得到 `20.00 / PERCENT / revenue_growth_rate_v1`，输入/证据完整。
- [实际存储受控故障](../artifacts/revenue-confirmation/actual-source-changed-rejection.json)：
  仅在成功数据根的新副本中追加 PDF 字节，保留原数据库的内容摘要与确认记录；
  CLI 返回 `source_changed`、result=null、退出1。该故障注入证明实际文件会重新核对，
  不表示产品新增同 ID 替换上传功能；原成功来源、确认与报告均保留。

- [验证汇总](../artifacts/revenue-confirmation/verification.json)：定向70 passed，
  Ruff/4源码mypy/diff检查通过。其余拒绝、损坏与事务故障使用明确标注的替身输入和
  模拟动作。旧业务卷未挂载，模型缓存只读，无网络、无 LLM，新临时容器执行后移除。

## 收入研究的最小图调度合同（2026-10-06）

- `app/agent/revenue_graph.py` 提供独立 `build_revenue_graph(service=...)` 装配入口，
  返回实际编译的 LangGraph 图；执行使用 `await graph.ainvoke(input)`。
  不接生产 Agent runtime、HTTP/UI，不调用 LLM。
- 锁定 `langgraph==1.2.13`，其 `langchain-core>=1.4.7,<2` 与现有 `1.5.0`
  兼容；锁文件只新增 langgraph、langgraph-checkpoint 4.2.0、langgraph-prebuilt
  1.1.0、langgraph-sdk 0.4.5、ormsgpack 1.12.2，原有包无升级或删除。
  安装的精确签名与官方 [Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
  对照；传递依赖的存在不表示启用其能力。
- `RevenueGraphInput` 只接受 `document_id` 与可选 `confirmation_id`。
  ID 是查询定位信息，不证明文档范围、授权、确认存在或仍有效；不接收裸金额、
  accepted、操作者类型或调用方自报来源版本。
- `RevenueGraphState` 只保存两 ID、本次候选/版本摘要、调度状态、结果、错误码和
  错误类别。摘要包含 snapshot_id、来源 revision 与期间/规范金额/单位；
  金额摘要不进入公式，snapshot_id 只是比较键。服务、仓储、连接与 Retriever
  在图外组装并通过闭包注入；不设计 checkpoint 序列化。
- 原 `RevenueWorkflowState` 与业务转移函数继续由候选/确认/计算服务复用，
  图 State 只传递单次执行数据，不重新定义候选、确认或来源真值。

| 节点 | 读取 | 调用/更新 | 下一步 |
|---|---|---|---|
| `read_review` | document_id | `service.preview`；写当前摘要及 previewed，清除旧结果/错误 | previewed → check_confirmation；业务拒绝/程序失败 → END |
| `check_confirmation` | confirmation_id | 无 ID → needs_confirmation；有合法非空 ID → verification_pending | verification_pending → calculate；其他 → END |
| `calculate` | 两 ID | `service.calculate`；成功写 completed/结果；确认缺失写 needs_confirmation，其他业务拒绝写 refused，意外异常写 failed | 全部 → END |

- 条件边只读取节点已经写入的 status；不查库、不调用服务、不再次检索。
  verification_pending 仅表示存在查询线索，不表示确认有效。
- 核验/计算节点复用现有应用服务：当前来源查证、SQLite 完整有效确认读回、
  范围受限事实查询、唯一公式与舍入、返回前再次来源查证均保持原实现。
  图的读取摘要节点增加一次 preview；服务 calculate 内部的必要查证保留。
  正常成功合计三次候选收集（preview 一次、calculate 前后两次），条件边零检索。
- 节点返回局部字段更新，默认按字段覆盖；未返回字段会保留，故所有失败出口
  显式写 result=None，读取节点也清除上次输出。输入 schema 限制外部仅传 ID，
  重用旧输出不会发布旧结果。未配置消息列表、自定义 reducer、并行节点。
- `RevenueConfirmationError` 的稳定业务码映射为需要确认或拒绝；已有文档不存在/
  非 ready 异常映射为 source_unavailable。其他 Exception 记录完整内部日志并返回
  failed/program/unexpected_error，不向结果暴露原异常，也不宣称业务成功。
  错误成功对象属于程序失败；不捕获取消等 BaseException，不配置盲重试。
- 图端口仅包含 preview/calculate，没有 confirm；图不创建确认、不伪造接受动作，
  只读取已有记录。机械集成测试的接受动作明确使用 simulated_test。
- 顺序函数与 if 也可实现本例。图提供显式调度与分支、局部状态更新及可观察节点
  顺序，同时增加类型/装配/依赖成本；业务校验仍在应用服务。

验证按证据层分别记录：

- `tests/test_revenue_graph_routing.py`：完全 fake 业务服务，只证明图路由、异常分类、
  不重试与失败无结果，不能代替业务集成。
- `tests/test_revenue_graph.py`：实际 compile/ainvoke/astream + 真实确认服务、SQLite、
  现有抽取与计算；检索及 PDF bytes 是替身，确认标 simulated_test。完整成功 payload
  与相同限定输入的直接调用一致；覆盖无/未知确认、快照变化、实际替身文件摘要变化、
  计算后来源重查、零分母、旧输出清理及节点顺序。
- `scripts/verify_revenue_graph.py`：仅对显式 disposable ready 副本运行，真实 Retriever、
  实际合成 PDF 与既有 local_operator 确认；对照直接服务与图的完整成功 payload，
  核对缺 ID、未知 ID 和副本实际文件内容变化的拒绝/result=null，再恢复副本文件。
  不调用 confirm，不修改旧成功数据根或旧业务卷，不覆盖历史评测。
- [实际图验证报告](../artifacts/revenue-graph/actual-verification.json) 与
  [定向验证汇总](../artifacts/revenue-graph/verification.json) 记录版本、源码摘要、结果
  与验证边界；不配置 checkpoint/interrupt/恢复/长期记忆，也不替换生产 runtime。

## 收入研究产品入口、终态存储与历史读取合同（2026-10-08，待实现）

本节规定独立收入研究产品路径。现有本地候选、确认、SQLite 事实与收入图已经实现；
本节新增的 HTTP 路由、公开 DTO、研究终态仓储及页面尚未实现。
目标限于单文档、营业收入、2024/2025 两期、本地操作者和同步完成的一次图执行。
不改变现有 `/chat`、`/agent/runs`、AgentRun 及 answered/refusal/system_error 合同。

### 用户操作与四个标识

1. 选择 ready 文档并点击审阅：展示规范金额、原始金额/单位、期间、文件/页码、
   全部合并来源及原文位置；没有确认写入，也不创建长期研究记录。
2. 明确接受这次展示的完整候选：服务端重新收集并比较所见快照，完全一致才沿用
   现有整组确认事务；变化则要求重新审阅，不静默接受新候选。
3. 明确运行研究：只用文档与确认查询线索执行一次收入图；结束后验证并保存完整
   终态，提交成功才返回可用研究 ID。图不代替操作者确认。
4. 刷新或重新打开已知研究 ID：只读已保存终态，并标明历史文档与执行时间。

| 标识 | 用途与产生方 | 持久性/边界 |
|---|---|---|
| `document_id` | 已有文档记录身份；页面取自文档选择 | 查询后还须服务端核对范围和 ready；文件名不能替代 |
| `snapshot_id` | `RevenueReview.snapshot_id` 对完整内部 review 生成的 SHA-256 内容比较键 | 不是确认 ID，也不是数据库行 ID；审阅不单独保存快照表 |
| `confirmation_id` | 现有仓储成功保存明确接受后返回的唯一确认身份 | 绑定完整快照及两期事实；相同仍有效快照复用原 ID/时间 |
| `research_id` | 研究应用服务为一次已结束图调用分配的唯一身份 | 只有完整终态提交成功才对外返回；不是图 checkpoint/thread ID |

`document_id` 相同不足以证明完整审阅内容相同。当前没有同 ID 替换 PDF 产品入口；
候选/证据/抽取版本变化仍须通过快照比较发现。确认记录保留不等于当前仍可计算。
跨文档确认、未确认候选或客户端自造金额不得进入公式。

### 四个 HTTP 入口与严格请求

后端路径如下；浏览器沿现有 Vite 代理使用 `/api` 前缀。
所有请求 DTO 禁止额外字段，采用严格类型；不把数字转字符串、不把字符串转布尔。
ID 使用严格非空字符串并拒绝纯空白；`snapshot_id` 必须为 64 位小写十六进制。
workspace、操作者类型、金额、单位、来源版本、候选和研究身份均不得由请求创造。

| 操作/入口 | 请求 | 成功响应 | 服务责任 |
|---|---|---|---|
| `POST /revenue-research/reviews` | `{document_id}` | 200，完整 Review DTO | 范围/ready 前置核对后调用 `preview`；不写确认/研究 |
| `POST /revenue-research/confirmations` | `{document_id, snapshot_id, accepted}` | 200，已提交 Confirmation DTO，含复用回执 | `accepted` 必须严格为 true；转换为服务参数 `reviewed_snapshot_id`；服务端固定 `local_operator` |
| `POST /revenue-research/runs` | `{document_id, confirmation_id?}` | 201，已提交 Research DTO，可能成功、拒绝或失败 | 范围/ready 核准后一次 `graph.ainvoke`；验证终态、一次保存后返回 |
| `GET /revenue-research/runs/{research_id}` | 路径 ID，无执行 body | 200，与 POST 相同的已保存 Research DTO | 固定服务端范围查库并校验；不执行图/检索/确认/计算 |

`accepted=false` 是明确未接受：409/confirmation_required，不查候选、不保存。
`accepted` 缺失、类型错误及额外字段为 422/invalid_revenue_request。
运行的 `confirmation_id` 可缺省或为 null：允许图形成可保存的 confirmation_required
拒绝；若提供字符串则要求非空。格式合法但未知或属于其他文档的确认 ID 也属于
运行时业务核验，不提前制造“有效确认”。页面正常链必须先获得确认回执才开放运行。

### 公开 DTO 与序列化边界

所有公开对象禁止额外字段，金额由 Decimal 格式化为十进制字符串，期间/页码/位置
使用严格整数，时间使用带时区 ISO 8601。不公开 workspace、对象 key、SQLite/物理
路径、原始异常、检索分数、模型输出或内部图 State。文件名使用已有逻辑文件名。
公开投影从服务返回的对象构造，不用客户端 payload 恢复事实；嵌套对象同样白名单。

- **Revision DTO**：`content_sha256`、`attempt`、`extraction_method`、
  `extraction_version`。文档身份由外层携带，workspace 留在内部范围与存储元数据。
- **Evidence DTO**：`chunk_id/source_file/page/text/start/end/raw_value/raw_unit`；
  保留全部证据原文、原始金额/单位与位置，禁止只取 evidence[0]。
- **Candidate DTO**：`source_ref/chunk_id/source_file/page/period/value/unit/`
  `extraction_method/extraction_version/evidence`；正常 review 两期均为 CNY_YUAN，
  evidence 非空，按期间排序。两条规范值及证据应能核对 100 万元→1000000 元、
  120 万元→1200000 元；有限抽取规则的限制保持现有合同。
- **Review DTO**：`schema="revenue-research-review-v1"`、`document_id/source_file/`
  `snapshot_id/revision/candidates`。必须显式取 `review.snapshot_id`，当前
  `RevenueReview.to_payload()` 不包含此字段；图的 ReviewSummary 不足以代替完整审阅。
- **Confirmation DTO**：`schema="revenue-research-confirmation-v1"`、
  `document_id/confirmation_id/confirmed_at/snapshot_id/confirmation_kind`；本产品入口
  的 kind 固定为 local_operator。机械测试另用 simulated_test 并标明，不能冒充本人接受。
- **Calculation DTO**：沿用 `ConfirmedRevenueCalculation.to_payload()` 的语义，含
  `confirmation_id/confirmed_at/confirmation_kind/snapshot_id/revision/value/unit/`
  `formula_id/inputs`；revision 与 inputs 使用上述公开投影。`value="20.00"`、
  `unit="PERCENT"`、`formula_id="revenue_growth_rate_v1"` 来自唯一现有计算器。
  inputs 包含两期完整候选及全部证据；不经过 float，不从图摘要再次组装金额。

公开投影省去内部 scope 字段不改变快照算法。snapshot 仍根据现有完整内部
`RevenueReview.to_payload()` 计算；客户端只回传摘要，不根据公开 DTO 自行重新计算。

**Research DTO** 的公共字段为 `schema="revenue-research-result-v1"`、
`research_id/document_id/source_file/confirmation_id/started_at/finished_at`；
`confirmation_id` 保存本次输入查询线索，可为 null，不宣称其一定有效。
按 `status` 区分三种互斥结果：

| status | calculation | error_code/message |
|---|---|---|
| `completed` | 必填且必须是通过校验的 Calculation DTO | 两字段均为 null |
| `refused` | 必填且只能为 null | 必填稳定业务码和固定安全说明 |
| `failed` | 必填且只能为 null | 固定 unexpected_error 与安全说明 |

成功计算的确认身份必须等于请求确认 ID，来源文档/逻辑文件名必须与核准文档一致，
两期/单位/公式和完整输入证据必须符合现有合同。图 completed 却缺/错结果，或未知图
状态，不允许补造计算值，作为 failed/unexpected_error 保存。映射不重新计算公式。
已知稳定业务错误从现有确认服务、Workflow 与计算器枚举维护显式白名单及固定说明；
未知码安全收窄为 failed/unexpected_error，不直通异常字符串。

图的 needs_confirmation 映射为 refused/confirmation_required；refused 保留已知
业务原因；failed 映射为 failed/unexpected_error。previewed/verification_pending
是内部中间态，不能作为公开终态保存。图内部 error_kind、review_summary 不直通 HTTP。
拒绝/失败不发布候选快照为“已核准版本”，不携带旧 calculation；只有成功计算已有
的 revision/inputs 被保存为该次执行来源。HTTP 与持久读回使用相同的判别联合校验。

### 请求与响应小例

以下 D1/S1/C1/R1 为讲解用符号，示例中 64 个 a 是符合字段格式的占位摘要 S1，
实际 ID/摘要须由服务端返回，不能拿占位值确认真实文档。省略的嵌套内容只为
缩短示例，真实响应必须满足前述完整 DTO，不得返回省略号。

```http
POST /revenue-research/reviews
Content-Type: application/json

{"document_id":"D1"}
```

200 的响应包含 document_id=D1、source_file=synthetic.pdf、snapshot_id=S1、
完整 revision 与两条 candidates。2024 的 value="1000000"、2025 的
value="1200000"，unit 均为 CNY_YUAN；evidence 保留第 1 页的原文“100万元”与“120万元”。

```http
POST /revenue-research/confirmations
Content-Type: application/json

{"document_id":"D1","snapshot_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","accepted":true}
```

正常 200 回执示意：

```json
{"schema":"revenue-research-confirmation-v1","document_id":"D1","confirmation_id":"C1","confirmed_at":"2026-10-08T02:00:00Z","snapshot_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","confirmation_kind":"local_operator"}
```

服务端重查快照不同则 409，无 confirmation_id：

```json
{"detail":{"code":"review_changed","message":"审阅内容已变化，请重新审阅后明确接受"}}
```

```http
POST /revenue-research/runs
Content-Type: application/json

{"document_id":"D1","confirmation_id":"C1"}
```

正常提交后 201：公共身份/时间、status=completed、完整 calculation（包含
value="20.00"、PERCENT、唯一 formula_id、确认快照、来源版本与两期输入），
error_code/message 均为 null。不能仅返回一个没有来源的百分数。

格式合法但未知确认输入的已保存拒绝示意（仍为 201）：

```json
{"schema":"revenue-research-result-v1","research_id":"R2","document_id":"D1","source_file":"synthetic.pdf","confirmation_id":"unknown-confirmation","started_at":"2026-10-08T02:05:00Z","finished_at":"2026-10-08T02:05:01Z","status":"refused","calculation":null,"error_code":"confirmation_required","message":"缺少可用确认，请重新审阅并明确接受"}
```

`GET /revenue-research/runs/R2` 返回 200 及同一份已保存拒绝，不替它补做确认。
成功 R1 的 GET 同样只读原成功记录，不能按当前候选重写 revision 或 20.00%。

### 前置 HTTP 错误与可保存业务终态

前置核对由应用服务在图调用之前执行；运行已进入图后的业务核验由原图/确认服务
负责。同类问题因发生阶段不同可能表现为前置 HTTP 错误或已保存终态，应显式分清。

| 场景 | 响应/记录 | 页面行为 |
|---|---|---|
| 输入非法、额外字段、快照格式错误 | 422/invalid_revenue_request；不执行、不写库 | 说明请求不合法，无研究 ID |
| 收入依赖未注入 | 503/revenue_service_unavailable；不初始化重依赖 | 显示服务未启用 |
| 所选文档不存在或越界 | 404/document_not_found；两者同响应，不执行图 | 清理当前操作数据，重新选择 |
| 前置时文档未 ready | 409/document_not_ready；无确认/研究写入 | 等文档可用后明确操作 |
| reviews/confirmations 的候选/来源业务问题 | 409/对应已知稳定码；不新增确认/研究 | 清除旧回执/结果，说明原因；review_changed 必须重审 |
| confirmations 的确认记录损坏 | 500/confirmation_integrity_error；不静默修复或新增成功回执 | 显示无法完成确认，禁止以旧值计算 |
| reviews/confirmations 的 SQLite 或意外异常 | 500/revenue_storage_error 或 revenue_internal_error；安全说明，无原异常 | 不显示成功回执，不自动重发 |
| 图运行中缺/未知/跨文档确认 | needs_confirmation→已保存 refused/confirmation_required，201 | 显示拒绝与研究 ID；无计算结果，引导审阅/确认 |
| 图运行中来源变更等已知业务拒绝 | 已保存 refused/原稳定码，201 | 撤下旧计算结果；不自动确认或重算 |
| 图捕获程序异常 | 已保存 failed/unexpected_error，201 | 显示已保存失败及 ID，不展示计算值 |
| 图算出结果但终态保存失败 | 500/revenue_storage_error；不返回 research_id 或 calculation | 不能宣称结果已保存；不自动重发 POST |
| GET 未知或其他范围研究 ID | 404/research_not_found | 无历史结果；不改为 POST |
| GET 损坏 JSON、身份不符、未知 schema、状态/结果不匹配 | 500/research_result_integrity_error | 安全失败；不部分展示或通过重新计算修复 |
| GET 数据库读取失败 | 500/revenue_storage_error | 历史读取失败，不生成 failed 研究来替代原记录 |

HTTP 错误壳统一为 `{"detail":{"code":"稳定码","message":"固定安全说明"}}`，不带
研究 ID/旧结果。运行图内若底层 SQLite 异常已被图映射成 failed，则在研究终态能够
成功保存时返回已保存 failed；不能笼统把所有 SQLite 问题写成同一阶段的 HTTP 错误。
取消/进程中断等没有完整终态的情形不保证保存，不把它们伪造成图正常结束。

### 研究终态存储与 GET

在已有 `documents.db` 增量增加独立 `revenue_research_results` 表，不改旧 agent-runs.db。
最小元数据列：`research_id` 主键、服务端 `workspace_id`、`document_id`、逻辑
`source_file`、可空 `confirmation_id` 查询线索、`schema_version`、`status`、
`started_at/finished_at`、`payload_json`。schema_version 初始为 1，status 限定三终态。
payload 为校验后完整公开 Research DTO；元数据与 payload 的身份、状态、时间/版本
须一致，GET 时再次验证。只存必要业务终态，不存服务对象、连接、内部 State 或消息轨迹。

confirmation_id 不设无条件确认外键：未知/跨文档 ID 是可能的正常拒绝输入，必须
允许记录本次查询线索及拒绝。document 身份也按执行时快照保存，不以 GET 查询当前
文档状态来补授权或删除历史；内部 workspace 查询范围始终来自服务端配置。

应用服务流程：前置核准文档并记录服务端身份→记录 started_at→一次图调用→
记录 finished_at→映射/校验公开终态→分配 research_id→构造并校验完整记录→
仓储一次 INSERT 事务提交→返回 201。仓储异常回滚，不返回内部分配的 ID。
响应编码可能在提交之后遇到网络故障，因此只承诺收到的 ID 对应已提交记录，
不承诺未收到 ID 就一定没有记录。公开投影/序列化校验须尽量在 INSERT 前完成。

确认保存与研究保存是两个明确用户动作、两次事务，不能宣称跨动作原子性。
研究仓储只有 save_terminal 与固定范围 get_terminal；没有 queued/running 状态表，
不建跨确认总体 Run 状态机，不追踪未完成审阅，也不承诺进程中断恢复。
GET 不要求历史文档此刻 ready，不读取当前文件/检索库/确认可用性，不宣称当前
来源有效；仅返回执行时记录的身份与成功结果已有来源版本。重新核验是新的明确运行。

### 页面责任与后续文件地图

页面使用明确的审阅、接受、运行按钮；accepted 不能在挂载、刷新或图中自动发生。
切换文档、开始重审或确认/运行失败时撤下当前旧回执/计算；历史数据库记录保留。
pending 防重复点击，并以请求所属文档/活动请求身份阻止迟到响应覆盖新选择。
只保留一个独立的已知 research_id 引用用于刷新 GET（或提供手动输入）；
不复用旧 Agent 本机历史索引，不保存候选原文/密钥，不建研究历史列表。
历史结果明确展示它自己的文档/文件与执行时间，不能冒充当前所选文档的新结果。
断网/取消等待而没收到 ID 时显示“结果未知”，不自动重发任何运行 POST。
完整幂等键、运行中恢复、后台 worker、SSE、checkpoint 与历史中心留后续。

| 接入阶段 | 实际文件落点（拟新增文件明确标注） | 职责 |
|---|---|---|
| 审阅/确认 HTTP | 既有 `app/api/runtime_factory.py` | 复用 document_service、object_store、document_preparer、同一 Retriever 与 documents.db；组装 CandidateService→SourceReader→ConfirmationRepository→ConfirmationService |
| 审阅/确认 HTTP | 既有 `app/api/app.py` | 可选注入收入依赖、服务端范围并挂载独立 router；缺依赖安全 503 |
| 审阅/确认 HTTP | 拟新增 `app/api/revenue_research.py`、`app/api/revenue_research_schemas.py` | 四入口中的 reviews/confirmations，严格 DTO、完整证据/快照、安全错误壳；后续在同文件补 runs/GET |
| 审阅/确认 HTTP | 既有 `app/agent/revenue_confirmation.py`、`app/agent/sqlite_financial_facts.py` | 复用已有 preview/confirm/calculate 与整组确认，不重写公式或快照算法；公开 DTO 补 snapshot 属于 API 投影 |
| 图执行/持久 GET | 拟新增 `app/agent/revenue_research.py`、`app/agent/revenue_research_storage.py` | 单次研究应用服务、终态模型/安全投影及仓储端口；无跨确认总体状态机 |
| 图执行/持久 GET | 拟新增 `app/agent/sqlite_revenue_research_repository.py` | 同库增量建独立表，一次事务保存、固定范围读取、版本/完整性验证；不复用确认外键阻断拒绝 |
| 图执行/持久 GET | 既有 `app/agent/revenue_graph.py`、上述 router/schema/factory/app | 复用一次 ainvoke 与 END；装配研究服务，增加 POST/GET 及判别联合；不把持久写入塞到图边 |
| 薄页面 | 既有 `frontend/src/App.tsx`、`frontend/src/index.css`、`frontend/src/requestOwnership.ts` | 复用文档选择/视觉/请求归属，接入独立收入区域 |
| 薄页面 | 拟新增 `frontend/src/RevenueResearchPanel.tsx`、`frontend/src/revenueResearchRequest.ts`、`frontend/src/revenueResearchResult.ts`、`frontend/src/revenueResearchReference.ts` | 三个明确动作、独立 DTO 解码/状态/历史标识、已知 ID GET；旧 Agent 文件不泛化 |

以上命名为实施落点，若局部合并须保留责任边界。现有 runtime 启动仍有 LLM 配置
与资源检查，收入图本身不调用 LLM；本接入不顺带改造旧配置体系。同步检索/SQLite
沿现有 asyncio.to_thread 边界，HTTP await 服务，GET 只委托库读取；不阻塞事件循环。

### 实施验收边界（待执行）

- 审阅返回完整证据及服务端快照；严格请求拒绝多余 scope/金额/类型；服务端固定
  local_operator，review_changed 不新增确认，相同有效快照复用原回执。
- 真实服务与临时 SQLite 下验证一次图→完整成功及业务拒绝终态→重建服务 GET；
  未知确认可保存拒绝，成功计算存在、拒绝/失败 calculation=null，写失败无可用 ID。
- GET 检索/确认/计算调用数均不增加；未知/跨范围/损坏/未知版本安全失败，来源改变
  后历史成功仍只读原执行版本。保存失败、HTTP 前置失败、已保存 failed 分别断言。
- 页面明确操作、切文档与迟到响应、防重复点击、刷新只 GET、未知结果不自动重发；
  受控 E2E 与真实上传/检索/本人确认链分层留证，不能以模拟确认冒充操作者接受。
- 当前本节仅合同设计，未新增代码骨架、未运行服务/模型或测试；既有验证报告保持
  原版本与范围，不作为新增 HTTP/UI/持久研究结果已经完成的证据。

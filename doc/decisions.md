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

- [composition root](../app/api/main.py) 显式提供 RAG 已创建的同一个 Retriever，复用 `findoc_runtime_documents_v1`、现有 Milvus 检索连接及关闭处理、同一个 OpenAI 兼容客户端。新增 Run/Event 库为 runtime 根目录下的 `agent-runs.db`；必需配置仍先于 BGE、SQLite、对象目录和 Milvus 初始化。后续装配失败时关闭已创建的检索连接。
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

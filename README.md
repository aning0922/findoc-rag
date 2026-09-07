# FinDoc RAG

中文财报解析与可溯源向量检索原型。

> **项目状态：建设中。** 当前已形成相互隔离的冻结评测库与 runtime 上传库，并完成可信非流式 RAG、引用校验、双层拒答、文档状态 API、SSE 聊天适配、React/TypeScript 单页薄壳、真实OpenAI兼容Function Calling与有限受控tool loop、复用同一业务合同的LangChain工具与消息薄适配，以及可持久查询的Agent Run/Event与独立12题评测链。测试范围另有唯一陌生schema工具Gate，但它未进入生产registry。
> 已使用真实文本层 PDF、真实 parser、真实 bge-m3、runtime Milvus Lite、真实 LLM、SSE 和浏览器完成一次成功回答与引用闭环并验证范围外拒答；真实模型工具smoke也已走通`user→assistant→tool→assistant`与确定性`25.00%`计算结果。
> 当前仍是单机学习原型，不具备任务恢复、身份认证、多用户隔离或生产级存储与队列能力。

Agent 内核已接入 runtime 依赖装配：复用上传库的 Retriever 与模型客户端，服务端查证单文档后只开放 `search_finance_docs`。当前证据来自替换重依赖的正式装配测试，尚未运行这条 Agent 链的真实依赖 smoke；计算、用户结果/引用校验、用户结果持久化和 HTTP/UI 仍未接通。范围与证据见[单文档任务合同及装配记录](doc/decisions.md#agent-单文档任务合同装配前约定)。

## 项目目标

FinDoc RAG 面向包含长文本和复杂表格的企业财报，探索一条可验证的 RAG 工程链路：

- 从 PDF 或 MinerU 输出中提取正文、标题、表格和页码
- 按中文文本特点进行分块，并保留来源元数据
- 使用 bge-m3 生成向量，写入 Milvus Lite
- 建立可重复的检索评测，记录 badcase、延迟和质量变化
- 在检索可靠后，再增加引用回答、拒答、工具调用和审核工作流

当前仓库已覆盖从解析、检索、可信生成到最薄浏览器问答的单机链路；未完成的生产能力仍保持明确边界，不把规划描述为已实现。

## 当前状态

| 模块 | 状态 | 说明 |
|---|---|---|
| LLM 调用示例 | 可运行 | DeepSeek OpenAI 兼容接口；包含同步、流式和异步并发示例 |
| PDF 快速解析 | 原型可运行 | PyMuPDF 提取正文，pdfplumber 提取表格 |
| MinerU 输出适配 | Day43真实数据smoke通过 | 已知`text/table/header/footer/page_number/image`有显式保留/跳过/报错策略；表格检索`text`含标题、表头和表体，`table_md`保留原始HTML |
| 中文分块 | 第6周理解Gate通过 | 中文分隔符+token计数、metadata复制、表格双表示与稳定ID已有测试；参数最优性待查询级评测 |
| Embedding | 本地实验已跑通 | bge-m3，dense vector维度为1024；Day39用5条候选和1条查询完成脱离Milvus的观察性黑盒对照 |
| Milvus Lite | legacy/v2并存 | 旧`findoc`保留7,451行；Day43新增`findoc_day43_v2` 5,269行，使用固定demo workspace和三份不同的稳定document_id；本地数据和数据库不提交 |
| 向量摄取与文档生命周期 | 小样本Gate通过 | Day40已验证合法chunk、embedding text、vector和Milvus row一一对应，并实现一种按`document_id`删除后重建的收敛策略；尚无事务或原子替换 |
| Retriever | Day43同配置对照通过 | 依赖注入、稳定`SearchHit`和可信workspace/source_file过滤保持不变；v2真实schema带workspace，legacy仅由实验兼容store移除经验证的workspace条件 |
| 检索评测 | Day43新旧对照完成 | 12题/13个证据ID迁移到v2；同bge-m3、COSINE、top_k=5和Retriever下，Hit@1 0.20→0.20、Hit@5 0.40→0.50、MRR 0.27→0.3333；逐题原始结果独立保留 |
| RAG 控制层 | 可信终态链已实现 | `retrieve → evidence gate → context/prompt → generation → parse/citation validation → RAGResult/RefusalResult/SystemErrorResult`；非法引用 fail-closed |
| Function Calling受控loop | 原生协议与真实适配已运行 | tools只从唯一registry/Pydantic schema生成；模型工具名、JSON、schema、可信上下文、权限、来源、重复调用和执行结果均由应用校验；默认`max_steps=4`，SDK重试关闭，每step最多1次白名单重试，五类终态明确 |
| 财报业务工具 | 两个固定工具可运行 | `search_finance_docs`只包装既有Retriever；`calculate_financial_metric`只支持`revenue_growth_rate_v1`并从受workspace/document约束的进程内可信fixture取Decimal数值；确定性ToolResult独立保存，模型最终文本不能覆盖计算真值 |
| LangChain工具与消息薄适配 | 项目可用L2 | 使用`langchain-core`的`AIMessage`、`ToolMessage`、`@tool`、schema转换和`StructuredTool.from_function`；两个正式工具继续复用唯一registry、schema、description、handler与服务端上下文。`bind_tools`仅有应用合同测试，不代表真实provider已接通 |
| Agent Run/Event | 项目可用L2 | 独立SQLite领域与repository保存按workspace隔离的Run、有序安全Event和唯一终态；终结Run与终态Event同一事务。事件是执行结束后的安全投影，不是实时流或完整Event Sourcing |
| Agent评测 | 12题冻结基线已运行 | 独立于W8 RAG题集；工具选择、参数、终态三个scorer分别计分。真实`deepseek-v4-flash`唯一一次运行结果为75.00%、61.54%、58.33%，原始结果按唯一评测run ID保存 |
| W9理解Gate | 工程通过、理解未收口 | 闭卷最小loop与测试专用复核工单陌生schema已运行；本人仍不能独立解释测试局部registry与生产factory装配隔离，因此Function Calling暂保持L2，不以测试全绿晋级L3 |
| 上传状态链 | 单进程原型可运行 | `queued → parsing → indexing → ready/failed`；SQLite 记录和 LocalObjectStore 持久，但内存任务不耐久 |
| 可信聊天 API 与 SSE | 可运行 | POST 请求只接受 `document_id/query`；服务端恢复 workspace 并构造 `document_id` 过滤；事件固定为 `status/final_answer/citation/usage/error/done` |
| React/TypeScript 页面 | 最薄闭环可运行 | 上传、列表、轮询、ready 选择、问答、拒答、安全错误、答案与可验证引用；Node 24 + Vite 代理 |
| 框架Agent / 权限 / 生产基础设施 | 计划中 | 尚未引入LangChain自动执行器、ChatOpenAI生产路径、LangGraph、登录、多用户、Redis、S3、可靠队列或后台恢复；原生`run_tool_loop`仍是唯一受控生产基线 |

“本地实验已跑通”表示作者使用本地数据完成过验证，不代表仓库已经提供可复现的公开 benchmark。

## 当前数据流

```text
PDF / MinerU content_list.json
        ↓
解析适配器
        ↓
DocChunk（text / page / type / source_file / table_md / section / chunk_id）
        ↓
中文递归分块
        ↓
合法chunk过滤（legal_chunks）
        ↓
稳定workspace/document/chunk身份 + 版本化JSONL/manifest
        ↓
embedding texts → dense vectors
        ↓
对齐组装rows（chunk metadata + vector）
        ↓
按document_id替换写入Milvus Lite
        ↓
query embedding + 可信上下文/业务过滤
        ↓
dense top-k → SearchHit DTO
        ├─冻结评测分支 → Hit@K / MRR
        └─可信问答分支 → evidence gate
                              ↓
                    context budget + 编号证据映射
                              ↓
                    LLM生成 → 引用解析与fail-closed校验
                              ↓
             RAGResult / RefusalResult / SystemErrorResult
                              ↓
                    SSE安全终态 → React页面
```

runtime 上传链为：

```text
浏览器PDF → 文档状态API → parser/chunk/BGE
        → data/runtime/milvus.db
        → findoc_runtime_documents_v1
```

runtime 上传与聊天只访问 `findoc_runtime_documents_v1`，不读取或写入 `findoc_day43_v2` 冻结评测库。自动测试覆盖调用顺序、可信过滤和失败边界；另有一次真实成功回答与引用、一次真实正常拒答的浏览器 smoke。真实 smoke 不是公开 benchmark，也不证明生产可靠性。
MinerU 解析过程目前由仓库外部执行，本仓库只读取其 `content_list.json` 输出。

受控工具调用分支为：

```text
用户问题 → messages + registry生成的tools
        → 真实模型assistant决策 + finish_reason
        → 应用交叉校验消息形状、工具allowlist、JSON与Pydantic schema
        → 服务端ToolExecutionContext注入workspace/document边界
        → 确定性工具执行 → ToolResult独立保存 → role=tool关联回填
        → 正常/协议/工具/供应商/max_steps明确终态
```

LangChain分支只投影工具与消息合同：`ToolSpec → StructuredTool`，服务端通过闭包注入同一个`ToolExecutionContext`并委托原handler；模型schema不包含workspace、用户、角色或授权结论。该分支没有复制业务逻辑、生产模型客户端或完整tool loop。

一次受控执行结束后，`AgentRunService`在原生loop外将安全业务事实投影到独立SQLite repository：

```text
服务端生成run_id + 注入可信workspace → 保存running Run
        → 调用唯一run_tool_loop
        → 从LoopOutcome/messages/trusted_tool_results提取白名单事实
        → 同一事务写终态Event并终结Run
        → workspace_id + run_id查询Run与有序Event
```

这里不保存system prompt、原始用户prompt、完整messages、检索全文、原始供应商响应、原始异常/traceback、密钥、base URL或隐藏CoT。错误workspace与不存在run对外采用相同not-found语义。

真实工具smoke使用现有两个正式工具和`InMemoryFinancialFactRepository`固定fixture，在`max_steps=2`下以2次provider attempts完成`user→assistant→tool→assistant`，模型请求`calculate_financial_metric`，可信结果为`revenue_growth_rate_v1=25.00%`。该证据只证明真实SDK协议链和应用终止边界，不代表OCR、财报结构化抽取、持久化财务数据库或任意指标能力。

冻结Agent评测集包含恰好12条任务，数据集SHA-256为`2d7ab53bc5fafb2a295e5c4391de3b73422c7a117fe0e6687f6b5c375e88012c`。2026-09-01只正式运行一次`deepseek-v4-flash`，评测run ID为`3a2d683e-a3ec-4b13-ac0a-a22cadbfa91f`：工具选择`9/12=75.00%`，参数槽位`8/13=61.54%`，终态`7/12=58.33%`。原评分保持不变。该运行使用固定检索样例与有限内存事实库，不能证明上传文档后的真实 Agent 工具链已接通。已有记录能区分调用申请、部分工具执行结果及运行终态，但未保存完整回答及响应轮次边界，不能确认历史 `protocol_error` 的具体触发分支，也不能断言两次申请来自单次响应。详见[固定结果归因与证据限制](eval/agent_results/agent_eval_3a2d683e-a3ec-4b13-ac0a-a22cadbfa91f_analysis.md)。

固定五题 release smoke 的既有结果经人工核对：事实正确且引用支持 `3/3`、正确拒答 `2/2`、system error `0/5`。这只是该固定样本与配置的观察，不是泛化准确率；合法引用编号也不自动证明语义支持。原始运行身份、逐题依据与限制见[发布证据](doc/release_evidence_v0.1.0.md)。

Day39另外使用Python标准库完成了一条隔离的`query vector → COSINE → 稳定排序 → top-k`链路，并用bge-m3做了5条候选和1条查询的小规模黑盒对照，未使用Milvus或7,451块数据。契约、预测误差和职责边界见[Day39向量检索决策记录](doc/vector_retrieval.md)。

Day40使用fake embedder和临时Milvus Lite完成`合法chunk → embedding text → vector → row`端到端小样本，并只实现按document删除后重建这一种生命周期策略。重复、换序、修改、删除、ghost检查和部分写入失败后的重跑收敛均有测试；没有运行或修改现有7,451块数据库。策略与后置边界见[Day40向量摄取与文档生命周期决策记录](doc/ingestion_lifecycle.md)。

Day41通过依赖注入建立可使用fake embedder/store测试的Retriever，固定`SearchHit`输出，区分非法输入、空结果、底层系统错误、数据契约错误与召回错误，并以可信workspace和用户可选`source_file`明确过滤边界。真实7,451块数据的6题学习基线为Hit@1 `0.2`、Hit@5 `0.4`、MRR `0.3`；这只是Day42正式评测前的小样本。契约、逐题结果和badcase见[Day41 Retriever与检索基线](doc/retriever_evaluation.md)。

Day42将冻结问题集扩展到12题（10题可回答、2题无答案），用同一旧7,451块collection得到Hit@1 `0.2`、Hit@5 `0.4`、MRR `0.27`，warm-up后探索性P50/P95为`54.44/194.75 ms`。Q8再次证明旧表格表体只在`table_md`、未进入embedding text会导致精确数字召回失败；当天保留诚实baseline，不调参或重灌。另用手造raw elements、5维deterministic embedder和临时Milvus完成`adapter → chunk → stable ID → document替换 → Retriever/filter → metrics`陌生Gate。Day41/42契约与后续证据见[Retriever契约与检索评测](doc/retriever_evaluation.md)。

Day43保留旧7,451行`findoc`和Day42 baseline，新增5,269行`findoc_day43_v2`、三份版本化JSONL与manifest。真实MinerU输入共8,750个元素，已显式处理页眉、页脚、页码、图片、空正文、空表壳和未知类型；表格检索`text`不再只有文档名或“第N页表格”，而是包含可见表头/表体，原始HTML继续保存在`table_md`。冻结12题迁移到13个v2稳定证据ID后，以同一模型、COSINE、`top_k=5`、Retriever和评测函数重跑，Hit@1保持`0.20`，Hit@5为`0.50`，MRR为`0.3333`；没有根据结果调参。Q8仍未召回目标表格，但v2候选已包含真实表体，说明上游结构缺陷消除不等于当前dense配置解决所有排序问题。

Day44在不重建Retriever或workspace过滤的前提下，新增供应商无关的最小`LLMClient` Protocol和非流式`RAGService`。fake Retriever/LLM记录调用参数、次数和prompt，自动证明检索失败或空证据时LLM不被调用，生成超时保留原始cause并归入generation失败，切换`TrustedContext`不会黏住上一次workspace且workspace ID不进入LLM prompt。当天只做空证据检查和最小prompt，正式Context Builder、引用校验和拒答后置。

## 技术栈

- Python 3.11+
- Pydantic
- PyMuPDF / pdfplumber / MinerU 输出适配
- LangChain Text Splitters / tiktoken
- LangChain Core 1.5.0（messages、tool schema与工具薄适配；无Agent或provider接入）
- FlagEmbedding bge-m3
- Milvus Lite
- pytest
- OpenAI Python SDK（调用 DeepSeek 兼容接口）
- FastAPI / StreamingResponse
- React 19 / TypeScript / Vite
- Node.js 24

LangChain Agent、LangChain provider集成、LangGraph、PostgreSQL、Redis、S3、Docker Compose 和生产级身份系统属于后续路线，不是当前已实现技术栈。

## 快速开始

### 1. 安装依赖

需要先安装 [uv](https://docs.astral.sh/uv/)。

```bash
git clone https://github.com/aning0922/findoc-rag.git
cd findoc-rag
uv sync
```

依赖包含文档解析和本地 Embedding 组件，首次安装及首次下载 bge-m3 可能耗时较长。

### 2. 生成公开合成 PDF 并检查解析

复用项目已有 PyMuPDF 依赖生成两页中文资料，不需要私有 PDF、模型调用、向量库或服务：

```bash
uv run python scripts/generate_demo_pdf.py
# 可选：--output artifacts/demo/another_demo.pdf
```

默认路径相对于当前目录，为 `artifacts/demo/synthetic_finance_demo.pdf`。文件或目录重名时保留原内容，尝试 `_v2`、`_v3` 等后缀，终端打印实际保存路径。后缀仅避免重名，不代表内容版本。默认目录下的生成 PDF 已被 Git 忽略，可从生成器重建。

每页标注“完全虚构，仅用于软件演示”，并嵌入中文字体。固定事实为：

| 页码 | 虚构企业甲的披露内容 |
|---|---|
| 1 | 2025年度营业收入120万元；2024年度营业收入100万元 |
| 2 | 2025年末员工人数12人；未提供员工年龄信息 |

资料支持直接查问上述收入和人数；员工平均年龄缺少依据，应拒答。这里约定的是资料边界，尚未用该 PDF 验证模型回答或拒答表现，也未接通真实计算事实确认链。

可用现有 `parse_pdf(path, backend="fast")` 读取终端打印的实际路径；返回块的 `page` 从1开始，`source_file` 保留传入路径。上传解析适配器则恢复逻辑文件名。重复生成保证固定事实、页码和文本一致，不承诺 PDF 字节哈希相同。

```bash
uv run pytest tests/test_parse.py tests/test_demo_pdf.py -q
```

专用检查会解析实际新生成的 PDF，验证数字、单位、两页合成标记、页码和两条解析路径的来源映射，比较重复生成的解析内容，并检查重名文件不被覆盖。本演示使用正文文本，不证明任意财报、扫描件或复杂表格能被准确解析或回答。

2026-09-06 本地验证：上述定向检查为 `3 passed`（另有5条底层SWIG弃用警告）；实际生成的最终文件另经 fast parser、上传解析适配器和 Poppler 两页渲染核对，关键文本、单位、页码、来源映射及显示正常。未为此调用模型、运行RAG/Agent评测或修改向量库。

原有解析 smoke 也可单独运行：

这个测试会临时生成一份小型 PDF，不需要下载年报：

```bash
uv run pytest tests/test_parse.py -q
```

完整契约测试可以通过以下命令查看：

```bash
uv run pytest -q
```

历史后端测试曾为 `330 passed`；首次公开 clean clone 暴露私有数据依赖，修复后无私有数据的隔离 candidate 为 `330 passed, 1 skipped`，作者含本地数据的检查为 `331 passed`。历史工具调用相关定向测试为 `70 passed`；另有 Ruff、`mypy app`（45个源码文件）、前端6项测试及 Node 24下构建和 lint 证据。各版本与环境身份见[发布证据](doc/release_evidence_v0.1.0.md)，不将这些历史结果称为当前 HEAD 的全量质量门。测试只证明已覆盖行为，不替代真实检索、答案事实或引用语义核验。

冻结Agent评测可通过以下命令运行；每次结果使用唯一文件名，已有结果不会被覆盖：

```bash
uv run python scripts/evaluate_agent.py
```

### 3. 启动可信上传与问答页面

复制环境变量模板并填写真实 LLM 配置后，无 `--reload` 启动后端，避免开发重载丢失内存任务：

```bash
cp .env.example .env
uv run uvicorn app.api.main:app \
  --env-file .env \
  --host 127.0.0.1 \
  --port 8000
```

另开终端启动 Node 24 和 Vite：

```bash
nvm use
npm --prefix frontend ci
npm --prefix frontend run dev -- --host 127.0.0.1
```

浏览器访问 `http://127.0.0.1:5173`。Vite 将 `/api` 代理到 `127.0.0.1:8000`，当前不扩展 CORS 设计。

### 4. 运行可选的 LLM 示例

```bash
cp .env.example .env
# 在 .env 中填写 DEEPSEEK_API_KEY
uv run python hello_llm.py
```

该脚本只是模型调用示例，不是 FinDoc RAG 的问答入口。

## 仓库结构

```text
app/
├── rag/
│   ├── parse/          # PDF 快速解析与 MinerU 输出适配
│   ├── chunk.py        # 中文分块与 JSONL 保存
│   ├── embed.py        # bge-m3 Embedding
│   ├── ingest.py       # 合法chunk对齐与document级替换摄取
│   ├── evaluation.py   # 逐题排名与结果状态分类
│   ├── metrics.py      # Hit@K、RR与MRR
│   ├── store.py        # Milvus Lite 建库、写入和搜索
│   ├── retriever.py    # 最小 dense retriever
│   └── service.py      # 可信非流式RAG、引用校验、拒答与系统失败边界
├── api/                # health、文档状态API、聊天路由与SSE适配
├── chat/               # 服务端可信请求准备与同步RAG的异步边界
├── gateway/            # 预留，尚未实现
└── agent/              # 原生受控loop、财报工具、LangChain薄适配、Run/Event与Agent评测
frontend/               # React/TypeScript/Vite单页薄壳与SSE流解析测试
scripts/                # 解析、分块、Embedding 和 Milvus 实验脚本
experiments/            # 分块、标准库向量检索与bge-m3小规模对照
tests/                  # smoke test、契约测试与理解Gate测试
doc/                    # 解析器、分块与向量检索决策记录
data/                   # 本地 PDF、JSONL 和 Milvus 数据，不提交
eval/                   # RAG评测资产，以及独立Agent 12题/config/唯一结果
```

当前 `scripts/` 中部分脚本仍使用作者的本地文件名，尚未整理成统一的端到端 CLI。

## 已知限制

- fast解析会跳过扫描页,不识别标题层级,且正文与表格分别收集后再拼接,不能保证原始元素顺序
- MinerU adapter会按上游`text_level`生成section;若上游把复选框等正文误判为标题,adapter无法自行恢复真实层级
- 当前`400/60`只是实现基线;Day38单样本中`400/10`与`400/60`输出相同,最优参数待查询级检索评测
- 表格当前保持原子块,可能超过配置size;完全重复正文缺少真实来源定位时仍有身份歧义
- Day40库函数已验证document级删除后重建，但旧实验脚本尚未统一接入；删除与插入不原子，中途失败可能留下空document或部分rows
- 当前只有 dense retrieval 和最小metadata过滤，没有hybrid search或rerank；v2真实schema有固定demo workspace，但旧7,451行schema仍无workspace_id，也没有完整认证或多租户系统
- Day43已用真实bge-m3构建5,269行v2并验证document级收敛；删除与插入仍非事务原子操作，不证明生产可靠性
- 向量相似度只表示当前向量空间中的接近程度，不验证公司、指标、数值或其他事实是否正确
- 当前已冻结20题可信RAG baseline；第11周再扩展到总30～40题（50题上限）并增加未参与调试的holdout集；7,451/5,269行都只是本地规模，不是质量指标
- legacy表格embedding text退化缺陷作为历史事实保留；v2已让标题、表头和表体进入检索text，但Q3/Q4/Q7/Q8/Q11仍未进入Top 5，后续必须另做受控检索诊断
- runtime上传库与冻结评测库相互隔离；浏览器闭环只查询上传文档所在的`findoc_runtime_documents_v1`
- `InProcessTaskDispatcher`不耐久；进程异常退出会使`queued/parsing/indexing`记录悬空，目前不做启动恢复或可靠队列。真实调试留下两条`indexing`记录，未伪装为ready
- 同步RAG通过`asyncio.to_thread`离开event loop；浏览器断开不代表已经进入线程的底层工作被取消
- LLMClient当前不提供真实token usage，因此保留`usage`事件合同但不发送固定0或伪造数字
- Milvus Lite在本机真实运行中出现过gRPC fork/keepalive提示和一次启动退出码139；BGE首次预热必须早于Milvus/gRPC初始化，已有collection在重启后必须显式load。受控重试后真实成功问答与正常拒答均已完成
- runtime使用固定`demo` workspace，不等于已经实现登录、权限或多租户隔离
- `InMemoryFinancialFactRepository`只是服务端预置的进程内fixture，不是OCR、财报结构化抽取或持久化财务数据库；当前正式计算只支持`revenue_growth_rate_v1`
- 当前只能证明计算`source_ref`属于服务端注入的workspace/document，不能证明一定来自同一轮之前的搜索调用
- `trusted_tool_results`只证明结果由registry内工具实际执行产生；搜索命中的文本仍可能是不可信数据，恶意输出测试不代表彻底解决所有prompt injection
- 最终计算文本保护只检查固定公式、`PERCENT`和ASCII `%`的严格集合匹配，不是通用自然语言事实核验器
- Run/Event是loop完成后的安全投影，不是实时事件；进程被杀或SQLite自身故障仍可能留下`running`，当前没有租约、启动对账、崩溃恢复或多用户认证
- 当前没有HTTP Agent Run API、前端Run时间线或事件回放；未来即使增加展示回放，也只从已保存Event重建视图，不重放模型或工具副作用
- 后台异步执行与实时SSE属于条件重构：只有真实延迟/并发需要出现后才引入`202 + worker`、幂等领取和断线续传，不能用`async def`包装同步loop冒充后台任务
- 当前不做token逐字直通、Prompt A/B、后台恢复、Redis/S3、多页面或复杂UI

## Roadmap

1. ~~基于已验证的隔离COSINE/top-k契约，验证`app/rag`向量与chunk对齐，实现document级更新和删除收敛语义~~（Day40小样本完成）
2. ~~完成metadata filters和可测试的Retriever接口~~（Day41完成契约与fake路径；真实workspace schema迁移后置）
3. ~~将6题学习baseline扩展为12题探索性baseline，并补齐逐题状态、metadata、延迟和陌生Gate；第8周冻结总20题可信RAG baseline~~（Day42-Day46完成）；第11周扩展到总30～40题（50题上限）并增加holdout集
4. ~~修复真实表格embedding text/section，生成可回滚v2并完成同12题新旧对照~~（Day43完成）
5. ~~复用Retriever完成可测试的最小非流式RAG控制层与fake失败边界~~（Day44完成）
6. ~~增加稳定引用映射、引用校验、正式拒答与可信RAG API/SSE浏览器薄壳~~（单机原型完成）
7. ~~增加原生Function Calling、两个财报工具、有限受控loop、LangChain工具/message薄适配、Run/Event及独立12题Agent评测~~；已补充仅检索的 Agent runtime 内核装配及离线边界测试，后续实现用户结果与引用验证、结果持久化及 HTTP Run API。后台执行、崩溃恢复与实时事件仍为后续能力
8. 增加鉴权、多用户workspace隔离、生产基础设施、Docker和可观测性；React最薄单页已完成，复杂UI后置

只有经过代码、测试或可复现实验验证的能力，才会移动到“当前状态”中的可运行项。

## 数据与用途声明

- 仓库不包含年报 PDF、解析产物、向量数据库、模型文件或 API 密钥
- 本地实验仅使用公开披露文件，原始文件的使用应遵守其来源条款
- 本项目用于工程学习和信息检索研究，不构成投资建议
- 已完成一次真实模型可信问答与正常拒答 smoke，以及一次真实Function Calling计算工具smoke；输出与进程内fixture仍需按上述边界理解，不构成生产质量、自动审核或投资建议

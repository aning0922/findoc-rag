# FinDoc RAG

中文财报解析与可溯源向量检索原型。

> **项目状态：建设中。** Day44 已完成可测试的最小非流式 RAG 控制层，复用现有 Retriever，并用 fake 验证生成前空证据闸门、prompt 输入与检索/生成失败归属。
> 真实 LLM 接入、引用校验、正式拒答、RAG API、Agent 工作流、权限系统和 Web 界面尚未实现，本仓库暂不适合生产使用。

## 项目目标

FinDoc RAG 面向包含长文本和复杂表格的企业财报，探索一条可验证的 RAG 工程链路：

- 从 PDF 或 MinerU 输出中提取正文、标题、表格和页码
- 按中文文本特点进行分块，并保留来源元数据
- 使用 bge-m3 生成向量，写入 Milvus Lite
- 建立可重复的检索评测，记录 badcase、延迟和质量变化
- 在检索可靠后，再增加引用回答、拒答、工具调用和审核工作流

当前仓库只覆盖这条路线的前半段，不把规划中的能力描述为已经完成。

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
| RAG 控制层 | Day44 fake链通过 | `retrieve → 空证据evidence gate → 最小prompt → LLMClient → RAGResult`；检索失败、空证据和生成超时有独立异常与fake调用次数证据 |
| RAG API / Agent / Web | 计划中 | 尚无真实模型全链或可运行网络入口 |

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
        ├─离线评测分支→ Hit@K / MRR
        └─Day44控制分支→ 最小空证据evidence gate
                              ↓
                    问题 + SearchHit.text → 最小prompt
                              ↓
                    LLMClient（仅fake验证）→ 未引用校验的RAGResult
```

目前生产数据链到检索结果已有真实本地证据；Day44后续控制链仅用fake验证调用顺序和错误边界，还没有真实模型问答、引用校验或正式无证据拒答。
MinerU 解析过程目前由仓库外部执行，本仓库只读取其 `content_list.json` 输出。

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
- FlagEmbedding bge-m3
- Milvus Lite
- pytest
- OpenAI Python SDK（调用 DeepSeek 兼容接口）

FastAPI、LangChain Agent、LangGraph、PostgreSQL、React 和 Docker Compose 属于后续路线，不是当前已实现技术栈。

## 快速开始

### 1. 安装依赖

需要先安装 [uv](https://docs.astral.sh/uv/)。

```bash
git clone https://github.com/aning0922/findoc-rag.git
cd findoc-rag
uv sync
```

依赖包含文档解析和本地 Embedding 组件，首次安装及首次下载 bge-m3 可能耗时较长。

### 2. 运行解析 smoke test

这个测试会临时生成一份小型 PDF，不需要下载年报：

```bash
uv run pytest tests/test_parse.py -q
```

完整契约测试可以通过以下命令查看：

```bash
uv run pytest -q
```

当前基线为`190 passed`。`uv run ruff check app experiments tests scripts`、`uv run mypy app`、Day44测试文件以及8个Day43实验模块的mypy检查通过。测试全绿只表示已覆盖的行为符合契约，不替代真实检索评测、模型答案或事实正确性。

### 3. 运行可选的 LLM 示例

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
│   └── service.py      # Day44最小非流式RAG控制层与LLM边界
├── api/                # 预留，尚未实现
├── gateway/            # 预留，尚未实现
└── agent/              # 预留，尚未实现
scripts/                # 解析、分块、Embedding 和 Milvus 实验脚本
experiments/            # 分块、标准库向量检索与bge-m3小规模对照
tests/                  # smoke test、契约测试与理解Gate测试
doc/                    # 解析器、分块与向量检索决策记录
data/                   # 本地 PDF、JSONL 和 Milvus 数据，不提交
eval/                   # Day41/42 baseline、Day43 legacy/v2对照与Day44评测题草稿
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
- 当前仍只有12题探索性对照；第8周P0扩展到总20题，第11周扩展到30～50题并增加未参与调试的holdout集；7,451/5,269行都只是本地规模，不是质量指标
- legacy表格embedding text退化缺陷作为历史事实保留；v2已让标题、表头和表体进入检索text，但Q3/Q4/Q7/Q8/Q11仍未进入Top 5，后续必须另做受控检索诊断
- 当前只有fake LLM验证的最小非流式生成控制链；没有真实模型全链、引用验证、正式拒答、RAG API、鉴权或多用户隔离
- 没有可直接使用的 Web 产品界面

## Roadmap

1. ~~基于已验证的隔离COSINE/top-k契约，验证`app/rag`向量与chunk对齐，实现document级更新和删除收敛语义~~（Day40小样本完成）
2. ~~完成metadata filters和可测试的Retriever接口~~（Day41完成契约与fake路径；真实workspace schema迁移后置）
3. ~~将6题学习baseline扩展为12题探索性baseline，并补齐逐题状态、metadata、延迟和陌生Gate~~（Day42完成）；第8周扩展到总20题P0、25题目标，第11周扩展到30～50题并增加holdout集
4. ~~修复真实表格embedding text/section，生成可回滚v2并完成同12题新旧对照~~（Day43完成）
5. ~~复用Retriever完成可测试的最小非流式RAG控制层与fake失败边界~~（Day44完成）
6. 增加稳定引用映射、引用校验、正式拒答与RAG API
7. 增加Function Calling、可恢复工作流和人工审核
8. 增加鉴权、workspace隔离、React界面、Docker和可观测性

只有经过代码、测试或可复现实验验证的能力，才会移动到“当前状态”中的可运行项。

## 数据与用途声明

- 仓库不包含年报 PDF、解析产物、向量数据库、模型文件或 API 密钥
- 本地实验仅使用公开披露文件，原始文件的使用应遵守其来源条款
- 本项目用于工程学习和信息检索研究，不构成投资建议
- 真实模型生成式回答、引用校验和自动审核尚未实现；未来版本的输出仍需人工核验

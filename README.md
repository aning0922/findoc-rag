# FinDoc RAG

中文财报解析与可溯源向量检索原型。

> **项目状态：建设中。** 当前重点是解析契约、稳定分块 ID、幂等入库和检索评测。
> API、答案生成、Agent 工作流、权限系统和 Web 界面尚未实现，本仓库暂不适合生产使用。

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
| MinerU 输出适配 | 契约测试通过 | 多级标题、section、顺序、表格正文、页码与异常输入已有成功/失败测试；仍依赖上游`content_list.json`质量 |
| 中文分块 | 第6周理解Gate通过 | 中文分隔符+token计数、metadata复制、表格双表示与稳定ID已有测试；参数最优性待查询级评测 |
| Embedding | 本地实验已跑通 | bge-m3，dense vector维度为1024；Day39用5条候选和1条查询完成脱离Milvus的观察性黑盒对照 |
| Milvus Lite | 本地实验已跑通 | 3 份公开年报、7,451 个块已完成本地入库；原始数据和数据库不提交 |
| Retriever | 当前实现baseline | Day39已在隔离实验中验证标准库COSINE/稳定top-k契约；`app/rag`仍只有dense top-k，filters、幂等更新和正式评测尚未完成 |
| RAG API / Agent / Web | 计划中 | 尚无可运行实现 |

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
bge-m3 dense embedding
        ↓
Milvus Lite
        ↓
dense top-k retrieval
```

目前链路终点是检索结果，还没有生成式回答、引用校验或无证据拒答。
MinerU 解析过程目前由仓库外部执行，本仓库只读取其 `content_list.json` 输出。

Day39另外使用Python标准库完成了一条隔离的`query vector → COSINE → 稳定排序 → top-k`链路，并用bge-m3做了5条候选和1条查询的小规模黑盒对照，未使用Milvus或7,451块数据。契约、预测误差和职责边界见[Day39向量检索决策记录](doc/vector_retrieval.md)。

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

当前基线为`99 passed`，其中40个为Day39标准库检索与独立Gate测试。测试全绿只表示已覆盖的行为符合契约,不替代真实检索评测或事实正确性。

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
│   ├── store.py        # Milvus Lite 建库、写入和搜索
│   └── retriever.py    # 最小 dense retriever
├── api/                # 预留，尚未实现
├── gateway/            # 预留，尚未实现
└── agent/              # 预留，尚未实现
scripts/                # 解析、分块、Embedding 和 Milvus 实验脚本
experiments/            # 分块、标准库向量检索与bge-m3小规模对照
tests/                  # smoke test、契约测试与理解Gate测试
doc/                    # 解析器、分块与向量检索决策记录
data/                   # 本地 PDF、JSONL 和 Milvus 数据，不提交
eval/                   # 预留，正式评测尚未建立
```

当前 `scripts/` 中部分脚本仍使用作者的本地文件名，尚未整理成统一的端到端 CLI。

## 已知限制

- fast解析会跳过扫描页,不识别标题层级,且正文与表格分别收集后再拼接,不能保证原始元素顺序
- MinerU adapter会按上游`text_level`生成section;若上游把复选框等正文误判为标题,adapter无法自行恢复真实层级
- 当前`400/60`只是实现基线;Day38单样本中`400/10`与`400/60`输出相同,最优参数待查询级检索评测
- 表格当前保持原子块,可能超过配置size;完全重复正文缺少真实来源定位时仍有身份歧义
- 入库脚本尚未实现可靠的幂等更新和删除语义
- 当前只有 dense retrieval，没有 metadata filters、hybrid search 或 rerank
- Day39只验证了5条候选的精确COSINE/top-k链路；尚未验证`app/rag`向量与chunk对齐、幂等性或大规模检索质量
- 向量相似度只表示当前向量空间中的接近程度，不验证公司、指标、数值或其他事实是否正确
- 尚未建立公开评测集，7,451 个块只是本地入库规模，不是质量指标
- 没有 RAG 答案生成、引用验证、拒答、API、鉴权或多用户隔离
- 没有可直接使用的 Web 产品界面

## Roadmap

1. 基于已验证的隔离COSINE/top-k契约，验证`app/rag`向量与chunk对齐,实现幂等更新和删除语义
2. 完成metadata filters和可测试的Retriever接口
3. 建立20～30条基础评测集,记录Hit@K、MRR和P95,再决定分块参数
4. 增加带页码引用和无证据拒答的RAG API
5. 增加Function Calling、可恢复工作流和人工审核
6. 增加鉴权、workspace隔离、React界面、Docker和可观测性

只有经过代码、测试或可复现实验验证的能力，才会移动到“当前状态”中的可运行项。

## 数据与用途声明

- 仓库不包含年报 PDF、解析产物、向量数据库、模型文件或 API 密钥
- 本地实验仅使用公开披露文件，原始文件的使用应遵守其来源条款
- 本项目用于工程学习和信息检索研究，不构成投资建议
- 生成式回答和自动审核尚未实现；未来版本的输出仍需人工核验

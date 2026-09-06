# v0.1.0 发布证据

## 发布身份

- 发布定位：可信财报 RAG MVP。
- 可见产品链：上传 → 解析/分块/索引 → 问答 → 引用或拒答。
- Agent 边界：原生受控 loop、两个财报工具、LangChain Core 薄适配、Run/Event 和冻结 12 题结果属于离线后端实验能力；尚未接入 HTTP 产品入口或前端面板。
- 首次远端验证基线：`befcb6cbde7b661f3b552989335d679a8983aea4`。
- `v0.1.0` candidate SHA 尚未冻结；最终身份以后续 candidate commit 与 tag target 为准，不在同一提交中自引用。

## 首次远端 clean clone

执行日期：2026-09-03。使用 `mktemp -d` 创建全新临时目录，并从公开远端执行 `git clone --depth 1`；未复制作者工作区的 `.env`、`data/`、`.venv`、模型、Milvus 数据库或缓存。

环境身份：

```text
commit: befcb6cbde7b661f3b552989335d679a8983aea4
Python 3.12.13
uv 0.11.25
Node v24.19.0
npm 11.17.0
```

首次命令与真实结果：

```text
uv sync --frozen
成功：按锁文件安装 175 个包。

uv run pytest tests/test_parse.py -q
1 passed, 5 warnings in 2.59s

uv run pytest -q
1 failed, 329 passed, 5 warnings in 117.00s

FAILED tests/test_trusted_rag_questions.py::test_trusted_rag_question_set_preserves_frozen_cases_and_validates_new_evidence
tests/test_trusted_rag_questions.py:40: AssertionError
chunk_paths = sorted(V2_CHUNK_DIR.glob("*_chunks.jsonl"))
assert chunk_paths
E assert []
```

失败结论：默认全量测试在公开 clone 中读取未提交的 `data/day43_data_v2/*_chunks.jsonl`，因此作者本机旧证据“330 passed”不能作为 clean-clone 证据。

Node 说明：非交互 shell 第一次未加载 nvm，`nvm use 24` 不可用并显示 Node `v20.20.1`；加载本机已有 nvm 后切换到 Node `v24.19.0`，再执行前端验证。Node 20 的环境失败不记为前端业务回归。

```text
npm --prefix frontend ci
成功：按锁文件安装 28 个包；审计报告 0 vulnerabilities。

npm --prefix frontend test
6 passed, 0 failed, 0 skipped

npm --prefix frontend run build
成功：TypeScript 与 Vite production build 通过。

npm --prefix frontend run lint
成功：oxlint 通过。
```

默认测试数据边界修复后的作者工作区验证：

```text
uv run pytest tests/test_trusted_rag_questions.py -q -rs
2 passed in 0.66s

uv run pytest tests/test_trusted_rag_questions.py -q -m local_data -rs
1 passed, 1 deselected in 0.39s

uv run pytest -q
331 passed, 5 warnings in 16.07s

uv run ruff check .
All checks passed!

uv run mypy app
Success: no issues found in 45 source files

git diff --check
通过，无输出。
```

上述 `331 passed` 使用作者本地冻结数据，只证明修改后默认全量在当前作者环境通过；它不是修复后 candidate 的隔离证据。candidate 的无私有数据复测单独记录如下。

提交后隔离 candidate 复测：

```text
来源：从本地已提交Git对象执行 --no-local --depth 1 隔离克隆；不是远端复测。
commit: e7d0176f04f353b58990747ce35511b6fe3ff2b9
工作树：干净
data/day43_data_v2：不存在

uv sync --frozen
成功：按锁文件安装 175 个包。

uv run pytest tests/test_trusted_rag_questions.py -q -rs
1 passed, 1 skipped in 11.61s
skip原因明确给出缺失目录和 -m local_data 显式运行命令。

uv run pytest -q
330 passed, 1 skipped, 5 warnings in 48.66s
```

该结果证明 `e7d0176` 的已提交文件在没有作者私有 chunks 时可以完成默认后端测试，并保留可见的本地数据核验 skip；它不替代 Day59 的真正远端 candidate 复核。

本地数据交叉核验的前置条件与显式入口：

```text
前置条件：作者本地存在完整 data/day43_data_v2。
命令：uv run pytest tests/test_trusted_rag_questions.py -q -m local_data -rs
缺少整个目录：测试显示带原因的 skip。
目录存在但为空、chunk 损坏、证据 ID 缺失或 metadata 漂移：测试失败，不得 skip。
```

配置启动风险检查结论：

```text
实际必需配置：LLM_API_KEY、LLM_MODEL、LLM_BASE_URL、LLM_TIMEOUT_SECONDS。
原风险顺序：BGE warmup → SQLite repository / object store → Milvus client 与 collection → 读取 LLM 配置。
修复后顺序：读取并校验 LLM 配置 → BGE warmup → SQLite repository / object store → Milvus client 与 collection。
配置实现：`cf2610b8dd265b85054562d89b74f3de0f18782a`；已验证的同一 LLM client 注入 RAG 资源，不再在 Milvus 创建后重复读取环境。
自动证据：缺少 LLM_API_KEY 时调用记录严格为 `["config"]`；临时 runtime 下 `documents.db`、`objects` 和 `milvus.db` 均不存在。本人定向测试为1 passed，组合配置定向测试为6 passed；Ruff、`mypy app`与diff检查通过。
剩余边界：`app.api.main`仍采用模块导入即装配；本次只覆盖代表性缺配置路径，不扩成统一Settings平台。
```

## 三层验证边界

| 层级 | 输入与依赖 | 可以证明 | 不能证明 |
|---|---|---|---|
| clean-clone 默认验证 | 仅公开远端 tracked files；无 `.env`、私有 PDF、作者 chunks、Milvus DB 或模型缓存 | 锁文件安装合同、公开离线单测/契约测试、前端测试与构建可复现 | 真实 RAG 质量、真实模型调用、本地 5,269 行数据或 runtime Demo 可复跑 |
| 作者本地 integration/eval | 冻结 PDF 派生数据、manifest、Milvus collection、模型与密钥 | 指定数据和配置上的检索、RAG、Agent 历史结果及题集—chunks 交叉核验 | 新用户仅 clone 即可复跑；结果可外推到任意财报或任意模型 |
| runtime Demo | 有效 LLM 配置、bge-m3、本地 runtime 库和可分发合成 PDF | 上传 → ready → 回答/引用 → 拒答的可见产品链 | 生产部署、在线 Demo、认证、多用户隔离或可靠后台任务 |

## Holdout 冻结身份与首次入口失败

冻结身份：

```text
代码 candidate commit: cf2610b8dd265b85054562d89b74f3de0f18782a
题集封存 commit: 3e1aea832b0580e6e1b18184de53e7ddd2b54a1f
runner: scripts/evaluate_trusted_rag.py
runner SHA-256: e445a43ff1e5f0846174f41515d4cb7b8a0606ef55b3e3db742f6f6238997665
描述性 baseline config SHA-256: 7c1361987141a4178c53ffbc6f2b8b580fa72a497043ccc46bcc800e0bcb5e09
data manifest SHA-256: 06bba7db22db4ea7cde485b1695be624ba7aaf91f3150562b5044390af008e59
suite SHA-256: 2ffde40665008b5dc0af99de5118b702be2500e7ffddaf9890d0d2492e3bd507
holdout manifest SHA-256: 7c2b0b4aecf5ed43118f17768b676671dece4433ee5a551c38cab86be060ae06
数据身份: day43_data_v2 / demo-financial-reports / data/milvus.db
collection: findoc_day43_v2 / 5,269 rows / COSINE
embedding: BAAI/bge-m3 / 1,024 dimensions
实际参数: top_k=5 / min_top_score=0.55 / max_evidence_chars=4000
Prompt版本: trusted-rag-json-v1
LLM: deepseek-v4-flash / https://api.deepseek.com / timeout=30s
密钥: 仅确认运行环境中存在；未读取或保存内容
```

题集包含恰好 5 题，聚合分布为 3 条可回答、2 条不可回答。正式运行前只核对
manifest 摘要、schema、数量和 SHA-256，不打开题集正文；这是程序性封存，
不是访问控制意义上的物理隔离。

2026-09-05 首次使用计划中的文件路径入口启动：

```text
uv run python scripts/evaluate_trusted_rag.py \
  --questions eval/trusted_rag_holdout_v1.jsonl \
  --output eval/trusted_rag_holdout_result_cff75a4b-d202-438c-ac40-5c7957c88a08.json

退出状态: 失败
错误: ModuleNotFoundError: No module named 'app'
失败位置: scripts/evaluate_trusted_rag.py 第16行模块导入
main()是否进入: 否
题集是否加载: 否
case开始数: 0
Milvus与模型是否调用: 否
结果文件是否产生: 否
```

根因是文件路径入口把 `scripts/` 作为模块搜索起点，无法解析仓库根目录下的
`app` 包；已有 baseline config 记录的执行入口为
`python -m scripts.evaluate_trusted_rag`。原冻结规则只明确允许 API 或数据库初始化
故障后的唯一重试，没有覆盖 `main()` 之前的入口命令失败。由于本次未加载题集、
未进入任何 case、未调用模型且未产生结果，人工决定透明记录该规则偏差，并只允许
一次模块入口修正；不得借此修改代码、题集、Prompt、阈值、模型或数据。

唯一入口修正身份：

```text
run-id: 1d6b709d-d91d-4398-a2e1-58c45565466c
output: eval/trusted_rag_holdout_result_1d6b709d-d91d-4398-a2e1-58c45565466c.json
入口: uv run python -m scripts.evaluate_trusted_rag
后续启动上限: 1
```

唯一入口修正运行已于 2026-09-05 完成，未再次运行：

```text
执行HEAD: f75398afff586f950a405c8a30ba07753324e17b
运行时工作树: clean
run-id: 1d6b709d-d91d-4398-a2e1-58c45565466c
result: eval/trusted_rag_holdout_result_1d6b709d-d91d-4398-a2e1-58c45565466c.json
result SHA-256: b3a18ff6920664fac5eb018da10db274a58346ec49d07623376201521355717b
题集SHA-256: 2ffde40665008b5dc0af99de5118b702be2500e7ffddaf9890d0d2492e3bd507
数据manifest SHA-256: 06bba7db22db4ea7cde485b1695be624ba7aaf91f3150562b5044390af008e59
结果数: 5
终态分布: answered=3 / refusal=2 / system_error=0
预期可回答题分母: 3；终态answered=3 / refusal=0
预期不可回答题分母: 2；终态refusal=2 / answered=0
协议级有效引用终态: 3
受控入口修正: 1次
修正后额外运行: 0次
```

以上只完成原始结果的存在性、唯一命名、分母、终态、system error 和身份完整性
检查。`answered` 不等于事实正确，协议级引用有效只表示引用编号可以映射到本次检索
证据，不表示证据一定支持答案；逐题事实与引用核对留到开封评分阶段。5 题从本次运行
起已成为揭示的一次性 release smoke，不再称为未见 holdout，也不用于运行后调参重跑。


## 固定五题事实、引用支持与拒答核对

核对日期：2026-09-05。沿用唯一结果 `1d6b709d-d91d-4398-a2e1-58c45565466c`；结果 SHA-256 为 `b3a18ff6920664fac5eb018da10db274a58346ec49d07623376201521355717b`。本节为既有结果的人工核对，不是新运行。题集、manifest、原始结果、runner、模型、阈值和代码均未变更，未重跑评测。

题集：[trusted_rag_holdout_v1.jsonl](../eval/trusted_rag_holdout_v1.jsonl)；原始回答、引用与检索片段：[固定结果](../eval/trusted_rag_holdout_result_1d6b709d-d91d-4398-a2e1-58c45565466c.json)。以下按 `case_id` 定位。三份冻结文本文件的 SHA-256 与数据 manifest 一致；三条可答题均人工核对了源 PDF 对应页。

| case_id | 原终态 | 人工结论 | 可追溯依据 |
|---|---|---|---|
| H56-001 | answered | 事实正确且引用支持 | 现金分红18.7亿元、占归母净利润35%，主体和2024年度口径一致；引用[1]对应京东方2025年报第3页“致股东”，chunk `ef5c2dd5ba538422359b0546766f5c0448f8719b7432dc3c4f5e18d2abcdc98c`。冻结文本第11行与结果引用片段一致，源PDF人工核对一致。 |
| H56-002 | answered | 事实正确且引用支持 | 每10股拟派发人民币0.49元（含税），保留“拟派发”状态；引用[1]对应成都华微2025年报第53页，chunk `d9e4e1ae682f5b5b4b06de210d7f603b10799acb7580a5c211375c69cade3aec`；引用[3]对应第2页，chunk `e3a03e13bace22318a0ad6f4e3e50834cd7a538bddd6eca35f389ef127c5f310`。两处均有原文支持，源PDF两页人工核对一致。 |
| H56-003 | answered | 事实正确且引用支持 | 年报审计费用35万元、内控审计费用15万元，费用名称和金额分别对应；引用[3]指向成都华微2025年报第75页，chunk `5b5704429464ef770452996e96157fcdf45af0cf30945e7e3c20f1853eb20947`。该段支持两项结论，源PDF人工核对一致。 |
| H56-004 | refusal | 正确拒答 | 实际检索结果为财务标题、环境披露名单及外部报告索引等，不能给出各公司范围一、范围二排放总量。对三份冻结文本共5269个片段定向核查相关中文及Scope 1/2表述，未找到所需披露；相关低碳叙述也无所需总量。模型仅返回拒答，未编造数值。结论限于冻结数据，不能推出外部ESG报告未披露。 |
| H56-005 | refusal | 正确拒答 | 实际检索结果未包含员工平均年龄。限定成都华微全部2436个冻结片段补查：第50页为全体在职员工990人及专业/学历构成；第27页为研发人员年龄分段。研发人员不能代表全体员工，分段人数也不能确定精确平均年龄。未找到全体在职员工平均年龄披露，模型仅返回拒答，未编造数值。 |

汇总：**事实正确且引用支持3/3；正确拒答2/2；system error 0/5。** 五题中未确认评分失败的badcase，不为凑数量列失败。协议级引用有效与原文语义支持分别核对；成功终态本身不证明事实正确。两条拒答的结论限定于冻结文本和本次证据，定向搜索不是对所有原始页面、其他措辞或外部材料不存在答案的穷尽证明；补查片段也不冒充模型当时检索所得。上述仅为该固定配置下五题release smoke的逐题观察，不推导泛化准确率。

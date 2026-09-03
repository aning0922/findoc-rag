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

上述 `331 passed` 使用作者本地冻结数据，只证明修改后默认全量在当前作者环境通过；它不是修复后 candidate 的 clean-clone 证据。candidate 隔离复测完成前，不宣称公开 clone 已通过默认全量。

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
当前初始化顺序：BGE warmup → SQLite repository / object store → Milvus client 与 collection → 读取 LLM 配置。
影响：缺少 LLM 配置时仍会先加载 BGE；若 warmup 成功，还会创建 data/runtime、documents.db、objects/ 与 Milvus 数据库/collection，随后才因配置失败。Milvus client 会在异常处理中关闭，但已创建的落盘状态不会回滚。
下一步：若今日不超过硬停止线，后续最小 fail-fast 必须由自动测试证明配置失败时 BGE warmup 未调用、Milvus client 未创建且 data/runtime 未产生半初始化状态；否则作为 Day56 第一块处理。
```

## 三层验证边界

| 层级 | 输入与依赖 | 可以证明 | 不能证明 |
|---|---|---|---|
| clean-clone 默认验证 | 仅公开远端 tracked files；无 `.env`、私有 PDF、作者 chunks、Milvus DB 或模型缓存 | 锁文件安装合同、公开离线单测/契约测试、前端测试与构建可复现 | 真实 RAG 质量、真实模型调用、本地 5,269 行数据或 runtime Demo 可复跑 |
| 作者本地 integration/eval | 冻结 PDF 派生数据、manifest、Milvus collection、模型与密钥 | 指定数据和配置上的检索、RAG、Agent 历史结果及题集—chunks 交叉核验 | 新用户仅 clone 即可复跑；结果可外推到任意财报或任意模型 |
| runtime Demo | 有效 LLM 配置、bge-m3、本地 runtime 库和可分发合成 PDF | 上传 → ready → 回答/引用 → 拒答的可见产品链 | 生产部署、在线 Demo、认证、多用户隔离或可靠后台任务 |

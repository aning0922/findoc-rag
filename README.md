# FinDoc Agent · 金融公告问答智能体(Agentic RAG)

> 基于 FastAPI + RAG + Function Calling 的金融年报可信问答系统:
> 向量检索 + 引用溯源 + 无证据拒答 + 工具调用(文档检索 / 财务指标计算)。
> 个人转型自建项目 · 2026-07 起 · 🚧 建设中(按 16 周计划推进,每周更新)

## 它解决什么工程问题
- 长文档(年报含大量表格)的解析、分块与**可溯源检索**
- RAG 召回质量:**混合检索(向量+BM25/RRF)+ rerank + 评测驱动优化**
- 生产可信:**引用溯源、无证据拒答、固定免责声明、防注入**
- 智能体编排:**Function Calling / LangGraph 工具调用**(文档检索 + 财务指标)+ 人审(HITL)
- 工程化:**LLM Gateway**(超时/重试/token 计费/可观测)、Docker 一键起

## 🚧 当前进度(Roadmap)
> 诚实标注:这是一个转型学习项目,以下按周推进,`README` 随进度更新。
- [x] 项目脚手架 + LLM 调用打通(DeepSeek/Qwen,openai 兼容 SDK;同步 / 流式 / 异步并发)
- [ ] **LLM Gateway**:FastAPI + SSE 流式 + 超时重试 + token 计数 + 结构化日志
- [ ] **文档解析入库**:PDF / 表格 → 中文分块 → embedding(bge-m3)→ Milvus
- [ ] **RAG 闭环**:向量检索 + 页码引用溯源 + 无证据拒答 + 评测集
- [ ] **Agent**:Function Calling 工具循环(文档检索 + 财务指标)+ HITL + 执行日志
- [ ] **检索增强**:混合检索(BM25/RRF)+ rerank + RAGAS 评测 + badcase 优化
- [ ] **工程化**:Docker Compose + 成本 / P95 延迟观测

## 技术栈
`Python` · `FastAPI` · `asyncio` · `RAG(向量/混合检索/rerank)` · `Milvus` ·
`LangChain / LangGraph` · `Function Calling` · `Prompt 工程` · `DeepSeek / Qwen` · `Docker`

## 目标架构
```
PDF(cninfo 年报) → 解析/表格/metadata → 中文分块 → embedding → 向量库(Milvus)
        → 混合检索(向量+BM25/RRF) → rerank → 拼上下文 → LLM 生成(带页码引用 / 无证据拒答)
[LLM Gateway: 多模型 / 超时重试 / token 计费 / 可观测]   [Agent: Function Calling / LangGraph 工具调用 + HITL]
```
> (开发到对应阶段后把真实架构图 / 截图贴这里)

## 关键指标(随开发填入真实数据)
| 指标 | 数值 |
|---|---|
| 召回率(优化前→后) | __% → __% |
| 答案忠实度(RAGAS) |  |
| P95 延迟 | __ ms |
| 单次问答成本 | __ |
| 评测集规模 | __ 条 |

## 本地运行
```bash
uv sync
cp .env.example .env          # 填 DEEPSEEK_API_KEY + LLM_MODEL
uv run python hello_llm.py    # ✅ 现在就能跑:LLM 同步 / 流式 / 异步并发 demo

# 以下随开发解锁:
# uvicorn app.gateway.main:app --reload   # LLM Gateway(第 4 周)
# docker compose up -d                      # Milvus 等中间件(第 15 周)
```

## 目录
- `app/gateway` LLM 网关 ｜ `app/rag` 解析/检索/重排 ｜ `app/agent` 工具调用 ｜ `app/api` FastAPI
- `data/` 年报 PDF(**.gitignore,不入库、不重分发**)｜ `eval/` 评测集与脚本 ｜ `scripts/` 灌库/重建索引 ｜ `tests/`

## 合规声明
仅基于公开披露文件,面向研究 / 合规 / 客服等内部信息检索场景。
**所有输出附"不构成投资建议"免责声明,不做荐股 / 预测 / 量化 / 投顾。**

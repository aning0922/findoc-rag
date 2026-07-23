# FinDoc Workflow Agent · 企业财报研究与审核工作流

> 目标:基于 FastAPI + 可信 RAG + Function Calling/LangGraph,把财报上传、检索、计算、草稿、校验、审批和审计串成可恢复业务流程。
> 个人转型自建项目 · 2026-07 起 · 🚧 建设中(按 16 周计划推进,每周更新)

## 它解决什么工程问题
- 长文档(年报含大量表格)的解析、分块与**可溯源检索**
- RAG 召回质量:向量 baseline → 混合检索/rerank 对照 → badcase 回归
- 生产可信:引用溯源、无证据拒答、权限隔离、HITL、失败恢复与审计
- 智能体编排:确定性工具 + LangGraph 状态工作流,不是让 LLM 随意执行全部步骤
- 工程化:Gateway、PostgreSQL、React 产品薄层、Docker、质量/延迟/token/成本

## 🚧 当前进度(Roadmap)
> 诚实标注:只把主仓里已有代码列为完成。`learning-lab/gateway` 的可运行 Gateway 是原型,第 8 周迁入本仓后才算主项目集成完成。
- [x] 项目脚手架 + LLM 调用打通(DeepSeek/Qwen,openai 兼容 SDK;同步 / 流式 / 异步并发)
- [x] **Gateway 原型**:`learning-lab/gateway` 已完成 FastAPI/SSE/超时重试/token/structlog;主仓集成待第 8 周
- [x] **文档底座**:PDF/表格 → 中文分块 → bge-m3 → 3 家 7451 块进入 Milvus Lite
- [ ] **Retriever Gate**:稳定 ID、幂等入库、filters、20-30 条题与 Hit@K/MRR/P95
- [ ] **RAG 产品闭环**:上传/状态/SSE 问答 + 页码引用 + 无证据拒答
- [ ] **Agent v0**:手写 Function Calling → LangChain 薄集成 + Run 时间线
- [ ] **质量/隔离**:hybrid/rerank 评测 + PostgreSQL/鉴权/workspace 隔离
- [ ] **Workflow**:LangGraph + checkpoint + HITL + 恢复/审计/系统集成
- [ ] **工程化**:Docker Compose + 全链路日志 + 成本/P95 + 故障演练

## 技术栈

**已实现:**`Python 3.12` · `Pydantic` · `pytest` · `pymupdf/pdfplumber/MinerU` · `bge-m3` · `Milvus Lite` · `DeepSeek/Qwen OpenAI 兼容 API`

**原型已实现、待主仓集成:**`FastAPI` · `asyncio` · `SSE` · `structlog`

**计划中(完成后再移到上面):**`React/TypeScript` · `LangChain` · `LangGraph` · `PostgreSQL/SQLAlchemy/Alembic` · `JWT/RBAC` · `Docker Compose`

## 目标架构
```
登录 → 上传/解析/索引 → 创建研究任务 → RAG 检索 / 财务计算
     → 生成草稿 → 引用与数字校验 → 自动通过或等待 reviewer 审批
     → 批准/驳回/恢复 → 保存结果与审计

[Gateway: SSE/超时/重试] [RAG: 引用/拒答/评测] [Workflow: 状态/checkpoint/HITL]
[可信度: workspace 隔离/工具权限/审计] [工程化: Docker/日志/P95/token/成本]
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

# 以下随开发解锁后再去掉注释:
# uvicorn app.api.main:app --reload       # 第 8 周主仓 API
# docker compose up -d                    # 第 15 周完整编排
```

## 目录
- `app/gateway` LLM 网关 ｜ `app/rag` 解析/检索/重排 ｜ `app/agent` 工具调用 ｜ `app/api` FastAPI
- `data/` 年报 PDF(**.gitignore,不入库、不重分发**)｜ `eval/` 评测集与脚本 ｜ `scripts/` 灌库/重建索引 ｜ `tests/`

## 合规声明
仅基于公开披露文件,面向研究 / 合规 / 客服等内部信息检索场景。
**所有输出附"不构成投资建议"免责声明,不做荐股 / 预测 / 量化 / 投顾。**

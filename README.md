# FinDoc RAG — 金融公告可信问答与风险分析平台

> 基于 FastAPI + 混合检索 + rerank + LLM 的金融文档 RAG 系统:年报/公告可溯源问答、财务指标核对、风险因素提取、无证据拒答、评测闭环。
> （个人项目 · 转型自建)

## 它解决什么工程问题
- 长文档(年报含大量表格)的解析、分块与可溯源检索
- RAG 召回质量:混合检索(向量+BM25)+ rerank + 评测驱动优化
- 生产可信:引用溯源、无证据拒答、固定免责声明、防注入
- 工程化:LLM Gateway(超时/重试/token 计费/可观测)、Docker 一键起

## 关键指标(填真实数据)
| 指标 | 数值 |
|---|---|
| 召回率(优化前→后) | __% → __% |
| 答案忠实度(RAGAS) |  |
| P95 延迟 | __ ms |
| 单次问答成本 | __ |
| 评测集规模 | __ 条 |

## 架构
```
PDF(cninfo 年报) → 解析/表格/metadata → 中文分块 → embedding → 向量库(Milvus)
            → 混合检索(向量+BM25/RRF) → rerank → 拼上下文 → LLM 生成(带页码引用 / 无证据拒答)
[LLM Gateway: 多模型 / 超时重试 / token 计费 / LangFuse]   [Agent: LangGraph 工具调用 + HITL]
```
> (开发到对应阶段后把真实架构图贴这里)

## 目录
- `app/gateway` LLM 网关 ｜ `app/rag` 解析/检索/重排 ｜ `app/agent` LangGraph 工具调用 ｜ `app/api` FastAPI
- `data/` 年报 PDF(**.gitignore,不入库、不重分发**)｜ `eval/` 评测集与脚本 ｜ `scripts/` 灌库/重建索引 ｜ `tests/`

## 本地运行
```bash
uv sync
cp .env.example .env   # 填 API Key
# docker compose up -d  # Milvus 等(待补)
# uvicorn app.api.main:app --reload
```

## 合规声明
仅基于公开披露文件,面向研究/合规/客服等内部信息检索场景,**输出附"不构成投资建议"免责声明,不做荐股/预测/量化/投顾**。

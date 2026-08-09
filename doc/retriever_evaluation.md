# Day41 Retriever 契约与六题检索基线

> 完成日期：2026-08-07 ｜ 起点 HEAD：`46d19f6` ｜ Gate：通过（L2）

## 本日范围

Day41 建立一个职责清晰、可测试、可评估的最小 Retriever 闭环：查询经注入的 embedder 生成向量，store 根据可信上下文和允许的业务过滤检索，Retriever 校验底层结果并转换成稳定的 `SearchHit`。本日只实现 dense retrieval、`workspace_id` 信任边界、`source_file` 业务过滤、Hit@K/MRR 和 6 题学习基线；不包含 RAG 生成、hybrid、rerank、RAGAS、完整权限系统或正式 20～30 题评测集。

## Retriever 契约

- 输入：非空 `query`、大于等于 1 且不能为 `bool` 的 `top_k`、服务端产生的 `TrustedContext`，以及可选的 `SearchFilters`。
- 依赖：embedder 和 store 通过构造函数注入，单元测试使用 fake，不重复加载真实模型。
- 输出：`list[SearchHit]`。DTO 固定暴露 score、chunk_id、text、page、source_file、type、section 和 table_md，隔离底层 store 的返回结构。
- 空结果：store 正常完成但没有候选时返回 `[]`。
- 非法输入：在调用 embedder/store 前抛出 `TypeError` 或 `ValueError`。
- 数据契约错误：embedder 未返回单个非空向量，或 store hit 缺少关键 metadata 时抛出 `RetrieverDataError`。
- 系统错误：Retriever 不把底层连接异常伪装成空结果；评测执行器按题捕获并记录为 `system_error`。
- 召回错误：系统正常返回候选，但人工标注的相关 chunk 未进入 Top K。该判断依赖评测标注，不属于 Retriever 自身异常。

## 过滤与信任边界

`workspace_id` 必须来自服务端认证后的 `TrustedContext`，用户请求不能覆盖它。用户只能通过白名单 DTO 提供当前允许的 `source_file`。构造器始终把可信 workspace 放入表达式，再追加允许的业务过滤。

当前真实 `findoc` collection 没有 `workspace_id` 字段，因此本日用 fake store 证明完整过滤契约和越权覆盖防护；真实 Milvus 只验证 schema 已支持的 `source_file`。这不是完整多租户权限系统。

## 指标定义

- Hit@K：每道可回答题的 Top K 中只要存在至少一个相关 chunk 就记 1，否则记 0；数据集指标取平均。
- RR：第一条相关结果位于第 `rank` 名时为 `1 / rank`，没有命中时为 0。
- MRR：所有可回答题 RR 的平均值，同时反映是否命中和首次命中的排序位置。

## 六题真实基线

运行命令：

```bash
uv run python -m scripts.evaluate_day41_retrieval
```

结果文件：`eval/day41_baseline.json`。模型加载约 8.62 秒，六题平均单题检索延迟约 291.38 ms。

| 题目 | 类别 | 状态 | 相关结果 rank | 延迟 |
|---|---|---|---:|---:|
| Q1 贵州茅台主要业务 | 普通文本 | normal | 1 | 724.62 ms |
| Q2 成都华微主要业务 | 普通文本 | normal | 2 | 283.79 ms |
| Q3 贵州茅台基本每股收益 | 表格/精确数字 | recall_error | — | 289.80 ms |
| Q4 京东方营业收入 | source_file 过滤/表格 | recall_error | — | 243.00 ms |
| Q5 量子计算机无关问题 | 无答案 | normal | — | 176.83 ms |
| Q6 成都华微现金流变化原因 | 易错问题 | recall_error | — | 30.24 ms |

5 道可回答题的指标：Hit@1 = 0.2，Hit@5 = 0.4，MRR = 0.3。六题均无系统错误；Q4 的 `source_file` 过滤正确生效。

## Badcase

1. Q3 的正确表格在 `table_md` 中包含“基本每股收益 65.66 元/股”，但参与 embedding 的 `text` 只有“第6页表格”，因此正确 chunk 未进入 Top 5。
2. Q4 的 Top 5 全部来自过滤后的京东方年报，证明过滤成功；但候选文本只有“2025年”等弱语义内容，正确的第12页表格未进入 Top 5，属于过滤后的召回错误。

## 验证与结论

- 全量 pytest：`141 passed`，较 Day40 增加 29 个 Day41 测试。
- `uv run ruff check .`：通过。
- `uv run mypy app`：通过，17 个源文件无问题。
- 单一 Gate：用户请求尝试传入 `WS-B`，服务端仍使用可信 `WS-A` 并组合 `source_file="已归档.pdf"`；合法过滤未命中时返回空列表。实现和口述均通过。
- 精确记录的 Day41 C～F 有效用时为 6 小时 26 分 05 秒；A、B 在前一日完成但未计时，不虚构总时长。

Day41 的 P0 为零，达到 L2，可以进入 Day42。Day41 结束时曾计划立即扩展到 20～30 题；Day42 的时间盒验收方案随后调整为 12 题 P0、第8周约25题、第11周30～50题并增加 holdout。真实 workspace schema 迁移、表格 embedding 文本修复、完整权限系统和历史实验文件 mypy 债务仍保留为后续项。

## Day42 联合验收追记

> 完成日期：2026-08-08～09 ｜ 起点 HEAD：`6cf9fc7` ｜ Gate：通过

Day42 不重写 Day35～41 实现，只补充可信评测集设计、12题冻结baseline和一个陌生端到端迁移Gate。问题必须从源PDF和原始chunk建立ground truth，不能根据本次Top 5事后选择相关ID；Hit@K和MRR只计算10道可回答题，2道无答案题不冒充拒答准确率。

运行命令：

```bash
uv run python -m scripts.evaluate_day42_retrieval
```

冻结范围为`legacy_7451_day41`数据、`BAAI/bge-m3`、`findoc` collection、7,451 rows、`top_k=5`和COSINE。模型加载约`7870.12 ms`，另做一次约`680.04 ms`的warm-up；12个非系统错误样本的探索性P50/P95为`54.44/194.75 ms`，不作为生产性能结论。

| 样本 | 数量或结果 |
|---|---:|
| 总题数 | 12 |
| 可回答题 / 无答案题 | 10 / 2 |
| Hit@1 | 0.20 |
| Hit@5 | 0.40 |
| MRR | 0.27 |
| normal / recall_error | 6 / 6 |
| metadata passed / failed | 3 / 1 |

唯一深入分析的Q8询问京东方显示器件业务收入占比。源PDF第19页和相关chunk的`table_md`均包含`81.34%`，但旧chunk的检索`text`只有“第19页表格”，相关ID没有进入Top 5。最早故障层是旧流程的chunk/embedding-text构造，不是parser、filter、ground-truth或Prompt；当天冻结并保留结果，没有调参、修改Retriever或重灌旧collection。

陌生Gate使用两级标题、正文、表格、同document V1/V2、两个workspace/source上下文、5维deterministic embedder和pytest临时Milvus，实际经过adapter、chunk、stable ID、rows对齐、document替换、Retriever、可信过滤和指标。相同版本重跑最终状态不变；正文修改后旧ID消失，未修改表格ID保持；用户提交的`WS-BETA`不能覆盖可信`WS-ALPHA`；三条查询均rank 1，Gate Hit@1、Hit@3和MRR均为1.0。该结果证明小型工程链路迁移正确，不证明真实模型语义质量或生产性能。

最终验证：Day42定向测试`13 passed`，全量pytest`154 passed`，Ruff通过，`mypy app`对17个源文件无问题。两天主动学习约10～11小时。Day42 P0为零，允许进入Day43；Day43/第8周首先检查并修复旧表格embedding text与legacy section数据问题，保留旧baseline并生成版本化对照，不覆盖历史报告。

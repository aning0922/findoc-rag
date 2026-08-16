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

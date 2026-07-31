# 分块决策(FinDoc)

> Day38证据更新:2026-08-01 ｜ 生产HEAD:`66592e4` ｜ 当前实现保持不变,参数优劣尚未经过查询级检索评测

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
- Day38没有查询、相关性标签、embedding或向量检索结果。**400/60暂时保留为当前基线,最优配置待Day41查询级检索评测验证。**

## 已知边界

- 完全重复正文目前只用同payload组内出现序号区分;缺少adapter提供的真实稳定来源定位时,不能证明重复块各自对应哪个物理位置。
- `duplicate_chars`实验字段实际统计非空白原文位置的重复覆盖;覆盖率1.0与重复0都不能证明边界自然。
- 当前分层抽查规则在运行前固定,但配置对审核者可见,因此不是匿名盲评。

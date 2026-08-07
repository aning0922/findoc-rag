# 向量摄取与文档生命周期决策（FinDoc）

> Day40证据更新：2026-08-06 ｜ 实现提交：`46d19f6` ｜ 未运行或修改现有7,451块Milvus数据

## 本日目标与范围

Day40用fake embedder、二维向量、pytest临时Milvus Lite和独立collection验证以下链路始终保持身份对齐：

```text
合法chunk
→ embedding text
→ vector
→ aligned row
→ Milvus row
```

本日只实现一种document级策略：按`document_id`删除旧rows，再写入当前完整版本。没有同时实现stable-ID upsert，也没有扩展Retriever、ANN、hybrid、rerank或查询级评测。

## 摄取输入契约与对齐不变量

- `text`缺失、为`None`或不是字符串时，整批在embedding前失败。
- `text == ""`或`text.strip() == ""`时跳过该chunk。
- 非空合法chunk必须具有非空字符串`chunk_id`。
- `legal_chunks`是唯一合法列表；embedding texts与row组装都从它派生。
- embedder返回后，必须先检查`len(vectors) == len(legal_chunks)`，再执行`zip`；数量不一致立即抛出`ValueError`，不返回部分rows。
- 每个row复制原chunk身份与metadata，并只增加对应vector；原始chunk不被原地修改。

端到端测试进一步从Milvus查询实际row，证明`I1/I3`的text、page、source、section、type、table payload和vector仍与各自原始合法chunk一致，空白`I-WS`未进入数据库。

## document身份与主键

- `document_id`由调用者提供，表示跨版本不变的逻辑文档身份；它不是内容hash，也不是输入顺序。
- Day40独立collection使用字符串`chunk_id`作为Milvus主键，不使用位置整数ID。
- 一次替换只删除满足目标`document_id`过滤条件的rows，其他document保留在同一collection中且不受影响。
- 本批新rows的`chunk_id`必须是非空且互不重复的字符串。

stable ID只保证相同身份规则与输入得到相同ID；它不保证数据库使用该ID执行upsert，也不清理新版中消失的旧ID，因此stable ID本身不等于document级幂等。

## 选择的生命周期策略

实现顺序为：

```text
验证document_id与本批chunk_id
→ 从完整新版本得到expected_ids
→ 查询目标document旧ID集合
→ 只删除目标document的旧rows
→ 插入完整新rows（空列表表示删除整份document）
→ 查询实际ID集合和行数
→ actual_ids必须等于expected_ids
→ 对old_ids - expected_ids执行主键精确不存在检查
```

计数采用物理操作语义：`inserted`等于本次完整新版本row数，`updated=0`，`skipped=0`。因此完全相同的重复摄取仍会重写rows，但最终逻辑状态不增加脏数据。

## 生命周期真值表

以对照文档`D-B={B1}`和目标文档`D-A`为例：

| 操作 | D-A完整新版本 | inserted | collection最终总行数 | D-A最终集合 | 必须不存在 |
|---|---|---:|---:|---|---|
| 首次摄取 | `{A1,A2}` | 2 | 3 | `{A1,A2}` | 无 |
| 完全重复 | `{A1,A2}` | 2 | 3 | `{A1,A2}` | 无重复row |
| 换序输入 | `[A2,A1]` | 2 | 3 | `{A1,A2}` | 无额外ID |
| 修改内容 | `{A1,A3}` | 2 | 3 | `{A1,A3}` | `A2` |
| 删除一个chunk | `{A3}` | 1 | 2 | `{A3}` | `A1` |
| 删除整份document | `{}` | 0 | 1 | `{}` | `A3` |

所有步骤中`D-B`始终为`{B1}`。证明没有ghost不能只看总数，还必须比较目标document实际ID集合、实际row数，并用主键精确查询被淘汰的旧ID。更新后的向量搜索也必须实际命中新row，同时不再返回旧ID或旧正文。

## 中途失败记录

删除与插入之间没有事务。故障注入让新版本只写入`A1`后抛出异常，观察到：

```text
故障后：D-A={A1}，D-B={B1}，A2/A3不存在，总行数2
再次完整运行后：D-A={A1,A3}，D-B={B1}，A2不存在，总行数3
```

这证明当前策略可以在再次提交完整版本时收敛，但不证明首次运行具有原子性。

## 自动检查与Gate证据

- Day40定向测试：`13 passed`。
- 完整回归：`112 passed`，原99个测试无回归。
- `uv run ruff check .`通过。
- `uv run mypy app`通过：15个生产代码文件无类型错误。
- COSINE搜索测试锁定score越大越相似，并验证完整metadata绑定。
- 陌生数量故障在embedder返回后、row组装前fail-fast。
- 陌生document迁移覆盖首次、重复、换序、修改和删除，旧`N9/N7`精确不存在，对照`D-ANCHOR={K4}`保持不变。
- 行为、量化、口述和陌生迁移证据均达到3级。
- 预测错误包括：曾把document误说成独立表、将stable ID与幂等混淆、重跑总数与换序集合出现笔误；均在最终陌生迁移前纠正。
- 最终P0为零，允许进入Day41；实际用时跨2026-08-05至08-06约12小时44分（8小时35分+4小时09分，午饭/午休不计），超过原6-8小时目标但没有删除P0。

## 明确后置

- 事务、rollback、补偿、任务队列和生产级崩溃恢复。
- delete前完整验证vector类型、维度及collection schema。
- 已存在同名collection的主键、vector字段和维度核验。
- 跨document的全局`chunk_id`主键碰撞策略。
- 将旧实验摄取脚本统一接入新helper并迁移现有7,451块数据库。
- ANN索引、metadata filters、hybrid、rerank、Hit@K、MRR和P95评测。

Day40的结论仅限小样本摄取正确性与document级最终状态收敛，不代表生产级可靠性已经完成。

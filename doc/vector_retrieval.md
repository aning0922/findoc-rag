# 向量检索决策(FinDoc)

> Day39证据更新:2026-08-05 ｜ 实验代码HEAD:`70f6514` ｜ `app/rag` Retriever和Milvus数据未修改

## 本日范围

Day39先隔离bge-m3和Milvus,用Python标准库独立验证`vector → COSINE → 稳定排序 → top-k`,再用bge-m3做5条候选和1条查询的黑盒对照。本日没有运行7,451块数据,没有连接或修改Milvus,也没有修改`app/rag/store.py`或`app/rag/retriever.py`。

## 数据流与职责

```text
上游准备 texts / IDs / metadata
        ↓
Embedding: list[str] → document vectors (N,D)
        ↓
调用程序组装 rows = {id, metadata, vector}

query text → Embedding → query batch (1,D) → query vector (D,)
        ↓
query vector 与每条 document vector 计算本次 score
        ↓
按 score 排序并返回 top-k rows
```

- Embedding只把文本映射到向量,不生成ID,不准备metadata,不验证事实。
- 调用程序负责组装row,并保证文档与查询使用兼容的模型、版本和向量空间。
- 向量库可保存ID、metadata和vector,接收query vector,在检索时计算并返回本次匹配的score。score不是文档的永久属性。
- 仅维度相同不能证明向量空间兼容。更换模型或维度后,应把原始文档文本重新输入选定模型,不能直接混用旧向量。

## 标准库最小契约

### `cosine(x, y)`

- 合法输入是非空、同维、非零的一维数字向量。
- 返回`float`分数;数学范围为`[-1,1]`,并对合法输入造成的极小浮点越界做边界截断。
- 维度不一致、空向量或任一零向量抛出`ValueError`。
- `1`表示方向相同,`0`表示方向垂直,`-1`表示方向相反。

### `top_k(query, candidates, k)`

- candidate至少包含`id`/`metadata`/`vector`;返回新列表,每条至少包含`id`/`metadata`/`vector`/`score`,不修改原`candidates`。
- score从大到小排列;同分时保留候选在原输入中的相对顺序,不按ID值另行排序。
- `k`必须是大于0的整数;非整数抛出`TypeError`,`k <= 0`抛出`ValueError`。
- 空候选且`k`合法时返回`[]`;`k`大于候选数时返回全部排序结果;任一候选向量非法时整体失败。

## bge-m3黑盒对照

固定查询为“甲公司2025年营业收入是多少？”,固定5条候选,在运行前冻结预测,运行后不替换文本。文档与向量数量都为5,文档向量整体shape为`(5,1024)`,查询批次shape为`(1,1024)`,传给自己`top_k`的单条查询shape为`(1024,)`。

| ID | 候选文本 | 实际score | 实际名次 |
|---|---|---:|---:|
| T1 | 甲公司在2025年度实现营收120亿元。 | 0.855295 | 1 |
| T4 | 甲公司2025年净利润为12亿元。 | 0.849637 | 2 |
| T3 | 乙公司2025年营业收入为120亿元。 | 0.753573 | 3 |
| T2 | “营业收入是多少”是一句用于询问金额的中文问句。 | 0.525767 | 4 |
| T5 | 海豚通过回声定位感知周围环境。 | 0.294914 | 5 |

冻结预测为`T1 > T4 > T2 > T3 > T5`,实际为`T1 > T4 > T3 > T2 > T5`,保留的预测错误是T2/T3顺序。T4与查询的score很高,但指标是“净利润”而非“营业收入”;T3的公司也不同。T5与查询明显无关,但因候选数和`k`都是5且契约没有分数阈值,仍被返回。这些结果说明排名只是当前向量空间中的相似性结果,不是事实正确性或绝对相关性证明。

上表score是本地环境一次运行的观测值。当前包装器启用`use_fp16=True`且未在文档中锁定模型revision,黑盒脚本也只打印结果而没有断言;因此这些精确数值不是稳定benchmark或自动回归基线。
如需手动重跑该观察性对照,使用`uv run python -m experiments.day39_bge_blackbox`;首次执行可能会获取模型文件。

## 可复现自动检查

- 标准库主实验覆盖22个契约测试,独立Gate重写覆盖18个陌生测试。
- 全量回归为`99 passed`,Ruff通过。bge-m3黑盒脚本不在这40个Day39自动测试中。

```bash
uv run pytest -q tests/test_day39_vector_lab.py
uv run pytest -q tests/test_day39_gate_rewrite.py
uv run ruff check .
```

## 人工Gate记录

- 故意反转排序时,事先预测的3个排序测试全部失败,恢复后全绿。
- 在空文件中独立重写`cosine/top_k`,第一版通过18个陌生Gate测试。
- 陌生三维手算得到`G4 > G1 > G2 = G6 > G3 > G5`,top-4为`G4/G1/G2/G6`;维度故障变体按契约整体抛出`ValueError`。
- Day39行为、量化、理解表达和迁移证据均评为3级,实际用时按碎片时间估算为8小时。

## 尚未证明

- 本日是5条候选的精确遍历,不证明大规模检索效率或质量。
- 未验证`app/rag`向量与chunk的一一对齐,未修复`store.py`中“越小越相似”的历史注释;本日隔离实验验证的COSINE契约是score越大越相似,`app/rag`注释与测试保留到Day40。
- 未实现入库幂等、更新或删除。
- 未研究ANN索引内部、sparse、hybrid、rerank或正式检索评测。
- `k`的冻结测试覆盖了正整数、非正整数、浮点数和字符串,未单独定义Python `bool`边界。

# 固定 Agent 评测结果归因

当前状态：十二题逐项评分、可追溯归因及三个合同/装配观察均已确认。原始评测分数保持不变；未证实的具体协议失败原因仍明确保留。

## 输入与评分口径

- 原始报告：[agent_eval_3a2d683e-a3ec-4b13-ac0a-a22cadbfa91f.json](agent_eval_3a2d683e-a3ec-4b13-ac0a-a22cadbfa91f.json)，SHA-256 `1799909b2cc1e38acfe6d21306c452c910e24a2da4c3300c794aacccb61480aa`。
- 冻结题集：[agent_tasks_v1.jsonl](../agent_tasks_v1.jsonl)，SHA-256 `2d7ab53bc5fafb2a295e5c4391de3b73422c7a117fe0e6687f6b5c375e88012c`。
- 原报告记录真实模型 `deepseek-v4-flash`，聚合评分保持工具选择 **9/12**、参数 **8/13**、终态 **7/12**。这是三个维度，不合并为单一准确率，也不以部分核对结果替换原聚合评分。
- [scorer](../../app/agent/evaluation.py)：工具选择按完整有序工具序列逐题比较；参数按预期调用位置计分，同位置工具名及全部指定参数规则均须匹配；终态只比较预期与实际状态。`0/0` 表示无预期调用位置、参数不适用，不计算百分比。
- 原始报告保留实际申请的工具名、参数及终态，没有完整模型回答。补充证据来自对 [agent_runs.sqlite3](agent_runs.sqlite3) 的只读查询：以各行 `run_id` 定位 `agent_runs` 和按 `sequence` 排序的 `run_events`。安全事件是执行后的投影，不用事件时间差推算真实工具耗时。
- [评测装配](../../scripts/evaluate_agent.py)使用 [固定依赖](../../app/agent/eval_fixtures.py)：真实模型搭配确定性检索片段及有限内存事实库。`agent-eval-report.pdf` 是样例来源标识，不等于真实年报文件核验。下文片段正文来自代码核对，不能冒充数据库保存的完整工具响应。
- 本次仅分析既有证据，未重跑评测、生产测试或模型，未修改题集、配置、代码或原始结果。

## 已确认案例

下表分数顺序为工具选择、参数、终态。每题完整 prompt 与冻结要求以题集同名 `case_id` 为准，原始观察以报告 `results` 中同名记录为准。

| case_id / run_id | 原评分逐项复核 | 可追溯证据与结论 |
|---|---|---|
| agent-001 / `24f1bb56-e136-4cc3-b15d-9664a82a3907` | 1/1；0/0（不适用）；1/1 | 要求用一句话解释营业收入增长率，不查询或计算。预期和实际工具序列均为空，终态均为 success；数据库仅有 sequence 1 的 run_succeeded，safe_result 中 final_answer_available=true、工具摘要为空。原评分通过，无已证实失败；正文未保存，解释正确性及一句话要求无法复核。 |
| agent-002 / `c1c18606-c638-428c-b336-acc7d480cbdf` | 1/1；0/0（不适用）；1/1 | 要求简要说明阅读财报的帮助方式，不调用工具或查数据。预期和实际工具序列均为空，终态均为 success；数据库仅有 sequence 1 的 run_succeeded，final_answer_available=true。原评分通过，无已证实失败；正文未保存，能力说明的准确性无法复核。 |
| agent-003 / `a573a9aa-d49d-44b7-8f42-7b9bd605e59e` | 1/1；1/1；1/1 | 要求检索2025年营业收入、最多3条。实际仅一次 search_finance_docs，query="2025年营业收入" 同时包含两个指定关键词，top_k=3，终态 success。sequence 2 的 tool_succeeded 记录 requested_top_k=3、result_count=2、chunk-current/chunk-previous；返回2条未超过上限。代码样例分别为2025年收入100亿元、2024年收入80亿元。原评分通过；最终回答正文未保存，不能据 success 认定其事实或引用正确。 |
| agent-004 / `4c8c6817-3a45-465d-a904-b880aba1cbc2` | 1/1；1/1；1/1 | 要求检索经营活动现金流量净额、最多2条。实际仅一次 search_finance_docs，query="经营活动产生的现金流量净额" 同时包含“经营活动”“现金流量净额”，top_k=2，终态 success。sequence 2 的 tool_succeeded 记录 result_count=1、chunk-cash-flow，未超过上限；代码样例为2025年经营活动现金流量净额30亿元。原评分通过；最终回答正文未保存。 |
| agent-005 / `f9ef3bee-69a6-45fd-9558-0d79cff88752` | 1/1；1/1；1/1 | 要求检索研发费用、只返回1条。实际仅一次 search_finance_docs，query="研发费用"、top_k=1，终态 success。sequence 2 的 tool_succeeded 记录 result_count=1、empty=false、chunk-rd；代码样例为2025年研发费用8亿元。工具实际返回数量符合要求，原评分通过；最终回答正文未保存。 |
| agent-006 / `326744da-c335-483b-b7b5-fbbc329e35bb` | 1/1；1/1；0/1 | 要求直接计算、不得先检索。实际仅一次 calculate_financial_metric，metric_id=revenue_growth_rate、本期来源chunk-current、上期来源chunk-previous，三项均匹配。sequence 2 的 tool_succeeded 保存 value="25.00"、unit=PERCENT、formula_id=revenue_growth_rate_v1、source_count=2；sequence 3 为 run_failed，terminal_status/error_code 均为 protocol_error，而预期为 success。工具计算已成功，运行在协议或输出校验层失败；具体触发原因待证实。 |

## agent-006 的归因边界

已证明：选用工具及参数符合冻结要求，计算工具成功返回25.00%，但运行未达到预期成功终态。不能归为工具计算失败，不能以缺少 HTTP runtime 解释本次离线失败。

待证实：[tool_loop.py](../../app/agent/tool_loop.py)的多个分支均可产生 protocol_error，包括未知 finish_reason、结束标记与消息形状不一致，以及最终文本未通过可信计算百分比一致性检查。现存报告和安全事件没有保存该次最终模型响应或具体错误说明，[run_service.py](../../app/agent/run_service.py)的失败事件只保留通用类别。故不能断言模型把25%改错，也不能确定命中了哪个分支。当前代码提供的是可能路径，不是历史触发路径的直接证据。

## 分批核对状态（已关闭）

首批保留agent-001—006的评分与证据；后续已补齐agent-007—012及三个合同/装配观察，详见以下追加记录。全部案例均已确认，具体根因的证据缺口不以猜测填补。

## 追加核对：agent-007 至 agent-012

以下六题已逐项确认，补齐十二题；分数顺序仍为工具选择、参数、终态。

| case_id / run_id | 原评分逐项复核 | 可追溯证据与结论 |
|---|---|---|
| agent-007 / `ff2b0261-fbbd-4f84-8bbf-75aaea57e057` | 1/1；1/1；1/1 | 要求直接使用本期chunk-current、上期chunk-previous计算，不检索。实际仅一次calculate_financial_metric，metric_id=revenue_growth_rate及两期来源全部匹配；sequence 2的tool_succeeded保存25.00%、source_count=2，sequence 3为run_succeeded。原评分通过；与006的关键差别是终态成功。safe_result保留计算摘要及final_answer_available=true，没有最终回答正文，不能逐句复核其语义。 |
| agent-008 / `def34b0a-04d5-4aa5-92df-0b8d22c09d89` | 1/1；1/1；0/1 | 要求调用可信计算工具，不自行心算。实际申请一次calculate_financial_metric，指标及chunk-current/chunk-previous均匹配；预期success，实际protocol_error。仅有sequence 1的tool_requested和sequence 2的run_failed，无tool_succeeded、tool_failed或计算结果摘要。不能像006一样确认计算成功，也不能将缺少成功记录直接断言为工具一定未执行；具体协议失败原因待证实。 |
| agent-009 / `d08ff972-3a9c-4c6e-89cc-4c35379fbadb` | 0/1；1/2；0/1 | 预期一次搜索2025、2024营业收入后计算。实际只有search_finance_docs，query="2025年和2024年营业收入"、top_k=2；第一个参数位置通过，第二个计算位置缺少调用，不能得分；完整序列不匹配。事件仅有tool_requested、run_failed(protocol_error)，无搜索成功证据或结果摘要。已证明申请流程未完成，不能说模型取得搜索结果后忘记计算；具体协议分支待证实。 |
| agent-010 / `de9fbf6e-ede6-4bca-b474-dc711bae1c2f` | 0/1；0/2；0/1 | 预期[搜索,计算]；实际[搜索,搜索]，query依次为“本期营业收入”“上期营业收入”，top_k均为2。第一个位置缺“上期”；第二个位置工具名不是计算工具，两个参数位置均不通过。两次tool_requested后为run_failed(protocol_error)，无成功事件或结果。已证明查询被拆成两次申请且缺少计算；报告丢失响应轮次边界，不能仅凭调用ID或事件时间认定同轮多工具调用，更不能将其作为已证实协议根因。 |
| agent-011 / `a755f04b-2b2c-4ecc-8189-c73bd3b0c6c2` | 0/1；0/2；0/1 | 冻结标准预期一次搜索同时含2025、2024、营收，top_k=5，再计算；实际是两次搜索申请，query依次为“2025年营业收入”“2024年营业收入”，top_k均为5。第一个位置缺2024，且“营业收入”不含连续字符串“营收”；第二个位置工具名不是计算工具。两次tool_requested后为run_failed(protocol_error)，无成功事件或结果。缺少计算及与冻结序列不符有直接记录；同义表达不被contains_all接受属于scorer字面匹配局限，不证明模型不理解营收；即使忽略同义词问题，原记录仍有年份和调用序列偏差。具体协议根因待证实。 |
| agent-012 / `cab04ea0-80e9-49aa-a099-23e6c2ada6f2` | 1/1；1/1；1/1 | 本题预期tool_error。实际仅一次calculate_financial_metric，metric_id=revenue_growth_rate、本期chunk-missing、上期chunk-previous全部符合题目；sequence 2为tool_failed(tool_execution_error)，sequence 3为run_failed(tool_error)。原评分通过，是预期失败场景，不能强行归为评测失败或模型参数填错。固定事实库没有chunk-missing，计算代码查不到本期来源时抛SOURCE_NOT_AVAILABLE，执行层统一映射为tool_execution_error；来源缺失有输入和代码支持，并与事件一致，但历史事件没有直接保存具体异常类型。 |

## 三维评分汇总与证据限制

十二题复核合计：工具选择9/12、参数8/13、终态7/12，与原报告一致。参数按预期调用位置计数，不按参数字段或来源数量计数；工具选择按题比较整个有序申请序列，不以工具执行是否成功直接判分。工具/参数scorer读取的是[模型申请记录](../../app/agent/eval_runner.py)，[安全事件投影](../../app/agent/run_service.py)另外提供可追溯的工具成功或失败摘要，两者不能混同。

001—005、007、012均通过各自原评分；012的预期即为受控工具失败。006、008、009、010、011的实际终态均为protocol_error，不能据共享错误码认定共同根因；006有计算成功证据，008—011缺少工具成功结果记录。没有新增或重跑评测，也没有修改scorer、阈值、数据、模型或代码。原分数保留，字面匹配局限及证据缺口单独记录。

## 已确认的三个合同与装配观察

1. **任务合同须区分调用申请、工具执行与运行终态。** agent-006计算成功但运行失败，agent-008只有计算申请、无法确认计算成功，agent-012的工具失败符合该题预期。后续任务合同应明确各层成功条件和预期失败，不能只凭参数正确、有计算结果或出现错误判定整个任务；后续对应A1的合同边界。
2. **真实装配与评测样例须保持来源边界。** 本报告是真实模型搭配固定检索样例和有限内存事实库的结果，不能证明上传财报后的真实工具链已接通。后续A2按既定范围装配真实可用搜索依赖并校验来源，不导入评测fixture冒充产品能力；现有HTTP runtime缺口是独立产品断点，不是历史离线失败的默认原因。
3. **后续验收同时保留原评分与证据限制。** 工具选择比较完整申请序列，参数按预期调用位置评分，终态只比较标签。agent-011的同义表达暴露字面匹配局限，但仍有独立的年份和调用序列偏差；通用protocol_error及未保存的回答正文限制具体根因和答案质量复核。后续合同与装配验收须区分已证明事实和待证实假设，不猜测历史触发分支，不调整历史分数。

以上是基于本次固定结果的有限观察，不新增或实施修复，不重跑评测，不将通过旧三维scorer扩大为真实文档事实正确性或完整产品质量承诺。

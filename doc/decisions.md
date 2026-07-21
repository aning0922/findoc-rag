# 分块决策(FinDoc)

- **策略**:递归字符分块(`RecursiveCharacterTextSplitter.from_tiktoken_encoder`)——中文尽量在句号 / 换行断、不硬劈;不用 `TokenTextSplitter`(会劈碎汉字)。
- **大小**:`chunk_size=400 token, overlap=60`——年报正文密,约一段话;overlap 保上下文不在边界断。
- **表格**:整块不切(表体存 `table_md`),避免"半行表格"污染检索。
- **元数据**:每块带 `source_file / page / section / chunk_id`;section 靠 MinerU 的 title 块串。
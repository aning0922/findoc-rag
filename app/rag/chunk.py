from langchain_text_splitters import RecursiveCharacterTextSplitter

CHINESE_SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", "，", "、", " ", ""]


def recursive_chunk_char(text: str, size: int = 500, overlap: int = 80) -> list[str]:
    """
    递归按中文分隔符分块，一定程度上保证语义完整
    Args:
        text: 文本
        size: 分块大小
        overlap: 重叠部分大小
    Returns:
        list[str]: 分块列表
    """
    sp = RecursiveCharacterTextSplitter(
        chunk_size=size,
        chunk_overlap=overlap,
        separators=CHINESE_SEPARATORS,
    )
    return sp.split_text(text)


def fixed_chunk(text: str, size: int = 500, overlap: int = 80) -> list[str]:
    """
    固定大小分块，不保证语义完整
    Args:
        text: 文本
        size: 分块大小
        overlap: 重叠部分大小
    Returns:
        list[str]: 分块列表
    """
    if size <= overlap:
        raise ValueError("size 必须 > overlap，否则死循环")
    chunks: list[str] = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + size])
        start += size - overlap
    return chunks

    
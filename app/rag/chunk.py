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


text = "你说什么呀，你在说什么什么什么嗯啊，什么好的是什么啊啊"
print(fixed_chunk(text, size=10, overlap=4))
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false, reportUnnecessaryComparison=false
from typing import Any
from pymilvus import MilvusClient

DIM = 1024


def get_client(db_path: str = "./data/milvus.db") -> MilvusClient:
    """获取milvus客户端"""
    return MilvusClient(db_path)


def ensure_collection(client: MilvusClient, name: str, dim: int = DIM) -> None:
    """
    确保集合存在
    """
    if not client.has_collection(name):
        client.create_collection(collection_name=name, dimension=dim, metric_type="COSINE")


def insert_rows(client: MilvusClient, name: str, rows: list[dict[str, Any]]) -> int:
    """插入行"""
    client.insert(collection_name=name, data=rows)
    return len(rows)


def count_rows(client: MilvusClient, name: str) -> int:
    """
    统计行数
    Args:
        client: Milvus客户端
        name: 集合名称
    Returns:
        int: 行数
    """
    res = client.query(collection_name=name, filter="", output_fields=["count(*)"])
    return int(res[0]["count(*)"])


def search(
    client: MilvusClient, name: str, query_vec: list[float], top_k: int = 5
) -> list[dict[str, Any]]:
    """
    搜索结果，返回距离和实体
    实体包含text, page, section, source_file, chunk_id, type, table_md
    距离越小，越相似
    Args:
        client: Milvus客户端
        name: 集合名称
        query_vec: 查询向量
        top_k: 返回结果数量
    Returns:
        list[dict[str, Any]]: 搜索结果
            - distance: 距离
            - text: 文本
            - page: 页码
            - section: 章节
            - source_file: 源文件
            - chunk_id: 块ID
            - type: 类型
            - table_md: 表格元数据
    """
    res = client.search(
        collection_name=name,
        data=[query_vec],
        limit=top_k,
        output_fields=["text", "page", "section", "source_file", "chunk_id", "type", "table_md"],
    )
    return [{"distance": h["distance"], **h["entity"]} for h in res[0]]

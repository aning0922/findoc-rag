import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pymilvus import MilvusClient

Embedder = Callable[[list[str]], list[list[float]]]


@dataclass(frozen=True)
class ReplaceResult:
    inserted: int
    updated: int
    skipped: int
    final_ids: frozenset[str]


def build_aligned_rows(
    raw_chunks: list[dict[str, Any]],
    embedder: Embedder,
) -> list[dict[str, Any]]:
    legal_chunks: list[dict[str, Any]] = []
    for index, chunk in enumerate(raw_chunks):
        if "text" not in chunk:
            raise ValueError(f"raw_chunks[{index}] 缺少 text 字段")
        if chunk["text"] is None:
            raise ValueError(f"raw_chunks[{index}] 的 text 为空")
        text = chunk["text"]
        if not isinstance(text, str):
            raise ValueError(f"raw_chunks[{index}] 的 text 类型错误")
        if text.strip() == "":
            continue
        chunk_id = chunk.get("chunk_id")
        if not isinstance(chunk_id, str) or not chunk_id.strip():
            raise ValueError(f"raw_chunks[{index}] 缺少有效 chunk_id")
        legal_chunks.append(chunk)

    texts = [chunk["text"] for chunk in legal_chunks]
    vectors = embedder(texts)

    if len(vectors) != len(legal_chunks):
        raise ValueError("vectors 长度与 legal_chunks 长度不一致")

    rows = [{**chunk, "vector": vector} for chunk, vector in zip(legal_chunks, vectors)]
    return rows


def replace_document_rows(
    client: MilvusClient, collection_name: str, document_id: str, rows: list[dict[str, Any]]
) -> ReplaceResult:
    if not isinstance(document_id, str) or not document_id.strip():
        raise ValueError("document_id 必须是非空字符串")

    expected_ids: set[str] = set()
    for row in rows:
        if row.get("chunk_id") is None:
            raise ValueError("row 缺少有效 chunk_id")

        chunk_id = row.get("chunk_id")
        if not isinstance(chunk_id, str) or not chunk_id.strip():
            raise ValueError("row 的 chunk_id 类型错误")
        if chunk_id in expected_ids:
            raise ValueError("row 的 chunk_id 重复")
        expected_ids.add(chunk_id)

    new_rows = [{**row, "document_id": document_id} for row in rows]

    document_filter = f"document_id == {json.dumps(document_id)}"
    old_rows = client.query(
        collection_name=collection_name,
        filter=document_filter,
        output_fields=["chunk_id"],
    )
    old_ids = {row["chunk_id"] for row in old_rows}
    client.delete(
        collection_name=collection_name,
        filter=document_filter,
    )

    if new_rows:
        client.insert(
            collection_name=collection_name,
            data=new_rows,
        )

    actual_rows = client.query(
        collection_name=collection_name,
        filter=document_filter,
        output_fields=["chunk_id"],
    )
    actual_ids = {row["chunk_id"] for row in actual_rows}

    if actual_ids != expected_ids:
        raise RuntimeError(f"document最终ID集合错误：expected={expected_ids}, actual={actual_ids}")

    if len(actual_rows) != len(expected_ids):
        raise RuntimeError(
            f"document最终行数错误：expected={len(expected_ids)}, actual={len(actual_rows)}"
        )

    stale_ids = old_ids - expected_ids

    if stale_ids:
        leftovers = client.get(
            collection_name=collection_name,
            ids=list(stale_ids),
            output_fields=["chunk_id"],
        )
        if leftovers:
            raise RuntimeError(f"旧chunk仍然存在：{stale_ids}")

    return ReplaceResult(
        inserted=len(new_rows),
        updated=0,
        skipped=0,
        final_ids=frozenset(actual_ids),
    )

from app.rag.embed import embed
from app.rag.store import get_client, search

_client = get_client()


def retrieve(query: str, top_k: int = 5, collection: str = "findoc") -> list[dict[str, object]]:
    query_vec = embed([query])[0]
    return search(_client, collection, query_vec, top_k)


if __name__ == "__main__":
    for hit in retrieve("京东方 2025 年营业收入是多少"):
        print(
            f"[{hit['distance']:.3f}] {hit['source_file']} p{hit['page']}: {str(hit['text'])[:40]}"
        )

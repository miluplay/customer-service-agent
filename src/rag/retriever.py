"""RAG 检索入口：根据用户问题从本地向量库中找出最相关的政策片段。"""

from src.config import settings
from src.rag.embed import embed_texts
from src.rag.vector_store import VectorStore


def search(query: str, top_k: int = 5) -> list[dict]:
    if not query.strip():
        return []

    store = VectorStore.load(settings.vector_store_path)
    if not store.records:
        return []

    query_embedding = embed_texts([query])[0]
    return store.search(query_embedding, top_k=top_k)


def search_default(query: str) -> list[dict]:
    return search(query, top_k=settings.top_k)

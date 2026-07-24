"""构建本地 RAG 知识库：读取政策文档、切 chunk、生成向量并保存 JSON。"""

from pathlib import Path

from src.config import settings
from src.rag.embed import chunk_text, embed_texts
from src.rag.vector_store import VectorStore


def build_knowledge_base() -> VectorStore:
    knowledge_base_dir = Path(settings.knowledge_base_dir)
    documents = sorted(knowledge_base_dir.glob("*.md"))
    store = VectorStore()

    for document in documents:
        text = document.read_text(encoding="utf-8")
        chunks = chunk_text(text)
        embeddings = embed_texts(chunks)
        for index, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            store.add(
                text=chunk,
                embedding=embedding,
                metadata={
                    "source": str(document),
                    "chunk_index": index,
                },
            )

    store.save(settings.vector_store_path)
    return store


def main() -> None:
    store = build_knowledge_base()
    print(f"Built knowledge base with {len(store.records)} chunks.")


if __name__ == "__main__":
    main()

"""RAG 向量化工具：负责政策文本切块，并把文本转换成可检索的向量。"""

import hashlib
import os
import re
from collections.abc import Iterable

from src.config import settings


LOCAL_EMBEDDING_DIM = 256


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    sections = _split_markdown_sections(text)
    chunks: list[str] = []
    for section in sections:
        chunks.extend(_split_by_size(section, chunk_size, overlap))
    return chunks


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    if os.getenv("OPENAI_API_KEY"):
        from openai import OpenAI

        client = OpenAI()
        response = client.embeddings.create(
            model=settings.embedding_model,
            input=texts,
        )
        return [item.embedding for item in response.data]
    return [_local_embedding(text) for text in texts]


def _split_markdown_sections(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").strip()
    if not normalized:
        return []

    sections: list[str] = []
    current: list[str] = []
    for line in normalized.splitlines():
        if line.startswith("#") and current:
            sections.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append("\n".join(current).strip())
    return [section for section in sections if section]


def _split_by_size(text: str, chunk_size: int, overlap: int) -> list[str]:
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end].strip())
        if end == len(text):
            break
        start = end - overlap
    return [chunk for chunk in chunks if chunk]


def _local_embedding(text: str) -> list[float]:
    tokens = _tokenize(text)
    vector = [0.0] * LOCAL_EMBEDDING_DIM
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % LOCAL_EMBEDDING_DIM
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    return _normalize(vector)


def _tokenize(text: str) -> Iterable[str]:
    return re.findall(r"[\w\u4e00-\u9fff]+", text.lower())


def _normalize(vector: list[float]) -> list[float]:
    norm = sum(value * value for value in vector) ** 0.5
    if norm == 0:
        return vector
    return [value / norm for value in vector]

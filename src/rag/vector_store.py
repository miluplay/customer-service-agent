"""本地向量库：用 JSON 保存 chunk、embedding 和来源信息，并提供相似度搜索。"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class VectorRecord:
    text: str
    embedding: list[float]
    metadata: dict


class VectorStore:
    def __init__(self, records: list[VectorRecord] | None = None) -> None:
        self.records = records or []

    def add(self, text: str, embedding: list[float], metadata: dict | None = None) -> None:
        self.records.append(
            VectorRecord(
                text=text,
                embedding=embedding,
                metadata=metadata or {},
            )
        )

    def search(self, query_embedding: list[float], top_k: int = 5) -> list[dict]:
        scored = [
            {
                "text": record.text,
                "metadata": record.metadata,
                "score": _cosine_similarity(query_embedding, record.embedding),
            }
            for record in self.records
        ]
        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:top_k]

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(record) for record in self.records]
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "VectorStore":
        source = Path(path)
        if not source.exists():
            return cls()
        payload = json.loads(source.read_text(encoding="utf-8"))
        records = [
            VectorRecord(
                text=item["text"],
                embedding=item["embedding"],
                metadata=item.get("metadata", {}),
            )
            for item in payload
        ]
        return cls(records)


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(left_value * right_value for left_value, right_value in zip(left, right))
    left_norm = sum(value * value for value in left) ** 0.5
    right_norm = sum(value * value for value in right) ** 0.5
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)

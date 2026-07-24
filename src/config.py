"""项目配置中心：集中读取模型、路径、检索数量和日志级别等配置。"""

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_env_file(path: Path) -> None:
    """读取简单 KEY=VALUE 配置，且不覆盖终端中已设置的环境变量。"""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip("'\"")
        if name:
            os.environ.setdefault(name, value)


_load_env_file(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    model_name: str
    deepseek_base_url: str
    embedding_model: str
    knowledge_base_dir: str
    vector_store_path: str
    top_k: int
    max_input_length: int


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    return int(value)


def _get_path(name: str, default: str) -> str:
    value = os.getenv(name, default)
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str(PROJECT_ROOT / path)


settings = Settings(
    model_name=os.getenv("MODEL_NAME", "deepseek-v4-flash"),
    deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
    knowledge_base_dir=_get_path("KNOWLEDGE_BASE_DIR", "data/knowledge_base"),
    vector_store_path=_get_path("VECTOR_STORE_PATH", "data/vector_store.json"),
    top_k=_get_int("TOP_K", 5),
    max_input_length=_get_int("MAX_INPUT_LENGTH", 2000),
)

MODEL_NAME = settings.model_name
DEEPSEEK_BASE_URL = settings.deepseek_base_url
EMBEDDING_MODEL = settings.embedding_model
KNOWLEDGE_BASE_DIR = settings.knowledge_base_dir
VECTOR_STORE_PATH = settings.vector_store_path
TOP_K = settings.top_k
MAX_INPUT_LENGTH = settings.max_input_length

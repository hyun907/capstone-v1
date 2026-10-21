"""비공개 로컬 runbook의 선택적 벡터 검색."""

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Iterator

from schemas import ManualSnippet

MODEL_NAME = "intfloat/multilingual-e5-small-onnx-o4"
MODEL_SOURCE = "intfloat/multilingual-e5-small"
MIN_SIMILARITY = 0.83


@dataclass(frozen=True)
class Passage:
    title: str
    source: str
    snippet: str
    text: str


@dataclass(frozen=True)
class VectorIndex:
    fingerprint: str
    passages: tuple[Passage, ...]
    vectors: tuple[tuple[float, ...], ...]


_lock = Lock()
_model = None
_index: dict[Path, VectorIndex] = {}


def search_vector_manual(query: str, top_k: int, data_dir: Path) -> list[ManualSnippet]:
    """첫 요청에서 메모리 인덱스를 만들고, 파일 변경 시 다시 만듭니다."""
    passages, fingerprint = _read_passages(data_dir)
    if not passages:
        return []

    with _lock:
        model = _load_model()
        root = data_dir.resolve()
        index = _index.get(root)
        if index is None or index.fingerprint != fingerprint:
            try:
                embeddings = model.embed([f"passage: {passage.text}" for passage in passages])
            except Exception:
                raise RuntimeError("운영 매뉴얼 벡터를 생성할 수 없습니다.") from None
            vectors = _encode(embeddings, len(passages))
            index = VectorIndex(fingerprint, passages, vectors)
            _index[root] = index
        try:
            query_embedding = model.query_embed(f"query: {query}")
        except Exception:
            raise RuntimeError("운영 매뉴얼 벡터를 생성할 수 없습니다.") from None
        query_vector = _encode(query_embedding, 1)[0]

    best: dict[str, ManualSnippet] = {}
    for passage, vector in zip(index.passages, index.vectors):
        score = _cosine(query_vector, vector)
        if score < MIN_SIMILARITY:
            continue
        previous = best.get(passage.source)
        if previous is None or score > previous.score:
            best[passage.source] = ManualSnippet(
                title=passage.title,
                source=passage.source,
                snippet=passage.snippet,
                score=score,
            )

    return sorted(best.values(), key=lambda item: (-item.score, item.source))[:top_k]


def _read_passages(data_dir: Path) -> tuple[tuple[Passage, ...], str]:
    runbook_dir = data_dir / "runbooks"
    if not runbook_dir.exists():
        return (), ""

    data_root = data_dir.resolve()
    runbook_root = runbook_dir.resolve()
    if not runbook_root.is_relative_to(data_root):
        raise RuntimeError("운영 매뉴얼 디렉터리 경로가 올바르지 않습니다.")

    fingerprint = hashlib.sha256()
    passages: list[Passage] = []
    for path in sorted(runbook_dir.glob("*.md")):
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", path.stem):
            continue
        try:
            resolved_path = path.resolve()
        except RuntimeError:
            continue
        except OSError:
            raise RuntimeError("운영 매뉴얼 파일 경로를 확인할 수 없습니다.") from None
        if not resolved_path.is_relative_to(runbook_root):
            continue
        try:
            contents = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            raise RuntimeError("운영 매뉴얼 파일을 읽을 수 없습니다.") from None

        fingerprint.update(path.name.encode("utf-8"))
        fingerprint.update(contents.encode("utf-8"))
        heading = ""
        for line in contents.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                heading = line.lstrip("# ").strip()
            for snippet in _chunks(line):
                passages.append(
                    Passage(
                        title=path.stem,
                        source=f"runbook://incident-response/{path.stem}",
                        snippet=snippet,
                        text=f"{path.stem} {heading} {snippet}",
                    )
                )
    return tuple(passages), fingerprint.hexdigest()


def _chunks(line: str) -> Iterator[str]:
    """긴 줄을 겹치는 짧은 조각으로 나눕니다."""
    start = 0
    while start < len(line):
        end = min(start + 180, len(line))
        yield line[start:end]
        if end == len(line):
            break
        start = end - 40


def _load_model():
    global _model
    if _model is not None:
        return _model
    try:
        from fastembed import TextEmbedding
    except ImportError:
        raise RuntimeError("벡터 검색 의존성이 없습니다. uv sync --extra vector를 실행하세요.") from None
    try:
        _register_model(TextEmbedding)
        _model = TextEmbedding(model_name=MODEL_NAME, local_files_only=True)
    except Exception:
        raise RuntimeError("벡터 모델을 로컬 캐시에서 열 수 없습니다. 모델을 먼저 설치하세요.") from None
    return _model


def _register_model(text_embedding_type) -> None:
    """FastEmbed의 로컬 E5-small ONNX 변형을 등록합니다."""
    if any(model["model"] == MODEL_NAME for model in text_embedding_type.list_supported_models()):
        return
    from fastembed.common.model_description import ModelSource, PoolingType

    text_embedding_type.add_custom_model(
        model=MODEL_NAME,
        pooling=PoolingType.MEAN,
        normalization=True,
        sources=ModelSource(hf=MODEL_SOURCE),
        dim=384,
        model_file="onnx/model_O4.onnx",
    )


def _encode(embeddings, expected: int) -> tuple[tuple[float, ...], ...]:
    try:
        vectors = tuple(tuple(float(value) for value in embedding) for embedding in embeddings)
    except Exception:
        raise RuntimeError("운영 매뉴얼 벡터를 생성할 수 없습니다.") from None
    if len(vectors) != expected or not vectors or not vectors[0]:
        raise RuntimeError("운영 매뉴얼 벡터 인덱스 형식이 올바르지 않습니다.")
    if any(len(vector) != len(vectors[0]) or not all(map(math.isfinite, vector)) for vector in vectors):
        raise RuntimeError("운영 매뉴얼 벡터 인덱스 형식이 올바르지 않습니다.")
    return vectors


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise RuntimeError("운영 매뉴얼 벡터 인덱스 차원이 맞지 않습니다.")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        raise RuntimeError("운영 매뉴얼 벡터 인덱스 형식이 올바르지 않습니다.")
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)

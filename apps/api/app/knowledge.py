from __future__ import annotations

import hashlib
import json
import math
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Protocol, Sequence

from .models import Document, DocumentChunk, Evidence
from .security import redact_secrets

EMBEDDING_DIMENSIONS = 1536
TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)
PLACEHOLDER_API_KEYS = {"", "replace-me", "changeme", "none", "null"}


def tokenize(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(text)}


@dataclass(frozen=True)
class RetrievalFilters:
    product_line: Optional[str] = None
    version: Optional[str] = None
    permissions: Sequence[str] = field(default_factory=tuple)
    as_of: Optional[str] = None


def chunk_document(document: Document, max_chars: int = 700) -> List[DocumentChunk]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", document.content) if part.strip()]
    chunks: List[DocumentChunk] = []
    current = ""

    for paragraph in paragraphs or [document.content]:
        if len(current) + len(paragraph) + 2 <= max_chars:
            current = f"{current}\n\n{paragraph}".strip()
            continue

        if current:
            chunks.append(_chunk_from_document(document, current, len(chunks)))
        current = paragraph[:max_chars]

    if current:
        chunks.append(_chunk_from_document(document, current, len(chunks)))

    return chunks


def _chunk_from_document(document: Document, content: str, chunk_index: int) -> DocumentChunk:
    return DocumentChunk(
        document_id=document.id,
        tenant_id=document.tenant_id,
        title=document.title,
        source_type=document.source_type,
        uri=document.uri,
        content=content,
        chunk_index=chunk_index,
        product_line=document.product_line,
        version=document.version,
        required_permissions=list(document.required_permissions),
        valid_from=document.valid_from,
        valid_until=document.valid_until,
        source_system=document.source_system,
    )


def embedding_text_for_chunk(chunk: DocumentChunk) -> str:
    metadata = " ".join(
        part
        for part in [
            chunk.product_line or "",
            chunk.version or "",
            " ".join(chunk.required_permissions),
            chunk.source_system or "",
        ]
        if part
    )
    return f"{chunk.title}\n{chunk.source_type}\n{metadata}\n{chunk.content}"


def _embedding_tokens(text: str) -> List[str]:
    tokens = [token.lower() for token in TOKEN_RE.findall(text)]
    bigrams = [f"{left}::{right}" for left, right in zip(tokens, tokens[1:])]
    return tokens + bigrams


class EmbeddingModel(Protocol):
    dimensions: int
    provider_name: str

    def embed(self, text: str) -> List[float]:
        ...


class EmbeddingError(RuntimeError):
    pass


class HashingEmbeddingModel:
    """Deterministic local embedding model for private tests and fallback."""

    provider_name = "hashing"

    def __init__(self, dimensions: int = EMBEDDING_DIMENSIONS) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> List[float]:
        features = _embedding_tokens(text)
        vector = [0.0] * self.dimensions
        if not features:
            return vector

        for feature in features:
            digest = hashlib.sha256(feature.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


@dataclass(frozen=True)
class EmbeddingSettings:
    provider: str
    base_url: str
    model: str
    api_key: str
    timeout_seconds: float
    dimensions: int

    @classmethod
    def from_env(cls) -> "EmbeddingSettings":
        provider = (
            _env("SUPPORT_COPILOT_EMBEDDING_PROVIDER")
            or _env("EMBEDDING_PROVIDER")
            or "hashing"
        ).lower()
        base_url = (
            _env("SUPPORT_COPILOT_EMBEDDING_BASE_URL")
            or _env("EMBEDDING_BASE_URL")
            or "https://api.openai.com/v1"
        )
        model = (
            _env("SUPPORT_COPILOT_EMBEDDING_MODEL")
            or _env("EMBEDDING_MODEL")
            or "text-embedding-3-small"
        )
        api_key = _env("SUPPORT_COPILOT_EMBEDDING_API_KEY") or _env("EMBEDDING_API_KEY")
        timeout_raw = (
            _env("SUPPORT_COPILOT_EMBEDDING_TIMEOUT_SECONDS")
            or _env("EMBEDDING_TIMEOUT_SECONDS")
            or "20"
        )
        dimensions_raw = (
            _env("SUPPORT_COPILOT_EMBEDDING_DIMENSIONS")
            or _env("EMBEDDING_DIMENSIONS")
            or str(EMBEDDING_DIMENSIONS)
        )
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError:
            timeout_seconds = 20.0
        try:
            dimensions = int(dimensions_raw)
        except ValueError:
            dimensions = EMBEDDING_DIMENSIONS

        return cls(
            provider=provider,
            base_url=base_url,
            model=model,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            dimensions=dimensions,
        )

    def embeddings_url(self) -> str:
        if self.base_url.rstrip("/").endswith("/embeddings"):
            return self.base_url.rstrip("/")
        return f"{self.base_url.rstrip('/')}/embeddings"


class OpenAICompatibleEmbeddingModel:
    provider_name = "openai_compatible"

    def __init__(self, settings: EmbeddingSettings) -> None:
        self.settings = settings
        self.dimensions = settings.dimensions

    def embed(self, text: str) -> List[float]:
        payload = {
            "model": self.settings.model,
            "input": text,
        }
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.settings.api_key and self.settings.api_key.strip().lower() not in PLACEHOLDER_API_KEYS:
            headers["Authorization"] = f"Bearer {self.settings.api_key}"

        request = urllib.request.Request(
            self.settings.embeddings_url(),
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.settings.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = redact_secrets(exc.read().decode("utf-8", errors="replace"))[:300]
            raise EmbeddingError(f"Embedding API returned HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise EmbeddingError(f"Embedding API request failed: {redact_secrets(exc)}") from exc

        try:
            vector = data["data"][0]["embedding"]
        except (KeyError, IndexError, TypeError) as exc:
            raise EmbeddingError("Embedding API response did not include data[0].embedding") from exc

        if not isinstance(vector, list) or not all(isinstance(item, (int, float)) for item in vector):
            raise EmbeddingError("Embedding API response embedding must be a numeric list")

        return _normalize_embedding([float(item) for item in vector], self.dimensions)


DEFAULT_EMBEDDING_MODEL = HashingEmbeddingModel()


def create_embedding_model_from_env() -> EmbeddingModel:
    settings = EmbeddingSettings.from_env()
    if settings.provider in {"hashing", "local", "deterministic", "test"}:
        return HashingEmbeddingModel(dimensions=settings.dimensions)
    if settings.provider in {"openai", "openai_compatible", "compatible"}:
        return OpenAICompatibleEmbeddingModel(settings)
    return HashingEmbeddingModel(dimensions=settings.dimensions)


def embedding_provider_status_from_env() -> Dict[str, object]:
    settings = EmbeddingSettings.from_env()
    mode = "hashing_fallback"
    if settings.provider in {"openai", "openai_compatible", "compatible"}:
        mode = "openai_compatible"
    return {
        "provider": settings.provider,
        "mode": mode,
        "model": settings.model if mode == "openai_compatible" else None,
        "base_url_configured": bool(settings.base_url) if mode == "openai_compatible" else False,
        "api_key_configured": (
            settings.api_key.strip().lower() not in PLACEHOLDER_API_KEYS
            if mode == "openai_compatible"
            else False
        ),
        "dimensions": settings.dimensions,
    }


def embed_chunk(chunk: DocumentChunk, embedding_model: EmbeddingModel = DEFAULT_EMBEDDING_MODEL) -> DocumentChunk:
    chunk.embedding = embedding_model.embed(embedding_text_for_chunk(chunk))
    return chunk


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right:
        return 0.0

    size = min(len(left), len(right))
    dot = sum(left[index] * right[index] for index in range(size))
    left_norm = math.sqrt(sum(value * value for value in left[:size]))
    right_norm = math.sqrt(sum(value * value for value in right[:size]))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def keyword_score_for_chunk(query: str, chunk: DocumentChunk) -> float:
    query_tokens = tokenize(query)
    if not query_tokens:
        return 0.0
    chunk_tokens = tokenize(_keyword_text_for_chunk(chunk))
    overlap = query_tokens.intersection(chunk_tokens)
    if not overlap:
        return 0.0
    coverage = len(overlap) / max(len(query_tokens), 1)
    density = len(overlap) / max(len(chunk_tokens), 1)
    return min(1.0, (coverage * 0.8) + (density * 0.2))


def chunk_matches_filters(chunk: DocumentChunk, filters: Optional[RetrievalFilters]) -> bool:
    if filters is None:
        return _is_active(chunk.valid_from, chunk.valid_until, None)

    if filters.product_line and chunk.product_line and chunk.product_line != filters.product_line:
        return False
    if filters.version and chunk.version and chunk.version != filters.version:
        return False

    granted_permissions = {item.lower() for item in filters.permissions}
    required_permissions = {item.lower() for item in chunk.required_permissions}
    if required_permissions and not required_permissions.issubset(granted_permissions):
        return False

    return _is_active(chunk.valid_from, chunk.valid_until, filters.as_of)


class Retriever(Protocol):
    uses_store_backend: bool

    def search(
        self,
        tenant_id: str,
        query: str,
        chunks: Optional[Iterable[DocumentChunk]] = None,
        limit: int = 4,
        filters: Optional[RetrievalFilters] = None,
    ) -> List[Evidence]:
        ...


class KeywordRetriever:
    """Deterministic keyword retriever used by hybrid search and tests."""

    uses_store_backend = False

    def search(
        self,
        tenant_id: str,
        query: str,
        chunks: Optional[Iterable[DocumentChunk]] = None,
        limit: int = 4,
        filters: Optional[RetrievalFilters] = None,
    ) -> List[Evidence]:
        if chunks is None:
            return []

        scored = []
        for chunk in chunks:
            if chunk.tenant_id != tenant_id:
                continue
            if not chunk_matches_filters(chunk, filters):
                continue
            score = keyword_score_for_chunk(query, chunk)
            if score <= 0:
                continue
            scored.append((score, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            _evidence_from_chunk(chunk, score, keyword_score=score, retrieval_mode="keyword")
            for score, chunk in scored[:limit]
        ]


class VectorRetriever:
    """In-memory vector retriever used for fast local tests and demos."""

    uses_store_backend = False

    def __init__(
        self,
        embedding_model: EmbeddingModel = DEFAULT_EMBEDDING_MODEL,
        min_score: float = 0.08,
    ) -> None:
        self.embedding_model = embedding_model
        self.min_score = min_score

    def search(
        self,
        tenant_id: str,
        query: str,
        chunks: Optional[Iterable[DocumentChunk]] = None,
        limit: int = 4,
        filters: Optional[RetrievalFilters] = None,
    ) -> List[Evidence]:
        if chunks is None:
            return []

        query_embedding = self.embedding_model.embed(query)
        if not any(query_embedding):
            return []

        scored = []
        for chunk in chunks:
            if chunk.tenant_id != tenant_id:
                continue
            if not chunk_matches_filters(chunk, filters):
                continue
            if not chunk.embedding:
                continue
            score = cosine_similarity(query_embedding, chunk.embedding)
            if score < self.min_score:
                continue
            scored.append((score, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            _evidence_from_chunk(chunk, score, vector_score=score, retrieval_mode="vector")
            for score, chunk in scored[:limit]
        ]


class PgVectorSearchStore(Protocol):
    def search_chunks_by_embedding(
        self,
        tenant_id: str,
        embedding: Sequence[float],
        limit: int = 4,
        filters: Optional[RetrievalFilters] = None,
    ) -> List[Evidence]:
        ...

    def search_chunks_by_keyword(
        self,
        tenant_id: str,
        query: str,
        limit: int = 4,
        filters: Optional[RetrievalFilters] = None,
    ) -> List[Evidence]:
        ...


class PgVectorRetriever:
    uses_store_backend = True

    def __init__(
        self,
        store: PgVectorSearchStore,
        embedding_model: EmbeddingModel = DEFAULT_EMBEDDING_MODEL,
        min_score: float = 0.08,
    ) -> None:
        self.store = store
        self.embedding_model = embedding_model
        self.min_score = min_score

    def search(
        self,
        tenant_id: str,
        query: str,
        chunks: Optional[Iterable[DocumentChunk]] = None,
        limit: int = 4,
        filters: Optional[RetrievalFilters] = None,
    ) -> List[Evidence]:
        del chunks
        query_embedding = self.embedding_model.embed(query)
        if not any(query_embedding):
            return []
        evidence = self.store.search_chunks_by_embedding(
            tenant_id,
            query_embedding,
            limit=limit,
            filters=filters,
        )
        return [item for item in evidence if item.score >= self.min_score]


class StoreKeywordRetriever:
    uses_store_backend = True

    def __init__(self, store: PgVectorSearchStore) -> None:
        self.store = store

    def search(
        self,
        tenant_id: str,
        query: str,
        chunks: Optional[Iterable[DocumentChunk]] = None,
        limit: int = 4,
        filters: Optional[RetrievalFilters] = None,
    ) -> List[Evidence]:
        del chunks
        return self.store.search_chunks_by_keyword(tenant_id, query, limit=limit, filters=filters)


class HybridRetriever:
    def __init__(
        self,
        vector_retriever: Retriever,
        keyword_retriever: Retriever,
        min_score: float = 0.12,
    ) -> None:
        self.vector_retriever = vector_retriever
        self.keyword_retriever = keyword_retriever
        self.min_score = min_score
        self.uses_store_backend = vector_retriever.uses_store_backend and keyword_retriever.uses_store_backend

    def search(
        self,
        tenant_id: str,
        query: str,
        chunks: Optional[Iterable[DocumentChunk]] = None,
        limit: int = 4,
        filters: Optional[RetrievalFilters] = None,
    ) -> List[Evidence]:
        candidate_limit = max(limit * 3, 8)
        vector_results = self.vector_retriever.search(
            tenant_id,
            query,
            chunks,
            limit=candidate_limit,
            filters=filters,
        )
        keyword_results = self.keyword_retriever.search(
            tenant_id,
            query,
            chunks,
            limit=candidate_limit,
            filters=filters,
        )

        merged: Dict[str, Evidence] = {}
        for item in vector_results:
            evidence = _copy_evidence(item)
            evidence.vector_score = max(evidence.vector_score, item.vector_score or item.score)
            merged[evidence.chunk_id] = evidence
        for item in keyword_results:
            evidence = merged.get(item.chunk_id) or _copy_evidence(item)
            evidence.keyword_score = max(evidence.keyword_score, item.keyword_score or item.score)
            merged[item.chunk_id] = evidence

        for evidence in merged.values():
            vector_score = max(0.0, evidence.vector_score)
            keyword_score = max(0.0, evidence.keyword_score)
            agreement_bonus = 0.12 if vector_score > 0 and keyword_score > 0 else 0.0
            evidence.score = round(min(1.0, (0.62 * vector_score) + (0.38 * keyword_score) + agreement_bonus), 3)
            if vector_score > 0 and keyword_score > 0:
                evidence.retrieval_mode = "hybrid"
            elif keyword_score > 0:
                evidence.retrieval_mode = "keyword"
            else:
                evidence.retrieval_mode = "vector"

        ranked = sorted(merged.values(), key=lambda item: item.score, reverse=True)
        return [item for item in ranked if item.score >= self.min_score][:limit]


def create_default_retriever(store: object, embedding_model: EmbeddingModel = DEFAULT_EMBEDDING_MODEL) -> Retriever:
    if hasattr(store, "search_chunks_by_embedding") and hasattr(store, "search_chunks_by_keyword"):
        vector = PgVectorRetriever(store, embedding_model=embedding_model)  # type: ignore[arg-type]
        keyword = StoreKeywordRetriever(store)  # type: ignore[arg-type]
        return HybridRetriever(vector, keyword)
    return HybridRetriever(VectorRetriever(embedding_model=embedding_model), KeywordRetriever())


def _evidence_from_chunk(
    chunk: DocumentChunk,
    score: float,
    *,
    keyword_score: float = 0.0,
    vector_score: float = 0.0,
    retrieval_mode: str = "unknown",
) -> Evidence:
    excerpt = " ".join(chunk.content.split())[:320]
    return Evidence(
        chunk_id=chunk.id,
        document_id=chunk.document_id,
        title=chunk.title,
        uri=chunk.uri,
        excerpt=excerpt,
        score=round(score, 3),
        source_type=chunk.source_type,
        product_line=chunk.product_line,
        version=chunk.version,
        required_permissions=list(chunk.required_permissions),
        valid_from=chunk.valid_from,
        valid_until=chunk.valid_until,
        source_system=chunk.source_system,
        keyword_score=round(keyword_score, 3),
        vector_score=round(vector_score, 3),
        retrieval_mode=retrieval_mode,
    )


def _copy_evidence(item: Evidence) -> Evidence:
    return Evidence(
        chunk_id=item.chunk_id,
        document_id=item.document_id,
        title=item.title,
        uri=item.uri,
        excerpt=item.excerpt,
        score=item.score,
        source_type=item.source_type,
        product_line=item.product_line,
        version=item.version,
        required_permissions=list(item.required_permissions),
        valid_from=item.valid_from,
        valid_until=item.valid_until,
        source_system=item.source_system,
        keyword_score=item.keyword_score,
        vector_score=item.vector_score,
        retrieval_mode=item.retrieval_mode,
    )


def _keyword_text_for_chunk(chunk: DocumentChunk) -> str:
    return " ".join(
        part
        for part in [
            chunk.title,
            chunk.source_type,
            chunk.product_line or "",
            chunk.version or "",
            " ".join(chunk.required_permissions),
            chunk.source_system or "",
            chunk.content,
        ]
        if part
    )


def _is_active(valid_from: Optional[str], valid_until: Optional[str], as_of: Optional[str]) -> bool:
    moment = _parse_datetime(as_of) or datetime.now(timezone.utc)
    starts_at = _parse_datetime(valid_from)
    ends_at = _parse_datetime(valid_until)
    if starts_at and starts_at > moment:
        return False
    if ends_at and ends_at < moment:
        return False
    return True


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    normalized = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _env(name: str, fallback: Optional[str] = None) -> str:
    value = os.getenv(name)
    if value is not None:
        return value
    return fallback or ""


def _normalize_embedding(vector: List[float], dimensions: int) -> List[float]:
    if len(vector) == dimensions:
        return vector
    if len(vector) > dimensions:
        return vector[:dimensions]
    return vector + ([0.0] * (dimensions - len(vector)))

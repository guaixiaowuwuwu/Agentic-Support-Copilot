from __future__ import annotations

import hashlib
import math
import re
from typing import Iterable, List, Optional, Protocol, Sequence

from .models import Document, DocumentChunk, Evidence

EMBEDDING_DIMENSIONS = 1536
TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)


def tokenize(text: str) -> set:
    return {token.lower() for token in TOKEN_RE.findall(text)}


def chunk_document(document: Document, max_chars: int = 700) -> List[DocumentChunk]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", document.content) if part.strip()]
    chunks: List[DocumentChunk] = []
    current = ""

    for paragraph in paragraphs or [document.content]:
        if len(current) + len(paragraph) + 2 <= max_chars:
            current = f"{current}\n\n{paragraph}".strip()
            continue

        if current:
            chunks.append(
                DocumentChunk(
                    document_id=document.id,
                    tenant_id=document.tenant_id,
                    title=document.title,
                    source_type=document.source_type,
                    uri=document.uri,
                    content=current,
                    chunk_index=len(chunks),
                )
            )
        current = paragraph[:max_chars]

    if current:
        chunks.append(
            DocumentChunk(
                document_id=document.id,
                tenant_id=document.tenant_id,
                title=document.title,
                source_type=document.source_type,
                uri=document.uri,
                content=current,
                chunk_index=len(chunks),
            )
        )

    return chunks


def embedding_text_for_chunk(chunk: DocumentChunk) -> str:
    return f"{chunk.title}\n{chunk.source_type}\n{chunk.content}"


def _embedding_tokens(text: str) -> List[str]:
    tokens = [token.lower() for token in TOKEN_RE.findall(text)]
    bigrams = [f"{left}::{right}" for left, right in zip(tokens, tokens[1:])]
    return tokens + bigrams


class EmbeddingModel(Protocol):
    dimensions: int

    def embed(self, text: str) -> List[float]:
        ...


class HashingEmbeddingModel:
    """Deterministic local embedding model for private MVP ingestion and tests."""

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


DEFAULT_EMBEDDING_MODEL = HashingEmbeddingModel()


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


class Retriever(Protocol):
    uses_store_backend: bool

    def search(
        self,
        tenant_id: str,
        query: str,
        chunks: Optional[Iterable[DocumentChunk]] = None,
        limit: int = 4,
    ) -> List[Evidence]:
        ...


class KeywordRetriever:
    """Small deterministic retriever used by the MVP and tests."""

    uses_store_backend = False

    def search(
        self,
        tenant_id: str,
        query: str,
        chunks: Optional[Iterable[DocumentChunk]] = None,
        limit: int = 4,
    ) -> List[Evidence]:
        if chunks is None:
            return []

        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        scored = []
        for chunk in chunks:
            if chunk.tenant_id != tenant_id:
                continue
            chunk_tokens = tokenize(f"{chunk.title} {chunk.content}")
            overlap = query_tokens.intersection(chunk_tokens)
            if not overlap:
                continue

            score = len(overlap) / max(len(query_tokens), 1)
            scored.append((score, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        evidence = []
        for score, chunk in scored[:limit]:
            excerpt = " ".join(chunk.content.split())[:320]
            evidence.append(
                Evidence(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    title=chunk.title,
                    uri=chunk.uri,
                    excerpt=excerpt,
                    score=round(score, 3),
                )
            )
        return evidence


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
            if not chunk.embedding:
                continue
            chunk_embedding = chunk.embedding
            score = cosine_similarity(query_embedding, chunk_embedding)
            if score < self.min_score:
                continue
            scored.append((score, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [_evidence_from_chunk(chunk, score) for score, chunk in scored[:limit]]


class PgVectorSearchStore(Protocol):
    def search_chunks_by_embedding(
        self,
        tenant_id: str,
        embedding: Sequence[float],
        limit: int = 4,
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
    ) -> List[Evidence]:
        del chunks
        query_embedding = self.embedding_model.embed(query)
        if not any(query_embedding):
            return []
        evidence = self.store.search_chunks_by_embedding(tenant_id, query_embedding, limit=limit)
        return [item for item in evidence if item.score >= self.min_score]


def create_default_retriever(store: object) -> Retriever:
    if hasattr(store, "search_chunks_by_embedding"):
        return PgVectorRetriever(store)  # type: ignore[arg-type]
    return VectorRetriever()


def _evidence_from_chunk(chunk: DocumentChunk, score: float) -> Evidence:
    excerpt = " ".join(chunk.content.split())[:320]
    return Evidence(
        chunk_id=chunk.id,
        document_id=chunk.document_id,
        title=chunk.title,
        uri=chunk.uri,
        excerpt=excerpt,
        score=round(score, 3),
    )

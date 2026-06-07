from __future__ import annotations

import re
from typing import Iterable, List

from .models import Document, DocumentChunk, Evidence

TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


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


class KeywordRetriever:
    """Small deterministic retriever used by the MVP and tests."""

    def search(self, tenant_id: str, query: str, chunks: Iterable[DocumentChunk], limit: int = 4) -> List[Evidence]:
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


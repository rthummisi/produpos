"""
RAG service for ProdUPOS.

Embeds repo file chunks via Ollama (nomic-embed-text) and stores them in
the local SQLite database as JSON-serialised float vectors.  Cosine
similarity is computed in Python so no pgvector extension is required.

Why RAG?
  repo_scanner currently passes every file to the LLM.  For large repos
  that blows context limits and costs money.  RAG lets feature_planner
  receive only the top-K chunks that are relevant to the proposed feature.
"""

import hashlib
import json
import math
import os
from typing import Optional

import httpx
from sqlalchemy.orm import Session

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text")


# ── Embedding ─────────────────────────────────────────────────────────────────

def embed_text_sync(text_content: str) -> Optional[list]:
    """Call Ollama /api/embed synchronously.  Returns None on any error."""
    base_url = OLLAMA_BASE_URL.rstrip("/")
    try:
        with httpx.Client(base_url=base_url, timeout=15) as client:
            r = client.post(
                "/api/embed",
                json={"model": EMBED_MODEL, "input": text_content[:8000]},
            )
            r.raise_for_status()
            embeddings = r.json().get("embeddings", [])
            return [float(v) for v in embeddings[0]] if embeddings else None
    except Exception:
        return None


# ── Chunking ──────────────────────────────────────────────────────────────────

def chunk_file(file_path: str, content: str, chunk_size: int = 1500) -> list:
    """Split a file into overlapping line-based chunks.

    Each chunk is prefixed with the file path so the LLM knows the source.
    """
    lines = content.split("\n")
    # ~80 chars per line estimate; step by chunk_size // 80 lines, overlap 10
    step = max(1, chunk_size // 80)
    chunks = []
    for i in range(0, len(lines), step):
        chunk_lines = lines[i : i + step + 10]
        chunk_text = f"# File: {file_path}\n" + "\n".join(chunk_lines)
        chunks.append(
            {"file_path": file_path, "content": chunk_text, "chunk_index": i}
        )
    return chunks


# ── Cosine similarity ─────────────────────────────────────────────────────────

def _cosine_similarity(a: list, b: list) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


# ── Indexing ──────────────────────────────────────────────────────────────────

def index_repo(db: Session, product_id: str, files: dict) -> int:
    """Embed and store all file chunks for a product.

    Runs synchronously so it can be called from asyncio.create_task via
    run_in_executor, or directly from a background thread.

    Returns the number of chunks stored.
    """
    from ..models import CodeChunk  # local import avoids circular deps

    stored = 0
    for file_path, content in files.items():
        if not content or len(content) < 50:
            continue
        for chunk in chunk_file(file_path, content):
            embedding = embed_text_sync(chunk["content"])
            if embedding is None:
                continue
            content_hash = hashlib.md5(chunk["content"].encode()).hexdigest()

            # Upsert: update if (product_id, file_path, chunk_index) exists
            existing = (
                db.query(CodeChunk)
                .filter_by(
                    product_id=product_id,
                    file_path=chunk["file_path"],
                    chunk_index=chunk["chunk_index"],
                )
                .first()
            )
            if existing:
                existing.content = chunk["content"]
                existing.content_hash = content_hash
                existing.embedding_json = json.dumps(embedding)
            else:
                row = CodeChunk(
                    product_id=product_id,
                    file_path=chunk["file_path"],
                    content=chunk["content"],
                    chunk_index=chunk["chunk_index"],
                    content_hash=content_hash,
                    embedding_json=json.dumps(embedding),
                )
                db.add(row)
            stored += 1

    db.commit()
    return stored


# ── Retrieval ─────────────────────────────────────────────────────────────────

def retrieve_relevant_code(
    db: Session, product_id: str, query: str, limit: int = 10
) -> list:
    """Find the most relevant code chunks for a given feature query.

    Returns a list of content strings ordered by descending cosine similarity.
    Falls back to an empty list if Ollama is unavailable.
    """
    from ..models import CodeChunk  # local import avoids circular deps

    query_embedding = embed_text_sync(query)
    if not query_embedding:
        return []

    chunks = (
        db.query(CodeChunk)
        .filter(CodeChunk.product_id == product_id)
        .all()
    )
    if not chunks:
        return []

    scored = []
    for chunk in chunks:
        try:
            vec = json.loads(chunk.embedding_json)
            score = _cosine_similarity(query_embedding, vec)
            scored.append((score, chunk.content))
        except Exception:
            continue

    scored.sort(key=lambda x: x[0], reverse=True)
    return [content for _, content in scored[:limit]]

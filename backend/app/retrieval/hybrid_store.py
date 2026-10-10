"""
Hybrid retrieval engine: Dense (embeddings) + Sparse (BM25) with rank fusion.
Supports metadata filtering and document attribution.
Pinecone-compatible interface; POC defaults to in-memory for zero-credential demos.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from rank_bm25 import BM25Okapi

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _simple_embed(text: str, dim: int = 64) -> np.ndarray:
    """
    Deterministic bag-of-hashes embedding for offline / no-key demos.
    In production replace with OpenAI / sentence-transformers.
    """
    vec = np.zeros(dim, dtype=np.float32)
    tokens = _tokenize(text)
    for t in tokens:
        h = int(hashlib.md5(t.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec


class HybridKnowledgeStore:
    """
    In-memory hybrid store that demonstrates:
    - Dense vector search
    - Sparse BM25
    - Hybrid ranking (alpha-weighted)
    - Metadata filtering (department, document_type, access_level, date)
    - Document attribution
    """

    def __init__(self):
        self.chunks: List[Dict[str, Any]] = []
        self.corpus_tokens: List[List[str]] = []
        self.bm25: Optional[BM25Okapi] = None
        self.embeddings: Optional[np.ndarray] = None
        self._ready = False
        self._use_openai_embeddings = False
        self._openai_client = None

    @property
    def ready(self) -> bool:
        return self._ready

    def _try_init_openai(self):
        settings = get_settings()
        if settings.openai_api_key:
            try:
                from openai import OpenAI
                self._openai_client = OpenAI(api_key=settings.openai_api_key)
                self._use_openai_embeddings = True
                logger.info("Using OpenAI embeddings for dense retrieval")
            except Exception as e:
                logger.warning("OpenAI embeddings unavailable: %s – falling back to hash embeddings", e)

    def _embed(self, texts: List[str]) -> np.ndarray:
        if self._use_openai_embeddings and self._openai_client:
            try:
                settings = get_settings()
                resp = self._openai_client.embeddings.create(
                    model=settings.openai_embedding_model,
                    input=texts,
                )
                return np.array([d.embedding for d in resp.data], dtype=np.float32)
            except Exception as e:
                logger.warning("OpenAI embed failed: %s – using hash fallback", e)
        return np.vstack([_simple_embed(t) for t in texts])

    def load_documents(self, docs_path: str) -> int:
        """Load markdown / text files and chunk them."""
        path = Path(docs_path)
        if not path.exists():
            logger.warning("Docs path %s does not exist", docs_path)
            return 0

        self._try_init_openai()
        all_chunks: List[Dict[str, Any]] = []

        for fp in sorted(path.glob("**/*")):
            if fp.suffix.lower() not in {".md", ".txt", ".rst"}:
                continue
            try:
                text = fp.read_text(encoding="utf-8")
            except Exception:
                continue

            meta = self._extract_metadata(text, fp.name)
            # Simple paragraph / heading aware chunking
            parts = re.split(r"\n(?=#{1,3}\s)", text)
            if len(parts) == 1:
                parts = [text[i : i + 1200] for i in range(0, len(text), 1000)]

            for i, part in enumerate(parts):
                part = part.strip()
                if len(part) < 40:
                    continue
                chunk_id = str(uuid.uuid4())
                all_chunks.append(
                    {
                        "id": chunk_id,
                        "content": part,
                        "source": fp.name,
                        "metadata": {**meta, "chunk_index": i},
                    }
                )

        if not all_chunks:
            logger.warning("No chunks loaded")
            return 0

        self.chunks = all_chunks
        self.corpus_tokens = [_tokenize(c["content"]) for c in self.chunks]
        self.bm25 = BM25Okapi(self.corpus_tokens)

        texts = [c["content"] for c in self.chunks]
        self.embeddings = self._embed(texts)
        self._ready = True
        logger.info("Loaded %d chunks from %s", len(self.chunks), docs_path)
        return len(self.chunks)

    def _extract_metadata(self, text: str, filename: str) -> Dict[str, Any]:
        meta: Dict[str, Any] = {
            "department": "general",
            "document_type": "document",
            "access_level": "internal",
            "created_date": "2025-01-01",
            "filename": filename,
        }
        # Parse front-matter style lines from our mock docs
        for line in text.splitlines()[:30]:
            m = re.match(r"\*\*([^*]+):\*\*\s*(.+)", line)
            if not m:
                continue
            key = m.group(1).strip().lower().replace(" ", "_")
            val = m.group(2).strip()
            if key in ("department", "document_type", "access_level", "created_date", "severity"):
                meta[key] = val.lower() if key != "created_date" else val
            if key == "incident_id":
                meta["incident_id"] = val
        # Infer from filename
        if "incident" in filename.lower():
            meta["document_type"] = "incident"
        elif "runbook" in filename.lower():
            meta["document_type"] = "runbook"
        elif "architecture" in filename.lower():
            meta["document_type"] = "architecture"
        elif "policy" in filename.lower():
            meta["document_type"] = "policy"
        if "payment" in filename.lower():
            meta["department"] = "payments"
        return meta

    def search(
        self,
        query: str,
        top_k: int = 6,
        filters: Optional[Dict[str, Any]] = None,
        alpha: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        if not self._ready or not self.chunks:
            return []

        settings = get_settings()
        alpha = alpha if alpha is not None else settings.hybrid_alpha

        # Sparse scores
        q_tokens = _tokenize(query)
        sparse_scores = np.array(self.bm25.get_scores(q_tokens), dtype=np.float32)
        if sparse_scores.max() > 0:
            sparse_scores = sparse_scores / (sparse_scores.max() + 1e-9)

        # Dense scores
        q_emb = self._embed([query])[0]
        dense_scores = self.embeddings @ q_emb
        if dense_scores.max() > 0:
            dense_scores = dense_scores / (dense_scores.max() + 1e-9)

        hybrid = alpha * dense_scores + (1 - alpha) * sparse_scores

        # Apply metadata filters
        candidate_indices = list(range(len(self.chunks)))
        if filters:
            candidate_indices = [
                i
                for i in candidate_indices
                if self._match_filters(self.chunks[i]["metadata"], filters)
            ]

        ranked = sorted(candidate_indices, key=lambda i: hybrid[i], reverse=True)[:top_k]

        results = []
        for i in ranked:
            c = self.chunks[i].copy()
            c["score"] = float(hybrid[i])
            c["dense_score"] = float(dense_scores[i])
            c["sparse_score"] = float(sparse_scores[i])
            results.append(c)
        return results

    def _match_filters(self, meta: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        for k, v in filters.items():
            if v is None:
                continue
            if isinstance(v, list):
                if meta.get(k) not in v:
                    return False
            else:
                if str(meta.get(k, "")).lower() != str(v).lower():
                    return False
        return True


# Singleton
_store: Optional[HybridKnowledgeStore] = None


def get_knowledge_store() -> HybridKnowledgeStore:
    global _store
    if _store is None:
        _store = HybridKnowledgeStore()
        settings = get_settings()
        # Resolve path relative to project root
        docs = settings.mock_docs_path
        if not os.path.isabs(docs):
            # Try common locations
            candidates = [
                docs,
                os.path.join(os.getcwd(), docs),
                os.path.join(os.path.dirname(__file__), "..", "..", "..", docs),
            ]
            for c in candidates:
                if os.path.isdir(c):
                    docs = c
                    break
        _store.load_documents(docs)
    return _store

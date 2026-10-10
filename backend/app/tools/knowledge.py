"""Knowledge Search Tool – wraps hybrid retrieval with RBAC filtering."""
from typing import Any, Dict, List, Optional

from app.models.schemas import UserRole
from app.retrieval.hybrid_store import get_knowledge_store
from app.security.guardrails import filter_chunks_by_access


async def knowledge_search(
    query: str,
    top_k: int = 6,
    department: Optional[str] = None,
    document_type: Optional[str] = None,
    role: UserRole = UserRole.VIEWER,
) -> Dict[str, Any]:
    store = get_knowledge_store()
    filters: Dict[str, Any] = {}
    if department:
        filters["department"] = department
    if document_type:
        filters["document_type"] = document_type

    raw = store.search(query, top_k=top_k * 2, filters=filters or None)
    filtered = filter_chunks_by_access(raw, role)[:top_k]

    return {
        "results": [
            {
                "id": r["id"],
                "content": r["content"][:1500],
                "source": r["source"],
                "score": r["score"],
                "dense_score": r.get("dense_score"),
                "sparse_score": r.get("sparse_score"),
                "metadata": r.get("metadata", {}),
            }
            for r in filtered
        ],
        "count": len(filtered),
        "query": query,
    }

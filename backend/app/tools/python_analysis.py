"""
Python Analysis Tool – performs structured analysis on retrieved data.
Used by the Research agent for aggregation, root-cause frequency counts, etc.
Safety: only executes a restricted set of pure analysis functions; no arbitrary code exec.
"""
from collections import Counter
from typing import Any, Dict, List, Optional


async def python_analysis(
    operation: str,
    data: List[Dict[str, Any]],
    field: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Supported operations:
    - count_by_field: frequency of values in a field
    - extract_root_causes: naive extraction of "root cause" style sentences
    - summarize_severities: count by severity
    - list_recurring_themes: look for repeated phrases across texts
    """
    if not data:
        return {"result": None, "message": "No data provided"}

    op = operation.lower().strip()

    if op == "count_by_field" and field:
        values = [str(item.get(field, item.get("metadata", {}).get(field, "unknown"))) for item in data]
        counts = dict(Counter(values))
        return {"operation": op, "field": field, "counts": counts}

    if op == "summarize_severities":
        sevs = []
        for item in data:
            meta = item.get("metadata") or {}
            sevs.append(meta.get("severity") or item.get("severity") or "unknown")
        return {"operation": op, "counts": dict(Counter(sevs))}

    if op == "extract_root_causes":
        causes = []
        for item in data:
            text = item.get("content", "")
            # Simple heuristic: lines after "Root Cause"
            lines = text.splitlines()
            capture = False
            buf = []
            for line in lines:
                if "root cause" in line.lower():
                    capture = True
                    continue
                if capture:
                    if line.startswith("#") or line.startswith("##"):
                        break
                    if line.strip():
                        buf.append(line.strip())
            if buf:
                causes.append({"source": item.get("source"), "root_cause": " ".join(buf)[:500]})
        return {"operation": op, "root_causes": causes, "count": len(causes)}

    if op == "list_recurring_themes":
        # Look for known recurring phrases from our domain
        themes = [
            "connection pool",
            "memory leak",
            "idempotency",
            "certificate",
            "timeout",
            "reconciliation",
        ]
        found = Counter()
        for item in data:
            text = (item.get("content") or "").lower()
            for t in themes:
                if t in text:
                    found[t] += 1
        return {"operation": op, "themes": dict(found.most_common())}

    return {"error": f"Unsupported operation: {operation}", "supported": [
        "count_by_field", "summarize_severities", "extract_root_causes", "list_recurring_themes"
    ]}

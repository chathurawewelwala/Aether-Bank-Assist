"""
Simple MCP-style enterprise data tools.
In a full deployment these would be exposed by a dedicated MCP server.
Here they are in-process async callables that the agent can invoke.
"""
from typing import Any, Dict, List, Optional

# Dummy enterprise data
EMPLOYEE_DIRECTORY = [
    {"id": "E001", "name": "Priya Sharma", "title": "Payments SRE", "team": "Payments Platform", "email": "priya.sharma@aether.bank"},
    {"id": "E002", "name": "Arjun Mehta", "title": "Staff Engineer", "team": "Payments Core", "email": "arjun.mehta@aether.bank"},
    {"id": "E003", "name": "Neha Gupta", "title": "Incident Commander", "team": "SRE", "email": "neha.gupta@aether.bank"},
    {"id": "E004", "name": "Rahul Verma", "title": "Product Manager", "team": "Payments Product", "email": "rahul.verma@aether.bank"},
]

SERVICE_CATALOG = [
    {"id": "SVC-PAYFLOW", "name": "PayFlow Orchestrator", "owner": "Payments Platform", "tier": "Tier-0", "oncall": "payments-oncall"},
    {"id": "SVC-RECON", "name": "Reconciliation Service", "owner": "Payments Core", "tier": "Tier-1", "oncall": "payments-oncall"},
    {"id": "SVC-UPI", "name": "UPI Adapter", "owner": "Payments Core", "tier": "Tier-0", "oncall": "payments-oncall"},
    {"id": "SVC-FRAUD", "name": "Fraud Engine", "owner": "Risk", "tier": "Tier-0", "oncall": "risk-oncall"},
]

INCIDENT_RECORDS = [
    {"id": "INC-2025-0312", "title": "Payment Gateway Outage", "severity": "SEV-1", "status": "resolved", "date": "2025-03-12"},
    {"id": "INC-2025-0108", "title": "Settlement File Delay", "severity": "SEV-2", "status": "resolved", "date": "2025-01-08"},
    {"id": "INC-2024-1122", "title": "Intermittent UPI Failures", "severity": "SEV-2", "status": "resolved", "date": "2024-11-22"},
]


async def mcp_employee_directory(query: Optional[str] = None) -> Dict[str, Any]:
    if not query:
        return {"employees": EMPLOYEE_DIRECTORY, "count": len(EMPLOYEE_DIRECTORY)}
    q = query.lower()
    matched = [e for e in EMPLOYEE_DIRECTORY if q in e["name"].lower() or q in e["team"].lower() or q in e["title"].lower()]
    return {"employees": matched, "count": len(matched), "query": query}


async def mcp_service_catalog(query: Optional[str] = None) -> Dict[str, Any]:
    if not query:
        return {"services": SERVICE_CATALOG, "count": len(SERVICE_CATALOG)}
    q = query.lower()
    matched = [s for s in SERVICE_CATALOG if q in s["name"].lower() or q in s["owner"].lower()]
    return {"services": matched, "count": len(matched), "query": query}


async def mcp_incident_records(query: Optional[str] = None, severity: Optional[str] = None) -> Dict[str, Any]:
    records = INCIDENT_RECORDS
    if severity:
        records = [r for r in records if r["severity"].lower() == severity.lower()]
    if query:
        q = query.lower()
        records = [r for r in records if q in r["title"].lower() or q in r["id"].lower()]
    return {"incidents": records, "count": len(records)}

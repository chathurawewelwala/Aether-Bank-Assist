"""
LangGraph node implementations.
Demonstrates multi-agent collaboration, RLM-style recursive decomposition,
tool calling, validation, and human-in-the-loop hooks.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List

from app.agents.llm import get_llm
from app.agents.state import AgentGraphState
from app.models.schemas import (
    AgentActivityEvent,
    AgentNode,
    AgentStateLabel,
    Citation,
    ToolCallRecord,
    UserRole,
)
from app.tools.registry import execute_tool

logger = logging.getLogger(__name__)


def _event(node: AgentNode, state: AgentStateLabel, message: str, details: Dict = None) -> AgentActivityEvent:
    return AgentActivityEvent(node=node, state=state, message=message, details=details or {})


async def supervisor_node(state: AgentGraphState) -> Dict[str, Any]:
    """
    Supervisor: intent understanding, task decomposition, routing.
    """
    events = [_event(AgentNode.SUPERVISOR, AgentStateLabel.THINKING, "Analyzing user intent and building plan")]

    llm = get_llm()
    history_snippet = "\n".join(f"{m['role']}: {m['content'][:200]}" for m in state.get("history", [])[-4:])
    prompt = f"""You are the Supervisor agent of Aether Assistant.
Classify the user request and produce a short JSON plan.

User message: {state['user_message']}
Recent history:
{history_snippet}
Memory summary: {state.get('memory_summary') or 'none'}

Respond with JSON only:
{{
  "intent": "search|summarize|investigate|lookup|general",
  "needs_research": true/false,
  "sub_queries": ["query1", "query2"],
  "tools_needed": ["knowledge_search", ...],
  "plan": ["step1", "step2"],
  "requires_approval": false
}}
If the question asks to summarize many incidents / find recurring patterns over time, set needs_research=true and create multiple sub_queries.
Set requires_approval=true when the user asks to use enterprise tools (employee directory, service catalog, incidents), or explicitly requests human approval / HITL.
"""
    raw = await llm.chat(
        [{"role": "system", "content": "You output only valid JSON."}, {"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=500,
    )

    intent = "general"
    needs_research = False
    sub_queries = [state["user_message"]]
    tools_needed = ["knowledge_search"]
    plan = ["Retrieve relevant documents", "Generate answer"]
    requires_approval = False
    msg_lower = state["user_message"].lower()

    try:
        # Extract JSON if wrapped in markdown
        text = raw.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text)
        intent = data.get("intent", intent)
        needs_research = bool(data.get("needs_research", False))
        sub_queries = data.get("sub_queries") or sub_queries
        tools_needed = data.get("tools_needed") or tools_needed
        plan = data.get("plan") or plan
        requires_approval = bool(data.get("requires_approval", False))
    except Exception:
        # Heuristic fallback for offline mode
        if any(w in msg_lower for w in ["summarize", "recurring", "root cause", "all outage", "last year", "pattern"]):
            needs_research = True
            sub_queries = [
                "payment outage incident reports",
                "payment failure root causes",
                "settlement delay incidents",
                "recurring themes connection pool memory leak",
            ]
            plan = [
                "Decompose into sub-queries (RLM)",
                "Retrieve batches of documents",
                "Analyze each batch for root causes",
                "Aggregate recurring themes",
                "Generate final summary with citations",
            ]
            intent = "investigate"

    # Deterministic HITL triggers (demo + safety) — always apply after LLM/heuristics
    if any(
        k in msg_lower
        for k in (
            "hitl",
            "human approval",
            "require approval",
            "needs approval",
            "employee directory",
            "who is on the",
            "service catalog",
            "list incidents",
        )
    ):
        requires_approval = True
        if "employee" in msg_lower or "who is" in msg_lower:
            tools_needed = list(set(tools_needed + ["mcp_employee_directory"]))
        if "service catalog" in msg_lower:
            tools_needed = list(set(tools_needed + ["mcp_service_catalog"]))
        if "incident" in msg_lower and "list" in msg_lower:
            tools_needed = list(set(tools_needed + ["mcp_incident_records"]))

    # To-do intents (all roles can manage their own list)
    if any(
        k in msg_lower
        for k in (
            "to-do", "todo", "to do", "task list", "my tasks",
            "add a task", "add task", "create a task", "create task",
            "mark done", "complete task", "finish task", "list my",
            "show my tasks", "delete task", "remove task",
        )
    ):
        if any(k in msg_lower for k in ("list", "show", "what are", "my tasks", "my to")):
            tools_needed = list(dict.fromkeys(tools_needed + ["todo_list"]))
        elif any(k in msg_lower for k in ("done", "complete", "finish", "mark")):
            tools_needed = list(dict.fromkeys(tools_needed + ["todo_list", "todo_complete"]))
        elif any(k in msg_lower for k in ("delete", "remove")):
            tools_needed = list(dict.fromkeys(tools_needed + ["todo_list", "todo_delete"]))
        elif any(k in msg_lower for k in ("add", "create", "new task", "remind me")):
            tools_needed = list(dict.fromkeys(tools_needed + ["todo_create"]))
        else:
            tools_needed = list(dict.fromkeys(tools_needed + ["todo_list"]))
        intent = "todo"

    # Already approved in a resumed run — do not ask again
    if state.get("approval_granted") is True:
        requires_approval = False

    events.append(
        _event(
            AgentNode.SUPERVISOR,
            AgentStateLabel.THINKING,
            f"Intent={intent}, research={needs_research}, approval={requires_approval}, sub_queries={len(sub_queries)}",
            {"intent": intent, "plan": plan, "sub_queries": sub_queries, "requires_approval": requires_approval},
        )
    )

    return {
        "intent": intent,
        "needs_research": needs_research,
        "sub_queries": sub_queries,
        "needs_tools": tools_needed,
        "plan": plan,
        "current_step": 0,
        "requires_approval": requires_approval,
        "current_node": AgentNode.SUPERVISOR.value,
        "activity": events,
    }


async def human_approval_node(state: AgentGraphState) -> Dict[str, Any]:
    """
    Human-in-the-loop gate.
    If approval is required and not yet granted, pause the graph and ask the user.
    If already granted (or not required), pass through to tools.
    """
    needs = bool(state.get("requires_approval"))
    granted = state.get("approval_granted")

    if needs and granted is not True:
        events = [
            _event(
                AgentNode.HUMAN_APPROVAL,
                AgentStateLabel.WAITING_APPROVAL,
                "Paused for human approval before running enterprise tools",
                {
                    "tools": state.get("needs_tools") or [],
                    "reason": "Sensitive tool use requires analyst/admin confirmation",
                },
            )
        ]
        return {
            "current_node": AgentNode.HUMAN_APPROVAL.value,
            "requires_approval": True,
            "approval_granted": None,
            "final_answer": (
                "This action needs human approval before I can run enterprise tools "
                f"({', '.join(state.get('needs_tools') or ['tools'])}).\n\n"
                "Click **Approve** to continue or **Reject** to cancel."
            ),
            "validation_passed": True,
            "activity": events,
        }

    events = [
        _event(
            AgentNode.HUMAN_APPROVAL,
            AgentStateLabel.COMPLETE,
            "Human approval granted — continuing to tools" if granted else "No approval required — continuing",
        )
    ]
    return {
        "current_node": AgentNode.HUMAN_APPROVAL.value,
        "activity": events,
    }


async def retrieval_node(state: AgentGraphState) -> Dict[str, Any]:
    """Retrieval agent: hybrid search with optional filters from intent."""
    events = [_event(AgentNode.RETRIEVAL, AgentStateLabel.RETRIEVING, "Starting hybrid dense+sparse search")]

    role = UserRole(state.get("user_role", "viewer"))
    query = state["user_message"]
    # Prefer first sub-query if research mode
    if state.get("sub_queries"):
        query = state["sub_queries"][0]

    start = time.perf_counter()
    result = await execute_tool(
        "knowledge_search",
        {"query": query, "top_k": 8},
        role,
    )
    latency = (time.perf_counter() - start) * 1000

    chunks = []
    if result.get("status") == "success":
        chunks = result["result"].get("results", [])
        events.append(
            _event(
                AgentNode.RETRIEVAL,
                AgentStateLabel.RETRIEVING,
                f"Retrieved {len(chunks)} chunks (hybrid ranking)",
                {
                    "count": len(chunks),
                    "latency_ms": round(latency, 1),
                    "sources": list({c["source"] for c in chunks}),
                },
            )
        )
    else:
        events.append(
            _event(AgentNode.RETRIEVAL, AgentStateLabel.ERROR, f"Retrieval failed: {result.get('error')}")
        )

    tool_rec = ToolCallRecord(
        tool_name="knowledge_search",
        arguments={"query": query, "top_k": 8},
        result_preview=f"{len(chunks)} chunks" if chunks else result.get("error"),
        status="success" if chunks else "error",
        latency_ms=round(latency, 1),
    )

    return {
        "retrieved_chunks": chunks,
        "current_node": AgentNode.RETRIEVAL.value,
        "activity": events,
        "tool_calls": [tool_rec],
        "tool_results": [result],
    }


async def research_node(state: AgentGraphState) -> Dict[str, Any]:
    """
    Research agent – demonstrates Recursive Language Model (RLM) concepts:
    1. Explore via multiple targeted sub-queries (not loading entire corpus)
    2. Retrieve in batches
    3. Analyze each batch with python_analysis tool
    4. Aggregate findings
    """
    events = [
        _event(
            AgentNode.RESEARCH,
            AgentStateLabel.RESEARCHING,
            "RLM: decomposing research into targeted sub-queries and batch analysis",
        )
    ]
    role = UserRole(state.get("user_role", "viewer"))
    sub_queries = state.get("sub_queries") or [state["user_message"]]
    all_chunks: List[Dict] = list(state.get("retrieved_chunks") or [])
    findings: List[Dict] = []

    for i, sq in enumerate(sub_queries[:4]):  # bound recursion depth for POC
        events.append(
            _event(AgentNode.RESEARCH, AgentStateLabel.RESEARCHING, f"Sub-query [{i+1}/{len(sub_queries)}]: {sq[:80]}")
        )
        start = time.perf_counter()
        res = await execute_tool("knowledge_search", {"query": sq, "top_k": 5}, role)
        latency = (time.perf_counter() - start) * 1000
        batch = []
        if res.get("status") == "success":
            batch = res["result"].get("results", [])
            # Dedupe by id
            existing_ids = {c["id"] for c in all_chunks}
            for c in batch:
                if c["id"] not in existing_ids:
                    all_chunks.append(c)
                    existing_ids.add(c["id"])

        # Analyze batch for root causes / themes (RLM recursive step)
        analysis = await execute_tool(
            "python_analysis",
            {"operation": "extract_root_causes", "data": batch},
            role,
        )
        theme_analysis = await execute_tool(
            "python_analysis",
            {"operation": "list_recurring_themes", "data": batch},
            role,
        )
        findings.append(
            {
                "sub_query": sq,
                "chunk_count": len(batch),
                "root_causes": (analysis.get("result") or {}).get("root_causes", []),
                "themes": (theme_analysis.get("result") or {}).get("themes", {}),
                "latency_ms": round(latency, 1),
            }
        )
        events.append(
            _event(
                AgentNode.RESEARCH,
                AgentStateLabel.RESEARCHING,
                f"Batch {i+1} analyzed: {len(batch)} chunks, themes={list((theme_analysis.get('result') or {}).get('themes', {}).keys())}",
            )
        )

    # Aggregate across batches
    agg = await execute_tool(
        "python_analysis",
        {"operation": "list_recurring_themes", "data": all_chunks},
        role,
    )
    events.append(
        _event(
            AgentNode.RESEARCH,
            AgentStateLabel.RESEARCHING,
            "RLM aggregation complete",
            {"total_chunks": len(all_chunks), "aggregated_themes": (agg.get("result") or {}).get("themes")},
        )
    )

    return {
        "retrieved_chunks": all_chunks,
        "research_findings": findings,
        "current_node": AgentNode.RESEARCH.value,
        "activity": events,
        "tool_results": findings,
    }


async def tool_executor_node(state: AgentGraphState) -> Dict[str, Any]:
    """Execute any additional MCP / analysis / to-do tools requested by supervisor."""
    events = [_event(AgentNode.TOOL_EXECUTOR, AgentStateLabel.CALLING_TOOL, "Evaluating additional tools")]
    role = UserRole(state.get("user_role", "viewer"))
    username = state.get("username") or "unknown"
    tools = [t for t in state.get("needs_tools", []) if t != "knowledge_search"]
    results = []
    tool_records = []
    msg = state.get("user_message") or ""

    for tname in tools:
        args: Dict[str, Any] = {}
        if tname.startswith("mcp_"):
            args["query"] = msg[:100]
        elif tname == "python_analysis":
            args = {"operation": "list_recurring_themes", "data": state.get("retrieved_chunks") or []}
        elif tname == "todo_list":
            args = {}
            if "done" in msg.lower() and "open" not in msg.lower():
                args["status"] = "done"
            elif "open" in msg.lower():
                args["status"] = "open"
        elif tname == "todo_create":
            # Extract title after common phrases
            title = msg
            for prefix in (
                "add a to-do", "add a todo", "add todo", "add a task", "add task",
                "create a to-do", "create a todo", "create todo", "create a task", "create task",
                "remind me to", "new task:", "todo:", "to-do:",
            ):
                if prefix in msg.lower():
                    idx = msg.lower().index(prefix) + len(prefix)
                    title = msg[idx:].strip(" :,-")
                    break
            args = {"title": title[:200] or msg[:200], "priority": "medium"}
            if "urgent" in msg.lower() or "high priority" in msg.lower():
                args["priority"] = "high"
        elif tname in ("todo_complete", "todo_delete", "todo_update"):
            # List first is usually also requested; complete/delete needs id from prior list in same turn
            args = {"todo_id": ""}  # filled below if we have list results
        elif tname.startswith("todo_"):
            args = {}

        # If complete/delete and we already listed todos in this loop, pick first open match
        if tname in ("todo_complete", "todo_delete") and not args.get("todo_id"):
            for prev in results:
                todos = (prev.get("result") or {}).get("todos") or []
                open_ones = [x for x in todos if x.get("status") == "open"]
                target = open_ones[0] if open_ones else (todos[0] if todos else None)
                if target:
                    args["todo_id"] = target["id"]
                    break

        start = time.perf_counter()
        res = await execute_tool(tname, args, role, username=username)
        latency = (time.perf_counter() - start) * 1000
        results.append(res)
        tool_records.append(
            ToolCallRecord(
                tool_name=tname,
                arguments=args,
                result_preview=str(res.get("result") or res.get("error"))[:200],
                status=res.get("status", "error"),
                latency_ms=round(latency, 1),
                error=res.get("error"),
            )
        )
        events.append(
            _event(
                AgentNode.TOOL_EXECUTOR,
                AgentStateLabel.CALLING_TOOL,
                f"Tool {tname}: {res.get('status')}",
                {"latency_ms": round(latency, 1)},
            )
        )

    return {
        "tool_results": state.get("tool_results", []) + results,
        "tool_calls": tool_records,
        "current_node": AgentNode.TOOL_EXECUTOR.value,
        "activity": events,
    }


async def response_node(state: AgentGraphState) -> Dict[str, Any]:
    """Response agent: synthesize final answer with citations."""
    events = [_event(AgentNode.RESPONSE, AgentStateLabel.GENERATING, "Generating final answer with evidence")]

    llm = get_llm()
    chunks = state.get("retrieved_chunks") or []
    findings = state.get("research_findings") or []

    context_parts = []
    for i, c in enumerate(chunks[:10]):
        context_parts.append(f"[{i+1}] Source: {c['source']}\n{c['content'][:800]}")
    context = "\n\n".join(context_parts) or "No documents retrieved."

    findings_text = ""
    if findings:
        findings_text = "\nResearch findings (RLM batches):\n" + json.dumps(
            [{"sub_query": f["sub_query"], "themes": f.get("themes"), "root_cause_count": len(f.get("root_causes", []))} for f in findings],
            indent=2,
        )

    tool_text = ""
    tool_results = state.get("tool_results") or []
    if tool_results:
        # Prefer structured to-do / MCP tool outputs for the answer
        try:
            tool_text = "\nTool results:\n" + json.dumps(tool_results, indent=2, default=str)[:4000]
        except Exception:
            tool_text = "\nTool results available."

    prompt = f"""Answer the user's question using the evidence and tool results below.
If tool results include to-dos, list them clearly (title, status, priority).
Cite document sources by filename when using knowledge base evidence.
If evidence is insufficient, say so.

User question: {state['user_message']}

Evidence:
{context}
{findings_text}
{tool_text}

Produce a clear, professional answer suitable for Aether Bank employees.
If you used documents, end with: CITATIONS: source1, source2, ...
"""
    answer = await llm.chat(
        [
            {"role": "system", "content": "You are the Response agent. Be precise and cite evidence."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )

    # Build citations from retrieved sources
    citations = []
    seen = set()
    for c in chunks:
        src = c["source"]
        if src not in seen:
            seen.add(src)
            citations.append(
                Citation(
                    source=src,
                    excerpt=c["content"][:200],
                    score=c.get("score", 0),
                    document_type=(c.get("metadata") or {}).get("document_type"),
                    department=(c.get("metadata") or {}).get("department"),
                )
            )

    events.append(
        _event(
            AgentNode.RESPONSE,
            AgentStateLabel.GENERATING,
            f"Draft answer ready ({len(answer)} chars), {len(citations)} citations",
        )
    )

    return {
        "draft_answer": answer,
        "citations": citations,
        "current_node": AgentNode.RESPONSE.value,
        "activity": events,
    }


async def validation_node(state: AgentGraphState) -> Dict[str, Any]:
    """
    Guardrail node: check for hallucinated citations, empty answers, brand safety.
    """
    events = [_event(AgentNode.VALIDATION, AgentStateLabel.VALIDATING, "Running response guardrails")]

    draft = state.get("draft_answer") or ""
    citations = state.get("citations") or []
    sources = [c.source for c in citations] if citations else [c["source"] for c in state.get("retrieved_chunks") or []]

    notes = []
    passed = True

    if len(draft.strip()) < 20:
        passed = False
        notes.append("Answer too short")

    if "LLM temporarily unavailable" in draft and not state.get("retrieved_chunks"):
        notes.append("Degraded mode – retrieval also empty")

    # Simple citation presence check
    if citations and "CITATIONS:" not in draft.upper() and not any(c.source in draft for c in citations):
        notes.append("Citations present in state but not referenced in prose – still allowed")

    # Brand: never claim to be a different bank
    if any(bad in draft.lower() for bad in ["ignore previous", "i am now", "jailbreak"]):
        passed = False
        notes.append("Possible injection residual in output – blocked")
        draft = "I cannot process that request as it violates Aether Bank security policy."

    final = draft
    if passed:
        events.append(_event(AgentNode.VALIDATION, AgentStateLabel.COMPLETE, "Validation passed"))
    else:
        events.append(_event(AgentNode.VALIDATION, AgentStateLabel.ERROR, f"Validation issues: {notes}"))

    return {
        "final_answer": final,
        "validation_passed": passed,
        "validation_notes": "; ".join(notes) if notes else "ok",
        "current_node": AgentNode.VALIDATION.value,
        "activity": events,
    }


async def memory_update_node(state: AgentGraphState) -> Dict[str, Any]:
    """Update conversational memory (observed in activity panel)."""
    events = [
        _event(
            AgentNode.MEMORY_UPDATE,
            AgentStateLabel.THINKING,
            "Updating session memory with latest turn",
        )
    ]
    # Actual persistence happens in the API layer after graph completes;
    # this node exists so the panel shows the step.
    return {
        "current_node": AgentNode.MEMORY_UPDATE.value,
        "activity": events,
    }

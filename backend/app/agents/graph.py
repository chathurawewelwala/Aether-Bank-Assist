"""
LangGraph orchestration for Aether Assistant.

Graph topology:

    START → supervisor → (retrieval | research) → human_approval
         → (tool_executor | END if waiting) → response → validation → memory_update → END

Human-in-the-loop:
- Supervisor may set requires_approval=True (MCP / explicit HITL keywords).
- human_approval pauses the run until the client calls POST /chat/approve.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Literal, Optional

from langgraph.graph import END, StateGraph

from app.agents.nodes import (
    human_approval_node,
    memory_update_node,
    research_node,
    response_node,
    retrieval_node,
    supervisor_node,
    tool_executor_node,
    validation_node,
)
from app.agents.state import AgentGraphState

logger = logging.getLogger(__name__)

# Pending HITL runs: session_id -> partial state to resume after approval
_pending_approvals: Dict[str, Dict[str, Any]] = {}


def save_pending_approval(session_id: str, state: Dict[str, Any]) -> None:
    _pending_approvals[session_id] = state


def pop_pending_approval(session_id: str) -> Optional[Dict[str, Any]]:
    return _pending_approvals.pop(session_id, None)


def get_pending_approval(session_id: str) -> Optional[Dict[str, Any]]:
    return _pending_approvals.get(session_id)


def _route_after_supervisor(state: AgentGraphState) -> Literal["research", "retrieval"]:
    if state.get("needs_research"):
        return "research"
    return "retrieval"


def _route_after_approval(state: AgentGraphState) -> Literal["tool_executor", "await_human"]:
    """If approval required and not granted, stop the graph for human input."""
    if state.get("requires_approval") and state.get("approval_granted") is not True:
        return "await_human"
    return "tool_executor"


def build_graph():
    graph = StateGraph(AgentGraphState)

    graph.add_node("supervisor", supervisor_node)
    graph.add_node("retrieval", retrieval_node)
    graph.add_node("research", research_node)
    graph.add_node("human_approval", human_approval_node)
    graph.add_node("tool_executor", tool_executor_node)
    graph.add_node("response", response_node)
    graph.add_node("validation", validation_node)
    graph.add_node("memory_update", memory_update_node)

    graph.set_entry_point("supervisor")

    graph.add_conditional_edges(
        "supervisor",
        _route_after_supervisor,
        {"research": "research", "retrieval": "retrieval"},
    )
    graph.add_edge("retrieval", "human_approval")
    graph.add_edge("research", "human_approval")
    graph.add_conditional_edges(
        "human_approval",
        _route_after_approval,
        {
            "tool_executor": "tool_executor",
            "await_human": END,  # pause — client must approve to resume
        },
    )
    graph.add_edge("tool_executor", "response")
    graph.add_edge("response", "validation")
    graph.add_edge("validation", "memory_update")
    graph.add_edge("memory_update", END)

    return graph.compile()


# Singleton compiled graph
_compiled = None


def get_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_graph()
    return _compiled


def build_initial_state(
    user_message: str,
    session_id: str,
    user_role: str,
    username: str,
    history: list = None,
    memory_summary: str = "",
    approval_granted: Optional[bool] = None,
) -> AgentGraphState:
    return {
        "user_message": user_message,
        "session_id": session_id,
        "user_role": user_role,
        "username": username,
        "history": history or [],
        "memory_summary": memory_summary,
        "intent": "",
        "plan": [],
        "current_step": 0,
        "needs_research": False,
        "needs_tools": [],
        "retrieved_chunks": [],
        "research_findings": [],
        "sub_queries": [],
        "tool_calls": [],
        "tool_results": [],
        "draft_answer": "",
        "citations": [],
        "final_answer": "",
        "validation_passed": False,
        "validation_notes": "",
        "activity": [],
        "current_node": "",
        "error": None,
        "requires_approval": False,
        "approval_granted": approval_granted,
    }


async def run_agent(
    user_message: str,
    session_id: str,
    user_role: str,
    username: str,
    history: list = None,
    memory_summary: str = "",
    approval_granted: Optional[bool] = None,
    resume_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Execute the full agent graph and return final state.
    """
    graph = get_graph()
    if resume_state:
        initial = dict(resume_state)
        initial["approval_granted"] = approval_granted
        # Skip re-asking: force path through tools after approval
        if approval_granted is True:
            initial["requires_approval"] = False
        initial["activity"] = list(initial.get("activity") or [])
    else:
        initial = build_initial_state(
            user_message,
            session_id,
            user_role,
            username,
            history,
            memory_summary,
            approval_granted=approval_granted,
        )

    try:
        final_state = await graph.ainvoke(initial)
        # If paused for HITL, keep state for resume
        if (
            final_state.get("requires_approval")
            and final_state.get("approval_granted") is not True
            and final_state.get("current_node") == "human_approval"
        ):
            save_pending_approval(session_id, dict(final_state))
        return final_state
    except Exception as e:
        logger.exception("Agent graph failed: %s", e)
        return {
            **initial,
            "final_answer": (
                "I encountered an internal error while processing your request. "
                "The team has been notified. Please try again or contact support."
            ),
            "error": str(e),
            "activity": list(initial.get("activity") or [])
            + [
                {
                    "node": "supervisor",
                    "state": "error",
                    "message": f"Graph execution error: {type(e).__name__}: {e}",
                    "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
                }
            ],
        }


async def resume_after_approval(
    session_id: str,
    approved: bool,
    user_role: str,
    username: str,
) -> Dict[str, Any]:
    """Continue a paused HITL run after the user approves or rejects."""
    pending = pop_pending_approval(session_id)
    if not pending:
        return {
            "final_answer": "No pending approval found for this session. Please ask again.",
            "activity": [],
            "requires_approval": False,
            "current_node": "human_approval",
        }

    if not approved:
        return {
            **pending,
            "approval_granted": False,
            "requires_approval": False,
            "final_answer": "Request rejected by human reviewer. No enterprise tools were executed.",
            "current_node": "human_approval",
            "activity": list(pending.get("activity") or [])
            + [
                {
                    "node": "human_approval",
                    "state": "complete",
                    "message": "Human rejected the action — tools skipped",
                }
            ],
        }

    # Resume: mark approved and continue from a state that skips the pause
    pending["approval_granted"] = True
    pending["requires_approval"] = False
    # Re-run remaining pipeline via tool_executor → response → validation → memory
    # Easiest reliable path: ainvoke from a minimal graph continuation by calling nodes
    from app.agents.nodes import (
        memory_update_node,
        response_node,
        tool_executor_node,
        validation_node,
    )

    state = dict(pending)
    accumulated_activity = list(state.get("activity") or [])

    for node_fn in (tool_executor_node, response_node, validation_node, memory_update_node):
        partial = await node_fn(state)
        new_events = partial.pop("activity", None) or []
        state.update(partial)
        accumulated_activity.extend(new_events)
        state["activity"] = accumulated_activity

    return state

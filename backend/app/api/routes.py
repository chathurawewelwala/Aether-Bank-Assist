"""
FastAPI routes: auth, chat (streaming + non-streaming), health, activity.
Async throughout. Structured error handling.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from pydantic import BaseModel, Field

from app.agents.graph import (
    build_initial_state,
    get_graph,
    resume_after_approval,
    run_agent,
    save_pending_approval,
)
from app.core.config import get_settings
from app.memory.conversation import get_memory_store
from app.models.schemas import (
    AgentActivityEvent,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    HealthResponse,
    LoginRequest,
    TokenResponse,
    UserInfo,
)


class ApproveRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    approved: bool = True
from app.retrieval.hybrid_store import get_knowledge_store
from app.security.auth import get_current_user, login
from app.security.guardrails import validate_user_input
from app.agents.llm import get_llm

logger = logging.getLogger(__name__)
router = APIRouter()



@router.get("/config")
async def public_config():
    """Browser-safe config (Keycloak URLs, auth mode) for the dashboard."""
    s = get_settings()
    return {
        "auth_mode": s.auth_mode,
        "keycloak_url": s.keycloak_public_url,
        "keycloak_realm": s.keycloak_realm,
        "keycloak_client_id": "aether-web",
        "company_name": s.company_name,
        "assistant_name": s.assistant_name,
        "api_version": s.app_version,
    }

@router.post("/auth/login", response_model=TokenResponse)
async def auth_login(body: LoginRequest):
    return login(body.username, body.password)


@router.get("/auth/me", response_model=UserInfo)
async def auth_me(user: UserInfo = Depends(get_current_user)):
    return user


@router.get("/health", response_model=HealthResponse)
async def health():
    settings = get_settings()
    store = get_knowledge_store()
    llm = get_llm()
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        llm_available=llm.available,
        retrieval_ready=store.ready,
        langsmith_enabled=settings.langchain_tracing_v2 and bool(settings.langchain_api_key),
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, user: UserInfo = Depends(get_current_user)):
    ok, err = validate_user_input(body.message)
    if not ok:
        raise HTTPException(status_code=400, detail=err)

    memory = get_memory_store()
    session = memory.get_or_create(body.session_id, user.username)

    final = await run_agent(
        user_message=body.message,
        session_id=session.session_id,
        user_role=user.role.value,
        username=user.username,
        history=session.get_context_window(),
        memory_summary=session.summary,
    )

    answer = final.get("final_answer") or final.get("draft_answer") or "No answer generated."
    activity = final.get("activity") or []
    # Normalize activity events if they are dicts
    activity_models = []
    for a in activity:
        if isinstance(a, AgentActivityEvent):
            activity_models.append(a)
        elif isinstance(a, dict):
            try:
                activity_models.append(AgentActivityEvent(**a))
            except Exception:
                pass

    assistant_msg = ChatMessage(
        role="assistant",
        content=answer,
        citations=final.get("citations") or [],
        activity=activity_models,
        tool_calls=final.get("tool_calls") or [],
    )
    user_msg = ChatMessage(role="user", content=body.message)
    session.add_message(user_msg)
    session.add_message(assistant_msg)

    return ChatResponse(
        session_id=session.session_id,
        message=assistant_msg,
        agent_trace=activity_models,
        final_node=final.get("current_node"),
    )


@router.post("/chat/stream")
async def chat_stream(body: ChatRequest, user: UserInfo = Depends(get_current_user)):
    """
    SSE stream of agent activity events as each LangGraph node completes,
    followed by the final answer. Powers the Agent Activity Panel in real time.
    """
    ok, err = validate_user_input(body.message)
    if not ok:
        raise HTTPException(status_code=400, detail=err)

    memory = get_memory_store()
    session = memory.get_or_create(body.session_id, user.username)

    async def event_generator() -> AsyncGenerator[dict, None]:
        yield {
            "event": "status",
            "data": json.dumps({"state": "started", "session_id": session.session_id}),
        }

        initial = build_initial_state(
            user_message=body.message,
            session_id=session.session_id,
            user_role=user.role.value,
            username=user.username,
            history=session.get_context_window(),
            memory_summary=session.summary,
        )

        graph = get_graph()
        merged: dict = dict(initial)
        seen_activity = 0

        try:
            # Stream node-by-node so the UI updates while the agent works
            async for update in graph.astream(initial, stream_mode="updates"):
                # update is {node_name: partial_state}
                if not isinstance(update, dict):
                    continue
                for node_name, partial in update.items():
                    if not isinstance(partial, dict):
                        continue
                    merged.update(partial)
                    # Emit any new activity events from this node
                    activities = partial.get("activity") or []
                    for a in activities:
                        if hasattr(a, "model_dump"):
                            payload = a.model_dump(mode="json")
                        elif isinstance(a, dict):
                            payload = a
                        else:
                            continue
                        yield {
                            "event": "activity",
                            "data": json.dumps(payload, default=str),
                        }
                        seen_activity += 1
                    # Also emit a compact node-complete status
                    yield {
                        "event": "status",
                        "data": json.dumps(
                            {
                                "state": "node_complete",
                                "node": node_name,
                                "current_node": partial.get("current_node") or node_name,
                            }
                        ),
                    }
        except Exception as e:
            logger.exception("Streaming agent failed: %s", e)
            yield {
                "event": "activity",
                "data": json.dumps(
                    {
                        "node": "system",
                        "state": "error",
                        "message": f"Agent error: {type(e).__name__}: {e}",
                    },
                    default=str,
                ),
            }
            merged["final_answer"] = (
                "I encountered an internal error while processing your request. "
                f"({type(e).__name__})"
            )
            merged["error"] = str(e)

        answer = (
            merged.get("final_answer")
            or merged.get("draft_answer")
            or "No answer generated."
        )
        citations = merged.get("citations") or []
        cit_payload = [
            c.model_dump() if hasattr(c, "model_dump") else c for c in citations
        ]
        tool_calls = merged.get("tool_calls") or []

        pending_approval = bool(
            merged.get("requires_approval")
            and merged.get("approval_granted") is not True
            and merged.get("current_node") == "human_approval"
        )
        if pending_approval:
            save_pending_approval(session.session_id, dict(merged))

        assistant_msg = ChatMessage(
            role="assistant",
            content=answer,
            citations=citations if citations and hasattr(citations[0], "model_dump") else [],
            activity=[],
            tool_calls=tool_calls if tool_calls and hasattr(tool_calls[0], "model_dump") else [],
        )
        try:
            session.add_message(ChatMessage(role="user", content=body.message))
            session.add_message(assistant_msg)
        except Exception:
            pass

        yield {
            "event": "answer",
            "data": json.dumps(
                {
                    "session_id": session.session_id,
                    "content": answer,
                    "citations": cit_payload,
                    "tool_calls": [
                        t.model_dump() if hasattr(t, "model_dump") else t
                        for t in tool_calls
                    ],
                    "final_node": merged.get("current_node"),
                    "error": merged.get("error"),
                    "pending_approval": pending_approval,
                    "pending_tools": merged.get("needs_tools") or [],
                },
                default=str,
            ),
        }
        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(event_generator())


@router.post("/chat/approve")
async def chat_approve(body: ApproveRequest, user: UserInfo = Depends(get_current_user)):
    """
    Human-in-the-loop: approve or reject a paused agent run.
    After approve, enterprise tools run and the final answer is returned.
    """
    final = await resume_after_approval(
        session_id=body.session_id,
        approved=body.approved,
        user_role=user.role.value,
        username=user.username,
    )

    activity = final.get("activity") or []
    activity_models = []
    for a in activity:
        if isinstance(a, AgentActivityEvent):
            activity_models.append(a)
        elif isinstance(a, dict):
            try:
                activity_models.append(AgentActivityEvent(**{k: v for k, v in a.items() if k in AgentActivityEvent.model_fields}))
            except Exception:
                pass

    answer = final.get("final_answer") or final.get("draft_answer") or "Done."
    citations = final.get("citations") or []

    memory = get_memory_store()
    session = memory.get_or_create(body.session_id, user.username)
    session.add_message(
        ChatMessage(
            role="assistant",
            content=answer,
            citations=citations if citations and hasattr(citations[0], "model_dump") else [],
            activity=activity_models[-8:] if activity_models else [],
        )
    )

    return {
        "session_id": body.session_id,
        "content": answer,
        "citations": [c.model_dump() if hasattr(c, "model_dump") else c for c in citations],
        "pending_approval": False,
        "approved": body.approved,
        "agent_trace": [a.model_dump(mode="json") if hasattr(a, "model_dump") else a for a in activity_models[-12:]],
        "final_node": final.get("current_node"),
    }


# ─── To-dos (UI + API; also used by agent tools) ───────────────────────────

class TodoCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    description: Optional[str] = None
    priority: str = "medium"
    due_date: Optional[str] = None


class TodoUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None


@router.get("/todos")
async def api_list_todos(
    status: Optional[str] = None,
    user: UserInfo = Depends(get_current_user),
):
    from app.db import todo_service
    items = await todo_service.list_todos(user.username, status=status)
    return {"todos": items, "count": len(items)}


@router.post("/todos")
async def api_create_todo(body: TodoCreate, user: UserInfo = Depends(get_current_user)):
    from app.db import todo_service
    try:
        item = await todo_service.create_todo(
            username=user.username,
            title=body.title,
            description=body.description,
            priority=body.priority,
            due_date=body.due_date,
        )
        return item
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/todos/{todo_id}")
async def api_update_todo(
    todo_id: str,
    body: TodoUpdate,
    user: UserInfo = Depends(get_current_user),
):
    from app.db import todo_service
    item = await todo_service.update_todo(
        user.username,
        todo_id,
        title=body.title,
        description=body.description,
        status=body.status,
        priority=body.priority,
        due_date=body.due_date,
    )
    if not item:
        raise HTTPException(status_code=404, detail="To-do not found")
    return item


@router.delete("/todos/{todo_id}")
async def api_delete_todo(todo_id: str, user: UserInfo = Depends(get_current_user)):
    from app.db import todo_service
    ok = await todo_service.delete_todo(user.username, todo_id)
    if not ok:
        raise HTTPException(status_code=404, detail="To-do not found")
    return {"deleted": True, "id": todo_id}

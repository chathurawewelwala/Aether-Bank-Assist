"""To-do tools for the agent – CRUD against Postgres (or memory fallback)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.db import todo_service


async def todo_list(username: str, status: Optional[str] = None) -> Dict[str, Any]:
    items = await todo_service.list_todos(username, status=status)
    return {"todos": items, "count": len(items), "username": username}


async def todo_create(
    username: str,
    title: str,
    description: Optional[str] = None,
    priority: str = "medium",
    due_date: Optional[str] = None,
) -> Dict[str, Any]:
    item = await todo_service.create_todo(
        username=username,
        title=title,
        description=description,
        priority=priority or "medium",
        due_date=due_date,
    )
    return {"todo": item, "message": f"Created to-do: {item['title']}"}


async def todo_complete(username: str, todo_id: str) -> Dict[str, Any]:
    item = await todo_service.update_todo(username, todo_id, status="done")
    if not item:
        return {"error": "To-do not found", "todo_id": todo_id}
    return {"todo": item, "message": f"Marked done: {item['title']}"}


async def todo_update(
    username: str,
    todo_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    due_date: Optional[str] = None,
) -> Dict[str, Any]:
    item = await todo_service.update_todo(
        username, todo_id, title=title, description=description,
        status=status, priority=priority, due_date=due_date,
    )
    if not item:
        return {"error": "To-do not found", "todo_id": todo_id}
    return {"todo": item, "message": f"Updated: {item['title']}"}


async def todo_delete(username: str, todo_id: str) -> Dict[str, Any]:
    ok = await todo_service.delete_todo(username, todo_id)
    if not ok:
        return {"error": "To-do not found", "todo_id": todo_id}
    return {"deleted": True, "todo_id": todo_id, "message": "To-do deleted"}

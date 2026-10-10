"""To-do persistence: PostgreSQL when available, in-memory fallback otherwise."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# In-memory fallback store: username -> list of todo dicts
_MEMORY: Dict[str, List[Dict[str, Any]]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mem_list(username: str) -> List[Dict[str, Any]]:
    return _MEMORY.setdefault(username, [])


async def list_todos(username: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
    try:
        from sqlalchemy import select
        from app.db.models import TodoRecord
        from app.db.session import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            q = select(TodoRecord).where(TodoRecord.username == username).order_by(TodoRecord.created_at.desc())
            if status:
                q = q.where(TodoRecord.status == status)
            rows = (await session.execute(q)).scalars().all()
            return [_row_to_dict(r) for r in rows]
    except Exception as e:
        logger.debug("todo list fallback memory: %s", e)
        items = list(_mem_list(username))
        if status:
            items = [t for t in items if t.get("status") == status]
        return sorted(items, key=lambda t: t.get("created_at", ""), reverse=True)


async def create_todo(
    username: str,
    title: str,
    description: Optional[str] = None,
    priority: str = "medium",
    due_date: Optional[str] = None,
) -> Dict[str, Any]:
    title = (title or "").strip()
    if not title:
        raise ValueError("title is required")
    priority = priority if priority in ("low", "medium", "high") else "medium"

    try:
        from app.db.models import TodoRecord
        from app.db.session import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            row = TodoRecord(
                username=username,
                title=title,
                description=description,
                status="open",
                priority=priority,
                due_date=due_date,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return _row_to_dict(row)
    except Exception as e:
        logger.debug("todo create fallback memory: %s", e)
        item = {
            "id": str(uuid.uuid4()),
            "username": username,
            "title": title,
            "description": description,
            "status": "open",
            "priority": priority,
            "due_date": due_date,
            "created_at": _now(),
            "updated_at": _now(),
        }
        _mem_list(username).insert(0, item)
        return item


async def update_todo(
    username: str,
    todo_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    due_date: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    try:
        from sqlalchemy import select
        from app.db.models import TodoRecord
        from app.db.session import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            row = (
                await session.execute(
                    select(TodoRecord).where(
                        TodoRecord.id == uuid.UUID(todo_id),
                        TodoRecord.username == username,
                    )
                )
            ).scalar_one_or_none()
            if not row:
                return None
            if title is not None:
                row.title = title.strip() or row.title
            if description is not None:
                row.description = description
            if status is not None and status in ("open", "done"):
                row.status = status
            if priority is not None and priority in ("low", "medium", "high"):
                row.priority = priority
            if due_date is not None:
                row.due_date = due_date or None
            await session.commit()
            await session.refresh(row)
            return _row_to_dict(row)
    except Exception as e:
        logger.debug("todo update fallback memory: %s", e)
        for t in _mem_list(username):
            if t["id"] == todo_id:
                if title is not None:
                    t["title"] = title.strip() or t["title"]
                if description is not None:
                    t["description"] = description
                if status is not None and status in ("open", "done"):
                    t["status"] = status
                if priority is not None and priority in ("low", "medium", "high"):
                    t["priority"] = priority
                if due_date is not None:
                    t["due_date"] = due_date or None
                t["updated_at"] = _now()
                return dict(t)
        return None


async def delete_todo(username: str, todo_id: str) -> bool:
    try:
        from sqlalchemy import select
        from app.db.models import TodoRecord
        from app.db.session import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            row = (
                await session.execute(
                    select(TodoRecord).where(
                        TodoRecord.id == uuid.UUID(todo_id),
                        TodoRecord.username == username,
                    )
                )
            ).scalar_one_or_none()
            if not row:
                return False
            await session.delete(row)
            await session.commit()
            return True
    except Exception as e:
        logger.debug("todo delete fallback memory: %s", e)
        items = _mem_list(username)
        before = len(items)
        _MEMORY[username] = [t for t in items if t["id"] != todo_id]
        return len(_MEMORY[username]) < before


def _row_to_dict(row) -> Dict[str, Any]:
    return {
        "id": str(row.id),
        "username": row.username,
        "title": row.title,
        "description": row.description,
        "status": row.status,
        "priority": row.priority,
        "due_date": row.due_date,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }

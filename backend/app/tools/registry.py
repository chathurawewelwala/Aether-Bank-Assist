"""Central tool registry with permission checks."""
from typing import Any, Callable, Dict, Optional

from app.models.schemas import UserRole
from app.security.auth import check_tool_permission
from app.security.guardrails import sanitize_tool_args
from app.tools.knowledge import knowledge_search
from app.tools.mcp_tools import mcp_employee_directory, mcp_incident_records, mcp_service_catalog
from app.tools.python_analysis import python_analysis
from app.tools.todo import todo_complete, todo_create, todo_delete, todo_list, todo_update

TOOL_MAP: Dict[str, Callable] = {
    "knowledge_search": knowledge_search,
    "mcp_employee_directory": mcp_employee_directory,
    "mcp_service_catalog": mcp_service_catalog,
    "mcp_incident_records": mcp_incident_records,
    "python_analysis": python_analysis,
    "todo_list": todo_list,
    "todo_create": todo_create,
    "todo_complete": todo_complete,
    "todo_update": todo_update,
    "todo_delete": todo_delete,
}

TODO_TOOLS = {"todo_list", "todo_create", "todo_complete", "todo_update", "todo_delete"}


async def execute_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    role: UserRole,
    username: Optional[str] = None,
) -> Dict[str, Any]:
    if not check_tool_permission(role, tool_name):
        return {
            "error": f"Permission denied: role '{role.value}' cannot execute tool '{tool_name}'",
            "status": "forbidden",
        }

    ok, clean_args, err = sanitize_tool_args(tool_name, arguments)
    if not ok:
        return {"error": err, "status": "invalid_args"}

    fn = TOOL_MAP.get(tool_name)
    if not fn:
        return {"error": f"Unknown tool: {tool_name}", "status": "not_found"}

    if tool_name == "knowledge_search":
        clean_args["role"] = role

    if tool_name in TODO_TOOLS:
        if not username:
            return {"error": "username required for to-do tools", "status": "invalid_args"}
        clean_args["username"] = username

    try:
        result = await fn(**clean_args)
        return {"status": "success", "result": result}
    except TypeError as e:
        return {"error": f"Invalid arguments for {tool_name}: {e}", "status": "invalid_args"}
    except Exception as e:
        return {"error": str(e), "status": "error"}

"""
Shared agent state for the LangGraph orchestration.
Designed for explainability: every transition is observable.
"""
from typing import Any, Dict, List, Optional, Annotated
from typing_extensions import TypedDict
import operator

from app.models.schemas import AgentActivityEvent, AgentNode, AgentStateLabel, Citation, ToolCallRecord, UserRole


class AgentGraphState(TypedDict):
    # Input
    user_message: str
    session_id: str
    user_role: str
    username: str

    # Conversation context
    history: List[Dict[str, str]]
    memory_summary: str

    # Supervisor decisions
    intent: str
    plan: List[str]
    current_step: int
    needs_research: bool
    needs_tools: List[str]

    # Retrieval / Research
    retrieved_chunks: List[Dict[str, Any]]
    research_findings: List[Dict[str, Any]]
    sub_queries: List[str]

    # Tool execution
    tool_calls: Annotated[List[ToolCallRecord], operator.add]
    tool_results: List[Dict[str, Any]]

    # Response
    draft_answer: str
    citations: List[Citation]
    final_answer: str
    validation_passed: bool
    validation_notes: str

    # Observability
    activity: Annotated[List[AgentActivityEvent], operator.add]
    current_node: str
    error: Optional[str]

    # Human-in-the-loop
    requires_approval: bool
    approval_granted: Optional[bool]

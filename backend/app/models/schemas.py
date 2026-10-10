"""
Pydantic models for request/response contracts and agent state.
Emphasizes type safety and explainability of every field.
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class UserRole(str, Enum):
    VIEWER = "viewer"
    ANALYST = "analyst"
    ADMINISTRATOR = "administrator"


class AgentNode(str, Enum):
    """Mirrors LangGraph node names for the activity panel."""
    SUPERVISOR = "supervisor"
    RETRIEVAL = "retrieval"
    RESEARCH = "research"
    RESPONSE = "response"
    TOOL_EXECUTOR = "tool_executor"
    VALIDATION = "validation"
    HUMAN_APPROVAL = "human_approval"
    MEMORY_UPDATE = "memory_update"


class AgentStateLabel(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    RETRIEVING = "retrieving"
    RESEARCHING = "researching"
    CALLING_TOOL = "calling_tool"
    VALIDATING = "validating"
    GENERATING = "generating"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETE = "complete"
    ERROR = "error"


class DocumentChunk(BaseModel):
    id: str
    content: str
    source: str
    score: float = 0.0
    dense_score: float = 0.0
    sparse_score: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ToolCallRecord(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]
    result_preview: Optional[str] = None
    status: str = "pending"  # pending | running | success | error
    latency_ms: Optional[float] = None
    error: Optional[str] = None


class AgentActivityEvent(BaseModel):
    """Real-time event streamed to the Agent Activity Panel."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    node: AgentNode
    state: AgentStateLabel
    message: str
    details: Optional[Dict[str, Any]] = None


class Citation(BaseModel):
    source: str
    excerpt: str
    score: float
    document_type: Optional[str] = None
    department: Optional[str] = None


class ChatMessage(BaseModel):
    role: str  # user | assistant | system
    content: str
    citations: List[Citation] = Field(default_factory=list)
    activity: List[AgentActivityEvent] = Field(default_factory=list)
    tool_calls: List[ToolCallRecord] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: Optional[str] = None
    stream: bool = True


class ChatResponse(BaseModel):
    session_id: str
    message: ChatMessage
    agent_trace: List[AgentActivityEvent] = Field(default_factory=list)
    final_node: Optional[AgentNode] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole
    username: str
    expires_in: int


class UserInfo(BaseModel):
    username: str
    role: UserRole
    departments: List[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    version: str
    llm_available: bool
    retrieval_ready: bool
    langsmith_enabled: bool

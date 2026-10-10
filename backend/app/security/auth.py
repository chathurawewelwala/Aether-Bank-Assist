"""
Open-source style authentication (JWT) with role-based access control.
In production this would integrate with Keycloak; here we provide a
self-contained mock identity provider that mirrors Keycloak claims.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
import hashlib

from app.core.config import get_settings
from app.models.schemas import TokenResponse, UserInfo, UserRole

security = HTTPBearer(auto_error=False)

# Mock user store (Keycloak realm simulation).
# Password for all demo users: password123
# SHA-256 used for POC reliability; production should use Keycloak + argon2/bcrypt.
def _hash(p: str) -> str:
    return hashlib.sha256(p.encode()).hexdigest()

MOCK_USERS = {
    "viewer@aether.bank": {
        "username": "viewer@aether.bank",
        "hashed_password": _hash("password123"),
        "role": UserRole.VIEWER,
        "departments": ["general"],
    },
    "analyst@aether.bank": {
        "username": "analyst@aether.bank",
        "hashed_password": _hash("password123"),
        "role": UserRole.ANALYST,
        "departments": ["payments", "risk", "operations"],
    },
    "admin@aether.bank": {
        "username": "admin@aether.bank",
        "hashed_password": _hash("password123"),
        "role": UserRole.ADMINISTRATOR,
        "departments": ["*"],
    },
}


def verify_password(plain: str, hashed: str) -> bool:
    return _hash(plain) == hashed


def authenticate_user(username: str, password: str) -> Optional[dict]:
    user = MOCK_USERS.get(username)
    if not user or not verify_password(password, user["hashed_password"]):
        return None
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.jwt_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def login(username: str, password: str) -> TokenResponse:
    user = authenticate_user(username, password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    token = create_access_token(
        {"sub": user["username"], "role": user["role"].value, "departments": user["departments"]}
    )
    settings = get_settings()
    return TokenResponse(
        access_token=token,
        role=user["role"],
        username=user["username"],
        expires_in=settings.jwt_expire_minutes * 60,
    )


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> UserInfo:
    settings = get_settings()
    if not settings.enable_auth:
        return UserInfo(username="dev@aether.bank", role=UserRole.ADMINISTRATOR, departments=["*"])

    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token = credentials.credentials

    # Keycloak / OIDC mode
    if settings.auth_mode == "keycloak":
        try:
            from app.security.oidc import validate_keycloak_token
            return await validate_keycloak_token(token)
        except Exception:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Keycloak token")

    # Local HS256 JWT mode (dev / POC without Keycloak)
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        username: str = payload.get("sub")
        role = UserRole(payload.get("role", "viewer"))
        departments = payload.get("departments", [])
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return UserInfo(username=username, role=role, departments=departments)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


# Role → allowed tools / capabilities
ROLE_PERMISSIONS = {
    UserRole.VIEWER: {
        "tools": {"knowledge_search", "todo_list", "todo_create", "todo_complete", "todo_update", "todo_delete"},
        "max_access_level": "internal",
        "can_use_mcp": False,
        "can_use_python_analysis": False,
        "can_admin": False,
    },
    UserRole.ANALYST: {
        "tools": {"knowledge_search", "mcp_employee_directory", "mcp_service_catalog", "mcp_incident_records", "python_analysis", "todo_list", "todo_create", "todo_complete", "todo_update", "todo_delete"},
        "max_access_level": "internal",
        "can_use_mcp": True,
        "can_use_python_analysis": True,
        "can_admin": False,
    },
    UserRole.ADMINISTRATOR: {
        "tools": {"*"},
        "max_access_level": "restricted",
        "can_use_mcp": True,
        "can_use_python_analysis": True,
        "can_admin": True,
    },
}


def check_tool_permission(role: UserRole, tool_name: str) -> bool:
    perms = ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS[UserRole.VIEWER])
    allowed = perms["tools"]
    if "*" in allowed:
        return True
    return tool_name in allowed


def get_max_access_level(role: UserRole) -> str:
    return ROLE_PERMISSIONS[role]["max_access_level"]

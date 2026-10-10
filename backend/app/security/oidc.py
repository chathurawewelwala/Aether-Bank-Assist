"""Keycloak / OIDC JWT validation using JWKS."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import httpx
from jose import jwt
from jose.exceptions import JWTError

from app.core.config import get_settings
from app.models.schemas import UserInfo, UserRole

logger = logging.getLogger(__name__)

_jwks_cache: Dict[str, Any] = {"keys": None, "fetched_at": 0}


async def _fetch_jwks() -> dict:
    settings = get_settings()
    now = time.time()
    if _jwks_cache["keys"] and now - _jwks_cache["fetched_at"] < 3600:
        return _jwks_cache["keys"]

    url = (
        f"{settings.keycloak_url.rstrip('/')}/realms/{settings.keycloak_realm}"
        f"/protocol/openid-connect/certs"
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
    _jwks_cache["keys"] = data
    _jwks_cache["fetched_at"] = now
    return data


def _map_roles(claims: dict) -> UserRole:
    """Map Keycloak realm/client roles to Aether roles."""
    realm_access = claims.get("realm_access") or {}
    roles = set(realm_access.get("roles") or [])
    resource = claims.get("resource_access") or {}
    for client_roles in resource.values():
        roles.update(client_roles.get("roles") or [])

    if "aether-admin" in roles or "administrator" in roles:
        return UserRole.ADMINISTRATOR
    if "aether-analyst" in roles or "analyst" in roles:
        return UserRole.ANALYST
    return UserRole.VIEWER


async def validate_keycloak_token(token: str) -> UserInfo:
    settings = get_settings()
    jwks = await _fetch_jwks()
    try:
        # python-jose can verify with key from JWKS
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        key = None
        for k in jwks.get("keys", []):
            if k.get("kid") == kid:
                key = k
                break
        if key is None and jwks.get("keys"):
            key = jwks["keys"][0]

        issuer = f"{settings.keycloak_public_url.rstrip('/')}/realms/{settings.keycloak_realm}"
        # Also accept internal issuer host
        alt_issuer = f"{settings.keycloak_url.rstrip('/')}/realms/{settings.keycloak_realm}"

        options = {"verify_aud": False}
        payload = None
        last_err = None
        for iss in (issuer, alt_issuer):
            try:
                payload = jwt.decode(
                    token,
                    key,
                    algorithms=["RS256"],
                    issuer=iss,
                    options=options,
                )
                break
            except JWTError as e:
                last_err = e
        if payload is None:
            raise last_err or JWTError("Unable to validate token")

        username = payload.get("preferred_username") or payload.get("email") or payload.get("sub")
        role = _map_roles(payload)
        return UserInfo(
            username=str(username),
            role=role,
            departments=["*"] if role == UserRole.ADMINISTRATOR else ["payments", "general"],
        )
    except Exception as e:
        logger.warning("keycloak_token_invalid: %s", e)
        raise

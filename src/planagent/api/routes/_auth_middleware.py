"""Optional authentication middleware for business endpoints.

Unlike the auth routes which require authentication, business endpoints
use optional auth — they work without a token but attach user context
when one is provided. This enables gradual adoption.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import Header, HTTPException, Request

_logger = logging.getLogger(__name__)


async def optional_auth(
    request: Request,
    authorization: str | None = Header(None),
) -> dict[str, Any] | None:
    """Optional JWT authentication dependency.

    Returns the token payload if a valid token is provided,
    or None if no token is present. Does NOT raise on missing token.
    Raises only if an INVALID token is provided.
    """
    if not authorization:
        return None

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None

    if not hasattr(request.app.state, "auth_service"):
        return None

    auth_service = request.app.state.auth_service
    payload = auth_service.verify_token(token)
    if payload is None:
        # Invalid token provided — this IS an error
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return payload


async def require_auth(
    request: Request,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """Required JWT authentication dependency.

    Raises 401 if no valid token is provided.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authentication required")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid Authorization format")

    if not hasattr(request.app.state, "auth_service"):
        raise HTTPException(status_code=503, detail="Auth service not available")

    auth_service = request.app.state.auth_service
    payload = auth_service.verify_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return payload

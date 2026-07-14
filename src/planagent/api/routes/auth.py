"""Auth API routes — JWT authentication endpoints."""

from __future__ import annotations

from ipaddress import ip_address
from secrets import compare_digest
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel, ConfigDict, Field

from planagent.services.auth import AuthService, UserRole

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ── Request / Response Models ─────────────────────────────────


class RegisterRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    username: str = Field(min_length=3, max_length=32)
    email: str = Field(min_length=5)
    password: str = Field(min_length=6)
    role: Literal["analyst", "viewer"] = "analyst"  # admin only via admin endpoint


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class UserInfo(BaseModel):
    id: str
    username: str
    email: str
    role: str
    is_active: bool
    created_at: str
    last_login: str | None = None


# ── Dependency ────────────────────────────────────────────────


def _get_auth_service(request: Request) -> AuthService:
    return _get_auth_service_from_app(request.app)


def _get_auth_service_from_app(app: Any) -> AuthService:
    if not hasattr(app.state, "auth_service"):
        from planagent.config import get_settings
        from planagent.services.auth import AuthConfig

        settings = get_settings()
        config = AuthConfig(
            secret_key=getattr(settings, "auth_secret_key", "") or "",
            database_url=settings.db.url,
            environment=settings.env,
        )
        app.state.auth_service = AuthService(config)
    return app.state.auth_service  # type: ignore[no-any-return]  # app.state 动态属性


def get_current_user_payload(
    request: Request,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """Extract and verify JWT from Authorization header."""
    return _verify_bearer_authorization(request.app, authorization)


def _verify_bearer_authorization(
    app: Any,
    authorization: str | None,
) -> dict[str, Any]:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=401, detail="Invalid Authorization format (expected 'Bearer <token>')"
        )

    auth_service = _get_auth_service_from_app(app)
    payload = auth_service.verify_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return payload


def get_community_access_payload(
    request: Request,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """Authenticate remote mode or provide the deployment-local single-user session."""
    existing = getattr(request.state, "community_access_payload", None)
    if isinstance(existing, dict):
        return existing
    return resolve_community_access(
        request.app,
        authorization,
        client_host=request.client.host if request.client else None,
        local_proxy_credential=request.headers.get("x-mingjian-local-proxy"),
    )


def resolve_community_access(
    app: Any,
    authorization: str | None,
    *,
    client_host: str | None,
    local_proxy_credential: str | None,
) -> dict[str, Any]:
    """Resolve the deployment-level Community access mode for HTTP or WebSocket."""
    from planagent.config import get_settings

    settings = get_settings()
    if settings.remote_access_enabled:
        return _verify_bearer_authorization(app, authorization)
    if not _is_loopback_client(client_host) and not _has_valid_local_proxy_credential(
        settings.local_proxy_secret,
        local_proxy_credential,
    ):
        raise HTTPException(
            status_code=403,
            detail="Local Community access requires a loopback connection",
        )

    return {
        "sub": "community-local",
        "username": "local",
        "role": UserRole.ADMIN.value,
        "type": "local_session",
        "iss": "planagent-community",
    }


def _is_loopback_client(client_host: str | None) -> bool:
    """Return whether the ASGI peer represents a loopback-only client."""
    if client_host == "testclient":
        return True
    if not client_host:
        return False
    try:
        return ip_address(client_host).is_loopback
    except ValueError:
        return False


def _has_valid_local_proxy_credential(
    configured_secret: str,
    provided_secret: str | None,
) -> bool:
    """Authenticate an explicitly configured same-deployment reverse proxy."""
    configured = configured_secret.strip()
    provided = (provided_secret or "").strip()
    return bool(configured and provided and compare_digest(configured, provided))


def require_role(required_role: UserRole):
    """Dependency factory for role-based access control."""

    def _check(
        request: Request, payload: dict[str, Any] = Depends(get_community_access_payload)
    ) -> dict[str, Any]:
        auth_service = _get_auth_service(request)
        if not auth_service.check_role(payload, required_role):
            raise HTTPException(status_code=403, detail=f"Requires role: {required_role.value}")
        return payload

    return _check


# ── Endpoints ─────────────────────────────────────────────────


@router.post("/register", response_model=UserInfo, status_code=201)
async def register(
    body: RegisterRequest,
    request: Request,
) -> UserInfo:
    """Register a new user."""
    from planagent.config import get_settings

    settings = get_settings()
    if settings.remote_access_enabled and not settings.remote_registration_enabled:
        raise HTTPException(status_code=403, detail="Remote user registration is disabled")

    auth_service = _get_auth_service(request)
    try:
        user = auth_service.create_user(
            username=body.username,
            email=body.email,
            password=body.password,
            role=UserRole(body.role),
        )
        return UserInfo(
            id=user.id,
            username=user.username,
            email=user.email,
            role=user.role.value,
            is_active=user.is_active,
            created_at=user.created_at.isoformat(),
            last_login=user.last_login.isoformat() if user.last_login else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
) -> TokenResponse:
    """Authenticate and get JWT tokens."""
    auth_service = _get_auth_service(request)
    tokens = auth_service.authenticate(body.username, body.password)
    if tokens is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    body: RefreshRequest,
    request: Request,
) -> TokenResponse:
    """Refresh access token."""
    auth_service = _get_auth_service(request)
    tokens = auth_service.refresh_access_token(body.refresh_token)
    if tokens is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post("/logout")
async def logout(
    request: Request,
    payload: dict[str, Any] = Depends(get_current_user_payload),
) -> dict[str, str]:
    """Revoke current token."""
    auth_service = _get_auth_service(request)
    # Extract token from header
    authorization = request.headers.get("authorization", "")
    _, _, token = authorization.partition(" ")
    if token:
        auth_service.revoke_token(token)
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserInfo)
async def get_me(
    request: Request,
    payload: dict[str, Any] = Depends(get_current_user_payload),
) -> UserInfo:
    """Get current user info."""
    auth_service = _get_auth_service(request)
    user = auth_service.get_user(payload["sub"])
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserInfo(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role.value,
        is_active=user.is_active,
        created_at=user.created_at.isoformat(),
        last_login=user.last_login.isoformat() if user.last_login else None,
    )


@router.get("/users", response_model=list[UserInfo])
async def list_users(
    request: Request,
    payload: dict[str, Any] = Depends(require_role(UserRole.ADMIN)),
) -> list[UserInfo]:
    """List all users (admin only)."""
    auth_service = _get_auth_service(request)
    return [
        UserInfo(
            id=u.id,
            username=u.username,
            email=u.email,
            role=u.role.value,
            is_active=u.is_active,
            created_at=u.created_at.isoformat(),
            last_login=u.last_login.isoformat() if u.last_login else None,
        )
        for u in auth_service.list_users()
    ]

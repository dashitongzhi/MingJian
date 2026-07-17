"""Auth API routes — JWT authentication endpoints."""

from __future__ import annotations

from collections.abc import Callable
from ipaddress import ip_address
from secrets import compare_digest
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from planagent.services.auth import AuthService, UserRole
from planagent.services.login_throttle import LoginAttemptLimiter

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ── Request / Response Models ─────────────────────────────────


class RegisterRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    username: str = Field(min_length=3, max_length=32)
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=6, max_length=72)
    role: Literal["analyst", "viewer"] = "analyst"  # admin only via admin endpoint

    @field_validator("password")
    @classmethod
    def validate_password_size(cls, value: str) -> str:
        return _validate_bcrypt_password_size(value)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=72)

    @field_validator("password")
    @classmethod
    def validate_password_size(cls, value: str) -> str:
        return _validate_bcrypt_password_size(value)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=6, max_length=72)
    new_password: str = Field(min_length=12, max_length=72)

    @field_validator("current_password", "new_password")
    @classmethod
    def validate_password_size(cls, value: str) -> str:
        return _validate_bcrypt_password_size(value)


class UserInfo(BaseModel):
    id: str
    username: str
    email: str
    role: str
    is_active: bool
    created_at: str
    last_login: str | None = None


def _validate_bcrypt_password_size(value: str) -> str:
    if len(value.encode("utf-8")) > 72:
        raise ValueError("Password must not exceed 72 UTF-8 bytes")
    return value


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
            default_admin_password=settings.bootstrap_admin_password or None,
        )
        app.state.auth_service = AuthService(config)
    return app.state.auth_service  # type: ignore[no-any-return]  # app.state 动态属性


def _get_login_attempt_limiter(request: Request) -> LoginAttemptLimiter:
    limiter = getattr(request.app.state, "login_attempt_limiter", None)
    if not isinstance(limiter, LoginAttemptLimiter):
        limiter = LoginAttemptLimiter()
        request.app.state.login_attempt_limiter = limiter
    return limiter


def _login_attempt_key(request: Request, username: str) -> str:
    client_host = request.client.host if request.client else "unknown"
    return f"{client_host}\0{username.strip().casefold()}"


def _enforce_remote_admin_session(
    request: Request,
    auth_service: AuthService,
    access_token: str,
) -> None:
    from planagent.config import get_settings

    if not get_settings().remote_access_enabled:
        return
    payload = auth_service.verify_token(access_token)
    if payload is not None and payload.get("role") == UserRole.ADMIN.value:
        return
    if payload is not None and isinstance(payload.get("sub"), str):
        auth_service.revoke_user_sessions(payload["sub"])
    raise HTTPException(
        status_code=403,
        detail="Community remote access is administrator-only",
    )


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
        payload = _verify_bearer_authorization(app, authorization)
        if payload.get("role") != UserRole.ADMIN.value:
            raise HTTPException(
                status_code=403,
                detail="Community remote access is administrator-only",
            )
        return payload
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


def require_role(required_role: UserRole) -> Callable[..., dict[str, Any]]:
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
    if settings.remote_access_enabled:
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
    limiter = _get_login_attempt_limiter(request)
    attempt_key = _login_attempt_key(request, body.username)
    retry_after = limiter.retry_after(attempt_key)
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts",
            headers={"Retry-After": str(retry_after)},
        )
    auth_service = _get_auth_service(request)
    tokens = auth_service.authenticate(body.username, body.password)
    if tokens is None:
        limiter.record_failure(attempt_key)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    _enforce_remote_admin_session(request, auth_service, tokens.access_token)
    limiter.clear(attempt_key)
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
    _enforce_remote_admin_session(request, auth_service, tokens.access_token)
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    payload: dict[str, Any] = Depends(get_current_user_payload),
) -> dict[str, str]:
    """Rotate the current user's password and invalidate all existing sessions."""
    auth_service = _get_auth_service(request)
    if not auth_service.change_password(
        str(payload["sub"]),
        body.current_password,
        body.new_password,
    ):
        raise HTTPException(status_code=400, detail="Current password is invalid")

    authorization = request.headers.get("authorization", "")
    _, _, token = authorization.partition(" ")
    if token:
        auth_service.revoke_token(token)
    return {"message": "Password changed successfully"}


@router.post("/logout")
async def logout(
    request: Request,
    payload: dict[str, Any] = Depends(get_current_user_payload),
) -> dict[str, str]:
    """Invalidate every session issued to the current Community user."""
    auth_service = _get_auth_service(request)
    auth_service.revoke_user_sessions(str(payload["sub"]))
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

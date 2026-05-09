"""JWT authentication and authorization service.

Addresses the audit gap: all API endpoints are publicly accessible.
Provides JWT-based auth with role-based access control.
"""

from __future__ import annotations

import logging
import secrets
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any

import bcrypt
import jwt

from planagent.domain.models import utc_now

_logger = logging.getLogger(__name__)


class UserRole(StrEnum):
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


@dataclass
class AuthConfig:
    """Auth configuration."""

    secret_key: str = ""  # Auto-generated if empty
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30
    issuer: str = "planagent"


@dataclass
class User:
    """In-memory user model. In production, this would be a DB model."""

    id: str
    username: str
    email: str
    password_hash: str
    role: UserRole = UserRole.ANALYST
    is_active: bool = True
    created_at: datetime = field(default_factory=utc_now)
    last_login: datetime | None = None


@dataclass
class TokenPair:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600


class AuthService:
    """JWT-based authentication service.

    Features:
    - User registration and login
    - JWT access + refresh tokens
    - Role-based access control (admin / analyst / viewer)
    - Token refresh and revocation
    """

    def __init__(self, config: AuthConfig | None = None) -> None:
        self.config = config or AuthConfig()
        if not self.config.secret_key:
            self.config.secret_key = secrets.token_urlsafe(48)
            _logger.warning(
                "Auth secret_key auto-generated (not persistent across restarts). Set PLANAGENT_AUTH_SECRET_KEY in .env"
            )

        self._users: dict[str, User] = {}  # user_id -> User
        self._username_index: dict[str, str] = {}  # username -> user_id
        self._email_index: dict[str, str] = {}  # email -> user_id
        self._revoked_tokens: OrderedDict[str, None] = OrderedDict()  # bounded FIFO
        self._max_revoked_tokens: int = 10_000
        self._refresh_tokens: dict[str, str] = {}  # refresh_token -> user_id

        # Create default admin if no users exist
        self._ensure_default_admin()

    def _ensure_default_admin(self) -> None:
        """Create a default admin user if none exists."""
        if not self._users:
            import secrets as _secrets

            random_password = _secrets.token_urlsafe(16)
            self.create_user(
                username="admin",
                email="admin@planagent.local",
                password=random_password,
                role=UserRole.ADMIN,
            )
            _logger.warning(
                "Default admin created — username: admin, password: %s (CHANGE THIS IMMEDIATELY)",
                random_password,
            )

    # ── User Management ───────────────────────────────────────

    def create_user(
        self,
        username: str,
        email: str,
        password: str,
        role: UserRole = UserRole.ANALYST,
    ) -> User:
        """Register a new user."""
        if username in self._username_index:
            raise ValueError(f"Username '{username}' already exists")
        if email in self._email_index:
            raise ValueError(f"Email '{email}' already exists")

        user_id = str(uuid.uuid4())
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        user = User(
            id=user_id,
            username=username,
            email=email,
            password_hash=password_hash,
            role=role,
        )

        self._users[user_id] = user
        self._username_index[username] = user_id
        self._email_index[email] = user_id
        return user

    def authenticate(self, username: str, password: str) -> TokenPair | None:
        """Authenticate user and return token pair."""
        user_id = self._username_index.get(username)
        if not user_id:
            return None

        user = self._users[user_id]
        if not user.is_active:
            return None

        if not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            return None

        user.last_login = utc_now()
        return self._create_token_pair(user)

    def refresh_access_token(self, refresh_token: str) -> TokenPair | None:
        """Get new access token using refresh token."""
        if refresh_token in self._revoked_tokens:
            return None

        user_id = self._refresh_tokens.get(refresh_token)
        if not user_id:
            # Try to decode it
            try:
                payload = jwt.decode(
                    refresh_token,
                    self.config.secret_key,
                    algorithms=[self.config.algorithm],
                )
                if payload.get("type") != "refresh":
                    return None
                user_id = payload.get("sub")
            except jwt.InvalidTokenError:
                return None

        if not user_id or user_id not in self._users:
            return None

        user = self._users[user_id]
        if not user.is_active:
            return None

        # Revoke old refresh token
        self.revoke_token(refresh_token)
        self._refresh_tokens.pop(refresh_token, None)

        return self._create_token_pair(user)

    def revoke_token(self, token: str) -> None:
        """Revoke a token.

        Evicts the oldest entry when the revoked-token set exceeds
        ``_max_revoked_tokens`` to prevent unbounded memory growth in
        long-running services.
        """
        if token in self._revoked_tokens:
            return
        self._revoked_tokens[token] = None
        while len(self._revoked_tokens) > self._max_revoked_tokens:
            self._revoked_tokens.popitem(last=False)
        self._refresh_tokens.pop(token, None)

    # ── Token Operations ──────────────────────────────────────

    def _create_token_pair(self, user: User) -> TokenPair:
        """Create access + refresh token pair."""
        now = datetime.now(timezone.utc)

        # Access token
        access_payload = {
            "sub": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role.value,
            "type": "access",
            "iss": self.config.issuer,
            "iat": now,
            "exp": now + timedelta(minutes=self.config.access_token_expire_minutes),
        }
        access_token = jwt.encode(
            access_payload, self.config.secret_key, algorithm=self.config.algorithm
        )

        # Refresh token
        refresh_payload = {
            "sub": user.id,
            "type": "refresh",
            "iss": self.config.issuer,
            "iat": now,
            "exp": now + timedelta(days=self.config.refresh_token_expire_days),
        }
        refresh_token = jwt.encode(
            refresh_payload, self.config.secret_key, algorithm=self.config.algorithm
        )
        self._refresh_tokens[refresh_token] = user.id

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self.config.access_token_expire_minutes * 60,
        )

    def verify_token(self, token: str) -> dict[str, Any] | None:
        """Verify and decode a JWT token. Returns payload or None if invalid."""
        if token in self._revoked_tokens:
            return None

        try:
            payload = jwt.decode(
                token,
                self.config.secret_key,
                algorithms=[self.config.algorithm],
            )
            if payload.get("type") != "access":
                return None

            # Check user still exists and is active
            user_id = payload.get("sub")
            if user_id and user_id in self._users:
                if not self._users[user_id].is_active:
                    return None

            return payload
        except jwt.InvalidTokenError:
            return None

    # ── User Query ────────────────────────────────────────────

    def get_user(self, user_id: str) -> User | None:
        return self._users.get(user_id)

    def get_user_by_username(self, username: str) -> User | None:
        user_id = self._username_index.get(username)
        return self._users.get(user_id) if user_id else None

    def list_users(self) -> list[User]:
        return list(self._users.values())

    def update_user_role(self, user_id: str, role: UserRole) -> User | None:
        user = self._users.get(user_id)
        if user:
            user.role = role
        return user

    def deactivate_user(self, user_id: str) -> bool:
        user = self._users.get(user_id)
        if user:
            user.is_active = False
            return True
        return False

    # ── Authorization Helpers ─────────────────────────────────

    def check_role(self, payload: dict[str, Any], required_role: UserRole) -> bool:
        """Check if token payload has the required role (or higher)."""
        role_hierarchy = {
            UserRole.VIEWER: 0,
            UserRole.ANALYST: 1,
            UserRole.ADMIN: 2,
        }
        user_role = UserRole(payload.get("role", "viewer"))
        return role_hierarchy.get(user_role, 0) >= role_hierarchy.get(required_role, 0)

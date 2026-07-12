"""JWT authentication and authorization service.

Addresses the audit gap: all API endpoints are publicly accessible.
Provides JWT-based auth with role-based access control.
"""

from __future__ import annotations

import logging
import secrets
import hashlib
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any

import bcrypt
import jwt
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from planagent.domain.models import AuthRefreshToken, AuthRevokedToken, AuthUser, utc_now

_logger = logging.getLogger(__name__)


class UserRole(StrEnum):
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


@dataclass
class AuthConfig:
    """Auth configuration."""

    secret_key: str = ""  # Auto-generated only for development/test.
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30
    issuer: str = "planagent"
    database_url: str | None = None
    environment: str = "development"
    create_default_admin: bool = True


@dataclass
class User:
    """Auth user returned by AuthService."""

    id: str
    username: str
    email: str
    password_hash: str
    role: UserRole = UserRole.ANALYST
    is_active: bool = True
    created_at: datetime = field(default_factory=utc_now)
    last_login: datetime | None = None
    auth_provider: str | None = None
    external_id: str | None = None


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
            if self.config.environment.lower() not in {"dev", "development", "test", "testing"}:
                raise RuntimeError("PLANAGENT_AUTH_SECRET_KEY is required outside development/test")
            self.config.secret_key = secrets.token_urlsafe(48)
            _logger.warning("Auth secret_key auto-generated for local development only")

        self._session_factory: sessionmaker[Session] | None = None
        self._engine: Engine | None = None
        if self.config.database_url:
            self._engine = create_engine(
                _sync_database_url(self.config.database_url),
                future=True,
                pool_pre_ping=True,
            )
            self._session_factory = sessionmaker(bind=self._engine, expire_on_commit=False)

        self._users: dict[str, User] = {}  # user_id -> User
        self._username_index: dict[str, str] = {}  # username -> user_id
        self._email_index: dict[str, str] = {}  # email -> user_id
        self._revoked_tokens: set[str] | OrderedDict[str, None]
        self._revoked_tokens = OrderedDict() if self._db_enabled else set()
        self._max_revoked_tokens: int = 100_000
        self._refresh_tokens: dict[str, str] = {}  # token_hash -> user_id

        if self.config.create_default_admin:
            self._ensure_default_admin()

    @property
    def _db_enabled(self) -> bool:
        return self._session_factory is not None

    def _session(self) -> Session:
        if self._session_factory is None:
            raise RuntimeError("AuthService was not configured with a database_url")
        return self._session_factory()

    def _ensure_default_admin(self) -> None:
        """Create a default admin user if none exists."""
        if self._db_enabled:
            with self._session() as session:
                has_user = session.execute(select(AuthUser.id).limit(1)).scalar_one_or_none()
                if has_user:
                    return
        elif self._users:
            return

        random_password = secrets.token_urlsafe(16)
        self.create_user(
            username="admin",
            email="admin@planagent.local",
            password=random_password,
            role=UserRole.ADMIN,
        )
        _logger.warning(
            "Default admin created for bootstrap; generated password was not logged. Reset it before operational use."
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
        if self._db_enabled:
            with self._session() as session:
                existing = session.execute(
                    select(AuthUser).where(
                        (AuthUser.username == username) | (AuthUser.email == email)
                    )
                ).scalar_one_or_none()
                if existing:
                    if existing.username == username:
                        raise ValueError(f"Username '{username}' already exists")
                    raise ValueError(f"Email '{email}' already exists")

                password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
                record = AuthUser(
                    id=str(uuid.uuid4()),
                    username=username,
                    email=email,
                    password_hash=password_hash,
                    role=role.value,
                    is_active=True,
                )
                session.add(record)
                session.commit()
                session.refresh(record)
                return _user_from_record(record)

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
        if self._db_enabled:
            with self._session() as session:
                record = session.execute(
                    select(AuthUser).where(AuthUser.username == username)
                ).scalar_one_or_none()
                if record is None or not record.is_active:
                    return None
                if not bcrypt.checkpw(password.encode(), record.password_hash.encode()):
                    return None
                record.last_login = utc_now()
                session.commit()
                return self._create_token_pair(_user_from_record(record))

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
        token_hash = _hash_token(refresh_token)
        if self._is_token_revoked(refresh_token):
            return None

        user_id = self._refresh_tokens.get(token_hash)
        if not user_id:
            user_id = self._lookup_refresh_token_user(refresh_token)

        if not user_id:
            return None

        user = self.get_user(user_id)
        if user is None:
            return None
        if not user.is_active:
            return None

        self.revoke_token(refresh_token)

        return self._create_token_pair(user)

    def revoke_token(self, token: str) -> None:
        """Revoke a token while preserving revocation semantics in every mode."""
        token_hash = _hash_token(token)
        expires_at = _token_expires_at(token, self.config.secret_key, self.config.algorithm)
        if self._db_enabled:
            with self._session() as session:
                refresh = session.get(AuthRefreshToken, token_hash)
                if refresh:
                    refresh.revoked_at = utc_now()
                if session.get(AuthRevokedToken, token_hash) is None:
                    session.add(AuthRevokedToken(token_hash=token_hash, expires_at=expires_at))
                session.commit()
            self._revoked_tokens[token_hash] = None
            while len(self._revoked_tokens) > self._max_revoked_tokens:
                self._revoked_tokens.popitem(last=False)
        else:
            self._revoked_tokens.add(token_hash)
        self._refresh_tokens.pop(token_hash, None)

    # ── Token Operations ──────────────────────────────────────

    def _create_token_pair(self, user: User) -> TokenPair:
        """Create access + refresh token pair."""
        now = datetime.now(timezone.utc)

        # Access token
        access_payload = {
            "jti": str(uuid.uuid4()),
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
            "jti": str(uuid.uuid4()),
            "sub": user.id,
            "type": "refresh",
            "iss": self.config.issuer,
            "iat": now,
            "exp": now + timedelta(days=self.config.refresh_token_expire_days),
        }
        refresh_token = jwt.encode(
            refresh_payload, self.config.secret_key, algorithm=self.config.algorithm
        )
        token_hash = _hash_token(refresh_token)
        self._refresh_tokens[token_hash] = user.id
        if self._db_enabled:
            with self._session() as session:
                session.add(
                    AuthRefreshToken(
                        token_hash=token_hash,
                        user_id=user.id,
                        issued_at=now,
                        expires_at=now + timedelta(days=self.config.refresh_token_expire_days),
                    )
                )
                session.commit()

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self.config.access_token_expire_minutes * 60,
        )

    def verify_token(self, token: str) -> dict[str, Any] | None:
        """Verify and decode a JWT token. Returns payload or None if invalid."""
        if self._is_token_revoked(token):
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
            if user_id:
                user = self.get_user(user_id)
                if user is None or not user.is_active:
                    return None

            return payload
        except jwt.InvalidTokenError:
            return None

    # ── User Query ────────────────────────────────────────────

    def get_user(self, user_id: str) -> User | None:
        if self._db_enabled:
            with self._session() as session:
                record = session.get(AuthUser, user_id)
                return _user_from_record(record) if record else None
        return self._users.get(user_id)

    def get_user_by_username(self, username: str) -> User | None:
        if self._db_enabled:
            with self._session() as session:
                record = session.execute(
                    select(AuthUser).where(AuthUser.username == username)
                ).scalar_one_or_none()
                return _user_from_record(record) if record else None
        user_id = self._username_index.get(username)
        return self._users.get(user_id) if user_id else None

    def list_users(self) -> list[User]:
        if self._db_enabled:
            with self._session() as session:
                records = session.execute(select(AuthUser).order_by(AuthUser.created_at)).scalars()
                return [_user_from_record(record) for record in records]
        return list(self._users.values())

    def update_user_role(self, user_id: str, role: UserRole) -> User | None:
        if self._db_enabled:
            with self._session() as session:
                record = session.get(AuthUser, user_id)
                if record is None:
                    return None
                record.role = role.value
                session.commit()
                session.refresh(record)
                return _user_from_record(record)
        user = self._users.get(user_id)
        if user:
            user.role = role
        return user

    def deactivate_user(self, user_id: str) -> bool:
        if self._db_enabled:
            with self._session() as session:
                record = session.get(AuthUser, user_id)
                if record is None:
                    return False
                record.is_active = False
                session.commit()
                return True
        user = self._users.get(user_id)
        if user:
            user.is_active = False
            return True
        return False

    def _lookup_refresh_token_user(self, refresh_token: str) -> str | None:
        try:
            payload = jwt.decode(
                refresh_token,
                self.config.secret_key,
                algorithms=[self.config.algorithm],
            )
            if payload.get("type") != "refresh":
                return None
        except jwt.InvalidTokenError:
            return None

        token_hash = _hash_token(refresh_token)
        if self._db_enabled:
            now = utc_now()
            with self._session() as session:
                record = session.get(AuthRefreshToken, token_hash)
                if (
                    record is None
                    or record.revoked_at is not None
                    or _as_utc(record.expires_at) <= now
                ):
                    return None
                return record.user_id
        return self._refresh_tokens.get(token_hash)

    def _is_token_revoked(self, token: str) -> bool:
        token_hash = _hash_token(token)
        if token_hash in self._revoked_tokens:
            return True
        if self._db_enabled:
            with self._session() as session:
                return session.get(AuthRevokedToken, token_hash) is not None
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


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _token_expires_at(token: str, secret_key: str, algorithm: str) -> datetime | None:
    try:
        payload = jwt.decode(
            token, secret_key, algorithms=[algorithm], options={"verify_exp": False}
        )
    except jwt.InvalidTokenError:
        return None
    exp = payload.get("exp")
    if exp is None:
        return None
    return datetime.fromtimestamp(float(exp), tz=timezone.utc)


def _sync_database_url(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://").replace(
        "sqlite+aiosqlite://", "sqlite://"
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _user_from_record(record: AuthUser) -> User:
    return User(
        id=record.id,
        username=record.username,
        email=record.email,
        password_hash=record.password_hash,
        role=UserRole(record.role),
        is_active=record.is_active,
        created_at=record.created_at,
        last_login=record.last_login,
        auth_provider=record.auth_provider,
        external_id=record.external_id,
    )

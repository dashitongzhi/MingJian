"""Unit tests for AuthService — JWT 认证与授权服务。"""

from __future__ import annotations

import pytest
import jwt

from planagent.domain.models import Base
from planagent.services.auth import AuthConfig, AuthService, UserRole


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def auth_service():
    """创建一个不自动创建默认 admin 的 AuthService。"""
    return AuthService(
        AuthConfig(
            secret_key="test-secret-key-for-unit-tests",
            algorithm="HS256",
            create_default_admin=False,
        )
    )


@pytest.fixture()
def auth_service_with_admin():
    """创建一个包含默认 admin 用户的 AuthService。"""
    svc = AuthService(config=AuthConfig(secret_key="test-secret-key"))
    return svc


def make_db_auth_service(db_url: str) -> AuthService:
    svc = AuthService(
        AuthConfig(
            secret_key="test-secret-key-for-unit-tests",
            algorithm="HS256",
            database_url=db_url,
            environment="test",
            create_default_admin=False,
        )
    )
    Base.metadata.create_all(svc._engine)
    return svc


# ---------------------------------------------------------------------------
# 用户创建
# ---------------------------------------------------------------------------


class TestUserCreation:
    """测试用户创建和密码验证。"""

    def test_create_user_success(self, auth_service: AuthService):
        """正常创建用户应返回 User 对象。"""
        user = auth_service.create_user("alice", "alice@test.com", "password123")
        assert user.username == "alice"
        assert user.email == "alice@test.com"
        assert user.role == UserRole.ANALYST
        assert user.is_active is True
        assert user.id  # 自动生成 UUID

    def test_create_user_with_role(self, auth_service: AuthService):
        """创建用户时可以指定角色。"""
        user = auth_service.create_user("bob", "bob@test.com", "pass", role=UserRole.ADMIN)
        assert user.role == UserRole.ADMIN

    def test_create_user_duplicate_username(self, auth_service: AuthService):
        """重复用户名应抛出 ValueError。"""
        auth_service.create_user("alice", "alice@test.com", "pass")
        with pytest.raises(ValueError, match="already exists"):
            auth_service.create_user("alice", "other@test.com", "pass2")

    def test_create_user_duplicate_email(self, auth_service: AuthService):
        """重复邮箱应抛出 ValueError。"""
        auth_service.create_user("alice", "alice@test.com", "pass")
        with pytest.raises(ValueError, match="already exists"):
            auth_service.create_user("bob", "alice@test.com", "pass2")

    def test_password_hashed(self, auth_service: AuthService):
        """密码不应以明文存储。"""
        user = auth_service.create_user("carol", "carol@test.com", "mypassword")
        assert user.password_hash != "mypassword"
        assert len(user.password_hash) > 0

    def test_password_verification(self, auth_service: AuthService):
        """使用正确密码应能成功认证。"""
        auth_service.create_user("dave", "dave@test.com", "secret")
        tokens = auth_service.authenticate("dave", "secret")
        assert tokens is not None
        assert tokens.access_token
        assert tokens.refresh_token

    def test_wrong_password_returns_none(self, auth_service: AuthService):
        """使用错误密码应返回 None。"""
        auth_service.create_user("eve", "eve@test.com", "correct")
        tokens = auth_service.authenticate("eve", "wrong")
        assert tokens is None

    def test_nonexistent_user_returns_none(self, auth_service: AuthService):
        """不存在的用户名应返回 None。"""
        tokens = auth_service.authenticate("nobody", "pass")
        assert tokens is None


# ---------------------------------------------------------------------------
# JWT Token 生成和验证
# ---------------------------------------------------------------------------


class TestTokenGeneration:
    """测试 JWT token 生成和验证。"""

    def test_access_token_is_valid_jwt(self, auth_service: AuthService):
        """生成的 access token 应该是合法的 JWT。"""
        auth_service.create_user("u1", "u1@test.com", "pass")
        tokens = auth_service.authenticate("u1", "pass")
        payload = jwt.decode(
            tokens.access_token,
            "test-secret-key-for-unit-tests",
            algorithms=["HS256"],
        )
        assert payload["type"] == "access"
        assert payload["username"] == "u1"
        assert payload["role"] == "analyst"

    def test_refresh_token_type(self, auth_service: AuthService):
        """refresh token 应该标记为 refresh 类型。"""
        auth_service.create_user("u2", "u2@test.com", "pass")
        tokens = auth_service.authenticate("u2", "pass")
        payload = jwt.decode(
            tokens.refresh_token,
            "test-secret-key-for-unit-tests",
            algorithms=["HS256"],
        )
        assert payload["type"] == "refresh"

    def test_verify_token_returns_payload(self, auth_service: AuthService):
        """verify_token 应返回完整的 token payload。"""
        auth_service.create_user("u3", "u3@test.com", "pass")
        tokens = auth_service.authenticate("u3", "pass")
        payload = auth_service.verify_token(tokens.access_token)
        assert payload is not None
        assert payload["sub"] == auth_service._username_index["u3"]
        assert payload["type"] == "access"

    def test_verify_token_returns_none_for_missing_user(self, auth_service: AuthService):
        """用户不存在时旧 access token 应失效。"""
        user = auth_service.create_user("u3b", "u3b@test.com", "pass")
        tokens = auth_service.authenticate("u3b", "pass")
        auth_service._users.pop(user.id)
        auth_service._username_index.pop(user.username)
        auth_service._email_index.pop(user.email)
        assert auth_service.verify_token(tokens.access_token) is None

    def test_verify_token_returns_none_for_refresh(self, auth_service: AuthService):
        """verify_token 不应该接受 refresh token。"""
        auth_service.create_user("u4", "u4@test.com", "pass")
        tokens = auth_service.authenticate("u4", "pass")
        payload = auth_service.verify_token(tokens.refresh_token)
        assert payload is None

    def test_verify_token_returns_none_for_tampered(self, auth_service: AuthService):
        """被篡改的 token 应验证失败。"""
        auth_service.create_user("u5", "u5@test.com", "pass")
        tokens = auth_service.authenticate("u5", "pass")
        payload = auth_service.verify_token(tokens.access_token + "tampered")
        assert payload is None

    def test_token_contains_issuer(self, auth_service: AuthService):
        """token 中应包含 issuer 字段。"""
        auth_service.create_user("u6", "u6@test.com", "pass")
        tokens = auth_service.authenticate("u6", "pass")
        payload = auth_service.verify_token(tokens.access_token)
        assert payload["iss"] == "planagent"

    def test_token_pair_has_correct_type_and_expires(self, auth_service: AuthService):
        """TokenPair 应返回正确的 token_type 和 expires_in。"""
        auth_service.create_user("u7", "u7@test.com", "pass")
        tokens = auth_service.authenticate("u7", "pass")
        assert tokens.token_type == "bearer"
        assert tokens.expires_in == 60 * 60  # 60 minutes


# ---------------------------------------------------------------------------
# Token 刷新机制
# ---------------------------------------------------------------------------


class TestTokenRefresh:
    """测试 token 刷新机制。"""

    def test_refresh_returns_valid_token_pair(self, auth_service: AuthService):
        """使用 refresh token 应获得可用的 token 对（access token 可验证）。"""
        auth_service.create_user("r1", "r1@test.com", "pass")
        tokens1 = auth_service.authenticate("r1", "pass")
        tokens2 = auth_service.refresh_access_token(tokens1.refresh_token)
        assert tokens2 is not None
        assert tokens2.token_type == "bearer"
        # 新的 access token 应可验证
        payload = auth_service.verify_token(tokens2.access_token)
        assert payload is not None
        assert payload["username"] == "r1"
        assert payload["type"] == "access"

    def test_old_refresh_token_revoked_after_refresh(self, auth_service: AuthService):
        """刷新后旧的 refresh token 应被撤销。"""
        auth_service.create_user("r2", "r2@test.com", "pass")
        tokens1 = auth_service.authenticate("r2", "pass")
        auth_service.refresh_access_token(tokens1.refresh_token)
        # 再次使用旧 refresh token 应失败
        result = auth_service.refresh_access_token(tokens1.refresh_token)
        assert result is None

    def test_refresh_with_revoked_token_returns_none(self, auth_service: AuthService):
        """已撤销的 refresh token 应返回 None。"""
        auth_service.create_user("r3", "r3@test.com", "pass")
        tokens = auth_service.authenticate("r3", "pass")
        auth_service.revoke_token(tokens.refresh_token)
        result = auth_service.refresh_access_token(tokens.refresh_token)
        assert result is None

    def test_refresh_with_invalid_token_returns_none(self, auth_service: AuthService):
        """无效的 refresh token 应返回 None。"""
        result = auth_service.refresh_access_token("not-a-real-token")
        assert result is None

    def test_inactive_user_cannot_refresh(self, auth_service: AuthService):
        """已停用用户的 refresh token 应返回 None。"""
        user = auth_service.create_user("r4", "r4@test.com", "pass")
        tokens = auth_service.authenticate("r4", "pass")
        auth_service.deactivate_user(user.id)
        result = auth_service.refresh_access_token(tokens.refresh_token)
        assert result is None


# ---------------------------------------------------------------------------
# 角色权限
# ---------------------------------------------------------------------------


class TestRoleAuthorization:
    """测试角色权限（admin/analyst/viewer）。"""

    def test_admin_has_admin_role(self, auth_service: AuthService):
        """admin 用户的 payload 应包含 admin 角色。"""
        auth_service.create_user("adm", "adm@test.com", "pass", role=UserRole.ADMIN)
        tokens = auth_service.authenticate("adm", "pass")
        payload = auth_service.verify_token(tokens.access_token)
        assert auth_service.check_role(payload, UserRole.ADMIN) is True

    def test_admin_can_access_analyst(self, auth_service: AuthService):
        """admin 应能访问 analyst 级别的资源。"""
        auth_service.create_user("adm2", "adm2@test.com", "pass", role=UserRole.ADMIN)
        tokens = auth_service.authenticate("adm2", "pass")
        payload = auth_service.verify_token(tokens.access_token)
        assert auth_service.check_role(payload, UserRole.ANALYST) is True

    def test_admin_can_access_viewer(self, auth_service: AuthService):
        """admin 应能访问 viewer 级别的资源。"""
        auth_service.create_user("adm3", "adm3@test.com", "pass", role=UserRole.ADMIN)
        tokens = auth_service.authenticate("adm3", "pass")
        payload = auth_service.verify_token(tokens.access_token)
        assert auth_service.check_role(payload, UserRole.VIEWER) is True

    def test_viewer_cannot_access_admin(self, auth_service: AuthService):
        """viewer 不应能访问 admin 级别的资源。"""
        auth_service.create_user("vis", "vis@test.com", "pass", role=UserRole.VIEWER)
        tokens = auth_service.authenticate("vis", "pass")
        payload = auth_service.verify_token(tokens.access_token)
        assert auth_service.check_role(payload, UserRole.ADMIN) is False

    def test_analyst_can_access_viewer(self, auth_service: AuthService):
        """analyst 应能访问 viewer 级别的资源。"""
        auth_service.create_user("ana", "ana@test.com", "pass", role=UserRole.ANALYST)
        tokens = auth_service.authenticate("ana", "pass")
        payload = auth_service.verify_token(tokens.access_token)
        assert auth_service.check_role(payload, UserRole.VIEWER) is True

    def test_analyst_cannot_access_admin(self, auth_service: AuthService):
        """analyst 不应能访问 admin 级别的资源。"""
        auth_service.create_user("ana2", "ana2@test.com", "pass", role=UserRole.ANALYST)
        tokens = auth_service.authenticate("ana2", "pass")
        payload = auth_service.verify_token(tokens.access_token)
        assert auth_service.check_role(payload, UserRole.ADMIN) is False

    def test_viewer_role_hierarchy_value(self, auth_service: AuthService):
        """viewer payload 应标记为 viewer 角色。"""
        auth_service.create_user("vis2", "vis2@test.com", "pass", role=UserRole.VIEWER)
        tokens = auth_service.authenticate("vis2", "pass")
        payload = auth_service.verify_token(tokens.access_token)
        assert payload["role"] == "viewer"


# ---------------------------------------------------------------------------
# Revoked Token 黑名单
# ---------------------------------------------------------------------------


class TestTokenRevocation:
    """测试 revoked token 黑名单。"""

    def test_revoke_access_token(self, auth_service: AuthService):
        """撤销 access token 后应验证失败。"""
        auth_service.create_user("v1", "v1@test.com", "pass")
        tokens = auth_service.authenticate("v1", "pass")
        auth_service.revoke_token(tokens.access_token)
        payload = auth_service.verify_token(tokens.access_token)
        assert payload is None

    def test_revoke_refresh_token(self, auth_service: AuthService):
        """撤销 refresh token 后应无法刷新。"""
        auth_service.create_user("v2", "v2@test.com", "pass")
        tokens = auth_service.authenticate("v2", "pass")
        auth_service.revoke_token(tokens.refresh_token)
        result = auth_service.refresh_access_token(tokens.refresh_token)
        assert result is None

    def test_revoke_nonexistent_token_no_error(self, auth_service: AuthService):
        """撤销不存在的 token 不应报错。"""
        auth_service.revoke_token("fake-token-that-does-not-exist")
        # 应该没有异常

    def test_multiple_tokens_independent(self, auth_service: AuthService):
        """撤销一个用户的 token 不应影响其他用户。"""
        auth_service.create_user("u_a", "ua@test.com", "pass")
        auth_service.create_user("u_b", "ub@test.com", "pass")
        tokens_a = auth_service.authenticate("u_a", "pass")
        tokens_b = auth_service.authenticate("u_b", "pass")

        auth_service.revoke_token(tokens_a.access_token)

        # u_a 的 token 应无效
        assert auth_service.verify_token(tokens_a.access_token) is None
        # u_b 的 token 应仍然有效
        assert auth_service.verify_token(tokens_b.access_token) is not None


# ---------------------------------------------------------------------------
# 默认 admin
# ---------------------------------------------------------------------------


class TestDefaultAdmin:
    """测试默认 admin 用户创建。"""

    def test_default_admin_created(self, auth_service_with_admin: AuthService):
        """AuthService 初始化时应自动创建 admin 用户。"""
        admin = auth_service_with_admin.get_user_by_username("admin")
        assert admin is not None
        assert admin.role == UserRole.ADMIN
        assert admin.email == "admin@planagent.local"

    def test_default_admin_can_authenticate(self, auth_service_with_admin: AuthService):
        """默认 admin 不应该能用空密码认证（密码是随机的）。"""
        tokens = auth_service_with_admin.authenticate("admin", "wrong-password")
        assert tokens is None

    def test_default_admin_password_not_logged(self, caplog):
        """默认 admin 日志不应泄漏随机明文密码。"""
        with caplog.at_level("WARNING"):
            AuthService(config=AuthConfig(secret_key="test-secret-key"))
        messages = "\n".join(record.getMessage() for record in caplog.records)
        assert "password:" not in messages
        assert "CHANGE THIS IMMEDIATELY" not in messages


# ---------------------------------------------------------------------------
# 用户管理辅助方法
# ---------------------------------------------------------------------------


class TestUserManagement:
    """测试用户管理辅助方法。"""

    def test_get_user(self, auth_service: AuthService):
        """get_user 应通过 user_id 查找用户。"""
        user = auth_service.create_user("m1", "m1@test.com", "pass")
        found = auth_service.get_user(user.id)
        assert found is not None
        assert found.username == "m1"

    def test_get_user_by_username(self, auth_service: AuthService):
        """get_user_by_username 应通过用户名查找用户。"""
        auth_service.create_user("m2", "m2@test.com", "pass")
        found = auth_service.get_user_by_username("m2")
        assert found is not None
        assert found.email == "m2@test.com"

    def test_list_users(self, auth_service: AuthService):
        """list_users 应返回所有用户。"""
        auth_service.create_user("l1", "l1@test.com", "pass")
        auth_service.create_user("l2", "l2@test.com", "pass")
        users = auth_service.list_users()
        assert len(users) == 2

    def test_update_user_role(self, auth_service: AuthService):
        """update_user_role 应更新用户角色。"""
        user = auth_service.create_user("r1", "r1@test.com", "pass", role=UserRole.VIEWER)
        updated = auth_service.update_user_role(user.id, UserRole.ADMIN)
        assert updated is not None
        assert updated.role == UserRole.ADMIN

    def test_deactivate_user(self, auth_service: AuthService):
        """deactivate_user 应停用用户，使其无法认证。"""
        user = auth_service.create_user("d1", "d1@test.com", "pass")
        assert auth_service.deactivate_user(user.id) is True
        tokens = auth_service.authenticate("d1", "pass")
        assert tokens is None

    def test_deactivate_nonexistent_user(self, auth_service: AuthService):
        """停用不存在的用户应返回 False。"""
        assert auth_service.deactivate_user("nonexistent-id") is False

    def test_inactive_user_auth_returns_none(self, auth_service: AuthService):
        """已停用用户不应能认证。"""
        user = auth_service.create_user("in1", "in1@test.com", "pass")
        auth_service.deactivate_user(user.id)
        assert auth_service.authenticate("in1", "pass") is None


class TestPersistentAuthStore:
    """测试 DB 持久化用户、refresh token、revoked token。"""

    def test_users_survive_service_restart(self, tmp_path):
        db_url = f"sqlite:///{tmp_path / 'auth.db'}"
        svc1 = make_db_auth_service(db_url)
        user = svc1.create_user("persisted", "persisted@test.com", "pass")

        svc2 = make_db_auth_service(db_url)
        found = svc2.get_user(user.id)
        assert found is not None
        assert found.username == "persisted"
        assert svc2.authenticate("persisted", "pass") is not None

    def test_refresh_token_survives_service_restart(self, tmp_path):
        db_url = f"sqlite:///{tmp_path / 'auth.db'}"
        svc1 = make_db_auth_service(db_url)
        svc1.create_user("refresh", "refresh@test.com", "pass")
        tokens = svc1.authenticate("refresh", "pass")

        svc2 = make_db_auth_service(db_url)
        refreshed = svc2.refresh_access_token(tokens.refresh_token)
        assert refreshed is not None
        assert svc2.verify_token(refreshed.access_token) is not None

    def test_revoked_token_survives_service_restart(self, tmp_path):
        db_url = f"sqlite:///{tmp_path / 'auth.db'}"
        svc1 = make_db_auth_service(db_url)
        svc1.create_user("revoked", "revoked@test.com", "pass")
        tokens = svc1.authenticate("revoked", "pass")
        svc1.revoke_token(tokens.access_token)

        svc2 = make_db_auth_service(db_url)
        assert svc2.verify_token(tokens.access_token) is None

    def test_production_requires_secret_key(self):
        with pytest.raises(RuntimeError, match="PLANAGENT_AUTH_SECRET_KEY"):
            AuthService(AuthConfig(secret_key="", environment="production"))

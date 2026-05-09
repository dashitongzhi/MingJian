"""Tests for new features: Auth, Notification, Export, Debate Optimization, Decision Feedback."""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from planagent.services.auth import AuthService, AuthConfig, UserRole
from planagent.services.notification import (
    NotificationService,
    NotificationConfig,
    NotificationChannel,
)
from planagent.services.export import ExportService
from planagent.services.debate.prompts import (
    build_round_plan,
    select_roles_for_domain,
)
from planagent.services.decision_feedback import DecisionFeedbackService, AccuracyReport


# ═══════════════════════════════════════════════════════════════
# Auth Service Tests
# ═══════════════════════════════════════════════════════════════

class TestAuthService:
    def setup_method(self):
        self.config = AuthConfig(secret_key="test-secret-key-for-testing-only")
        self.service = AuthService(self.config)

    def test_create_user(self):
        user = self.service.create_user("testuser", "test@example.com", "password123")
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.role == UserRole.ANALYST
        assert user.is_active is True

    def test_create_duplicate_user_raises(self):
        self.service.create_user("dup", "dup@example.com", "pass")
        with pytest.raises(ValueError, match="already exists"):
            self.service.create_user("dup", "dup2@example.com", "pass")

    def test_create_duplicate_email_raises(self):
        self.service.create_user("user1", "same@example.com", "pass")
        with pytest.raises(ValueError, match="already exists"):
            self.service.create_user("user2", "same@example.com", "pass")

    def test_authenticate_success(self):
        self.service.create_user("authuser", "auth@example.com", "mypassword")
        tokens = self.service.authenticate("authuser", "mypassword")
        assert tokens is not None
        assert tokens.access_token
        assert tokens.refresh_token
        assert tokens.token_type == "bearer"

    def test_authenticate_wrong_password(self):
        self.service.create_user("authuser2", "auth2@example.com", "correct")
        tokens = self.service.authenticate("authuser2", "wrong")
        assert tokens is None

    def test_authenticate_nonexistent_user(self):
        tokens = self.service.authenticate("nobody", "pass")
        assert tokens is None

    def test_verify_token(self):
        self.service.create_user("verify", "verify@example.com", "pass123")
        tokens = self.service.authenticate("verify", "pass123")
        assert tokens is not None
        payload = self.service.verify_token(tokens.access_token)
        assert payload is not None
        assert payload["username"] == "verify"
        assert payload["type"] == "access"

    def test_verify_revoked_token(self):
        self.service.create_user("revoke", "revoke@example.com", "pass123")
        tokens = self.service.authenticate("revoke", "pass123")
        assert tokens is not None
        self.service.revoke_token(tokens.access_token)
        payload = self.service.verify_token(tokens.access_token)
        assert payload is None

    def test_refresh_token(self):
        user = self.service.create_user("refresh", "refresh@example.com", "pass123")
        tokens = self.service.authenticate("refresh", "pass123")
        assert tokens is not None
        import time
        time.sleep(1.1)  # Ensure different iat (1-second granularity)
        new_tokens = self.service.refresh_access_token(tokens.refresh_token)
        assert new_tokens is not None
        assert new_tokens.access_token != tokens.access_token
        # Old refresh token should be revoked
        assert self.service.refresh_access_token(tokens.refresh_token) is None

    def test_role_hierarchy(self):
        self.service.create_user("viewer", "v@example.com", "pass", UserRole.VIEWER)
        self.service.create_user("analyst", "a@example.com", "pass", UserRole.ANALYST)
        # Use the default admin user
        admin_payload = {"role": "admin"}
        analyst_payload = {"role": "analyst"}
        viewer_payload = {"role": "viewer"}

        # Admin can access analyst-level
        assert self.service.check_role(admin_payload, UserRole.ANALYST) is True
        # Analyst can access viewer-level
        assert self.service.check_role(analyst_payload, UserRole.VIEWER) is True
        # Viewer cannot access analyst-level
        assert self.service.check_role(viewer_payload, UserRole.ANALYST) is False

    def test_deactivate_user(self):
        user = self.service.create_user("deactivate", "deact@example.com", "pass")
        assert self.service.deactivate_user(user.id) is True
        tokens = self.service.authenticate("deactivate", "pass")
        assert tokens is None

    def test_default_admin_created(self):
        """Default admin should exist on fresh service with random password."""
        admin = self.service.get_user_by_username("admin")
        assert admin is not None
        assert admin.role == UserRole.ADMIN
        # Password should be set (we can verify by authenticating)
        # Since password is random, just verify admin exists and is active
        assert admin.is_active is True


# ═══════════════════════════════════════════════════════════════
# Notification Service Tests
# ═══════════════════════════════════════════════════════════════

class TestNotificationService:
    def setup_method(self):
        self.service = NotificationService(NotificationConfig())

    @pytest.mark.asyncio
    async def test_websocket_notification_no_connections(self):
        """Should not raise when no connections exist."""
        notif = await self.service.notify(
            user_id="user1",
            title="Test",
            body="Hello",
            channel=NotificationChannel.WEBSOCKET,
        )
        assert not notif.delivered  # No connections

    @pytest.mark.asyncio
    async def test_websocket_notification_with_mock_connection(self):
        mock_ws = AsyncMock()
        self.service.register_ws("user1", mock_ws)

        notif = await self.service.notify(
            user_id="user1",
            title="Test",
            body="Hello",
            channel=NotificationChannel.WEBSOCKET,
        )
        assert notif.delivered is True
        mock_ws.send_text.assert_called_once()
        sent_data = json.loads(mock_ws.send_text.call_args[0][0])
        assert sent_data["title"] == "Test"
        assert sent_data["body"] == "Hello"

    def test_register_unregister_ws(self):
        mock_ws = MagicMock()
        self.service.register_ws("user1", mock_ws)
        assert "user1" in self.service._ws_connections

        self.service.unregister_ws("user1", mock_ws)
        assert "user1" not in self.service._ws_connections

    @pytest.mark.asyncio
    async def test_broadcast(self):
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()
        self.service.register_ws("user1", mock_ws1)
        self.service.register_ws("user2", mock_ws2)

        count = await self.service.broadcast(title="Alert", body="Something happened")
        assert count == 2

    def test_get_notifications(self):
        self.service._notification_log = [
            MagicMock(user_id="user1", delivered=True),
            MagicMock(user_id="user1", delivered=False),
            MagicMock(user_id="user2", delivered=True),
        ]
        notifs = self.service.get_notifications("user1")
        assert len(notifs) == 2

    def test_get_stats(self):
        stats = self.service.get_stats()
        assert "total" in stats
        assert "delivered" in stats
        assert "failed" in stats

    @pytest.mark.asyncio
    async def test_webhook_notification_no_config(self):
        """Should fail gracefully when no webhook URLs configured."""
        notif = await self.service.notify(
            user_id="user1",
            title="Test",
            body="Hello",
            channel=NotificationChannel.WEBHOOK,
        )
        assert not notif.delivered  # No webhook URLs

    @pytest.mark.asyncio
    async def test_email_notification_no_config(self):
        """Should fail when SMTP not configured."""
        notif = await self.service.notify(
            user_id="user1@example.com",
            title="Test",
            body="Hello",
            channel=NotificationChannel.EMAIL,
        )
        assert not notif.delivered
        assert notif.error is not None


# ═══════════════════════════════════════════════════════════════
# Export Service Tests
# ═══════════════════════════════════════════════════════════════

class TestExportService:
    def setup_method(self, tmp_path=None):
        import tempfile
        self.tmp_dir = tempfile.mkdtemp()
        self.service = ExportService(output_dir=self.tmp_dir)

    def test_export_analysis_md(self):
        data = {
            "domain_id": "corporate",
            "generated_at": "2024-01-01T00:00:00Z",
            "findings": ["Finding 1", "Finding 2"],
            "recommendations": ["Recommendation 1"],
            "risk_factors": ["Risk 1"],
            "sources": [
                {"title": "Source 1", "url": "http://example.com", "source_type": "news"},
            ],
            "confidence_score": 0.75,
        }
        md = self.service.export_analysis_md(data)
        assert "情报分析报告" in md
        assert "Finding 1" in md
        assert "Recommendation 1" in md
        assert "Risk 1" in md
        assert "Source 1" in md
        assert "75.0%" in md

    def test_export_assistant_result_md(self):
        data = {
            "topic": "AI Market Analysis",
            "domain_id": "corporate",
            "subject_name": "AI Industry",
            "generated_at": "2024-01-01T00:00:00Z",
            "analysis": {
                "findings": ["Market growing 30%"],
                "recommendations": ["Invest in AI chips"],
                "risk_factors": ["Regulatory risk"],
                "confidence_score": 0.8,
                "sources": [],
            },
            "debate": {
                "verdict": "Proceed with investment",
                "verdict_confidence": 0.75,
                "rounds": [],
                "recommendations": ["Diversify portfolio"],
                "risk_factors": ["Geopolitical risk"],
            },
            "panel_discussion": [
                {
                    "participant_id": "expert1",
                    "label": "AI Expert",
                    "summary": "Strong growth expected",
                    "recommendation": "Buy",
                    "confidence": 0.85,
                },
            ],
        }
        md = self.service.export_assistant_result_md(data)
        assert "战略决策报告" in md
        assert "AI Market Analysis" in md
        assert "情报分析" in md
        assert "多角色辩论" in md
        assert "专家讨论" in md

    def test_export_debate_md(self):
        data = {
            "topic": "Should we enter the Chinese market?",
            "domain_id": "corporate",
            "status": "COMPLETED",
            "rounds": [
                {
                    "round_number": 1,
                    "phase": "立论",
                    "messages": [
                        {"role": "advocate", "content": "Yes, because..."},
                    ],
                },
            ],
            "verdict": "Enter cautiously",
        }
        md = self.service.export_debate_md(data)
        assert "辩论报告" in md
        assert "Chinese market" in md
        assert "Enter cautiously" in md

    def test_md_to_pdf(self):
        pytest.importorskip("weasyprint")
        try:
            md = "# Test Report\n\nThis is a test with **bold** and *italic*."
            pdf_bytes = self.service.md_to_pdf(md, title="Test")
            assert isinstance(pdf_bytes, bytes)
            assert len(pdf_bytes) > 100
            assert pdf_bytes[:4] == b"%PDF"  # PDF magic bytes
        except OSError:
            pytest.skip("weasyprint system deps (pango/gobject) not available")

    def test_save_markdown(self):
        content = "# Test\n\nHello world"
        path = self.service.save_markdown(content, "test.md")
        assert path.exists()
        assert path.read_text(encoding="utf-8") == content

    def test_save_pdf(self):
        fake_pdf = b"%PDF-1.4 fake content"
        path = self.service.save_pdf(fake_pdf, "test.pdf")
        assert path.exists()
        assert path.read_bytes() == fake_pdf


# ═══════════════════════════════════════════════════════════════
# Debate Optimization Tests
# ═══════════════════════════════════════════════════════════════

class TestDebateOptimization:
    def test_full_round_plan_default(self):
        """Default should be full 4-round plan."""
        plan = build_round_plan()
        round_numbers = set(r[0] for r in plan)
        assert round_numbers == {1, 2, 3, 4}
        roles = set(r[1] for r in plan)
        assert "advocate" in roles
        assert "challenger" in roles
        assert "arbitrator" in roles

    def test_fast_round_plan(self):
        """Fast mode should have 2 rounds, 3 roles."""
        plan = build_round_plan(mode="fast")
        round_numbers = set(r[0] for r in plan)
        assert round_numbers == {1, 2}
        roles = set(r[1] for r in plan)
        assert "advocate" in roles
        assert "challenger" in roles
        # Should have 3 total entries
        assert len(plan) == 3

    def test_fast_round_plan_with_domain_corporate(self):
        """Corporate fast mode should use econ_analyst."""
        plan = build_round_plan(mode="fast", domain_id="corporate")
        roles = [r[1] for r in plan]
        assert "econ_analyst" in roles

    def test_fast_round_plan_with_domain_military(self):
        """Military fast mode should use military_strategist."""
        plan = build_round_plan(mode="fast", domain_id="military")
        roles = [r[1] for r in plan]
        assert "military_strategist" in roles

    def test_fast_round_plan_with_custom_agents(self):
        """Fast mode should include custom agents in round 1."""
        custom = [{"role_key": "custom_expert", "name": "Custom Expert", "icon": "🎯"}]
        plan = build_round_plan(custom_agents=custom, mode="fast")
        roles = [r[1] for r in plan]
        assert "custom_expert" in roles

    def test_select_roles_for_domain_corporate(self):
        roles = select_roles_for_domain("corporate")
        assert "econ_analyst" in roles
        assert "tech_foresight" in roles
        assert "advocate" in roles

    def test_select_roles_for_domain_military(self):
        roles = select_roles_for_domain("military")
        assert "military_strategist" in roles
        assert "geo_expert" in roles
        assert "advocate" in roles

    def test_select_roles_for_domain_auto(self):
        roles = select_roles_for_domain("auto")
        assert "intel_analyst" in roles
        assert "advocate" in roles

    def test_select_roles_for_unknown_domain(self):
        roles = select_roles_for_domain("unknown_domain")
        assert "advocate" in roles  # Core always included


# ═══════════════════════════════════════════════════════════════
# Decision Feedback Tests
# ═══════════════════════════════════════════════════════════════

class TestDecisionFeedbackService:
    def setup_method(self):
        self.service = DecisionFeedbackService()

    def test_accuracy_report_defaults(self):
        report = AccuracyReport()
        assert report.total_decisions == 0
        assert report.verified_outcomes == 0
        assert report.adopt_count == 0

    def test_report_counts(self):
        report = AccuracyReport(
            total_decisions=10,
            verified_outcomes=7,
            adopt_count=5,
            defer_count=2,
            reject_count=3,
            has_outcome=7,
        )
        assert report.total_decisions == 10
        assert report.adopt_count == 5
        assert report.has_outcome == 7

    def test_empty_report(self):
        report = AccuracyReport()
        assert report.total_decisions == 0
        assert report.details == []

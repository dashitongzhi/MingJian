"""Unit tests for planagent.config.Settings — env-var loading and OpenAI target resolution."""

from __future__ import annotations


import pytest
from pydantic import ValidationError

from planagent.config import Settings, OpenAIConfig, OpenAITargetConfig


# ---------------------------------------------------------------------------
# Settings construction from env vars
# ---------------------------------------------------------------------------


class TestSettingsFromEnv:
    def test_default_values(self, settings: Settings) -> None:
        assert settings.app_name == "PlanAgent"
        assert settings.env == "development"
        assert settings.bind_host == "127.0.0.1"
        assert settings.remote_registration_enabled is False
        assert settings.db_pool_size == 20
        assert settings.worker_max_attempts == 3
        assert settings.accepted_claim_confidence == 0.70
        assert settings.review_claim_confidence_floor == 0.45

    def test_env_override_string(self, monkeypatch):
        monkeypatch.setenv("PLANAGENT_ENV", "staging")
        s = Settings(_env_file=None)
        assert s.env == "staging"

    def test_env_override_int(self, monkeypatch):
        monkeypatch.setenv("PLANAGENT_DB_POOL_SIZE", "5")
        s = Settings(_env_file=None)
        assert s.db_pool_size == 5

    def test_env_override_float(self, monkeypatch):
        monkeypatch.setenv("PLANAGENT_ACCEPTED_CLAIM_CONFIDENCE", "0.85")
        s = Settings(_env_file=None)
        assert s.accepted_claim_confidence == pytest.approx(0.85)

    def test_env_override_bool(self, monkeypatch):
        monkeypatch.setenv("PLANAGENT_SQL_ECHO", "true")
        s = Settings(_env_file=None)
        assert s.sql_echo is True

    def test_extra_env_vars_ignored(self, monkeypatch):
        monkeypatch.setenv("PLANAGENT_NONEXISTENT_FIELD", "whatever")
        s = Settings(_env_file=None)
        # Should not raise
        assert s.app_name == "PlanAgent"

    def test_no_dotenv_loaded(self, settings):
        """_env_file=None means no .env is read — settings should have pure defaults."""
        assert settings.database_url.startswith("postgresql+psycopg://")

    def test_non_loopback_bind_requires_remote_access(self) -> None:
        with pytest.raises(ValidationError, match="remote access must be explicitly enabled"):
            Settings(_env_file=None, bind_host="0.0.0.0")

    @pytest.mark.parametrize("secret", ["", "too-short"])
    def test_remote_access_requires_strong_persistent_auth_secret(self, secret: str) -> None:
        with pytest.raises(ValidationError, match="AUTH_SECRET_KEY is required"):
            Settings(
                _env_file=None,
                bind_host="0.0.0.0",
                remote_access_enabled=True,
                auth_secret_key=secret,
            )

    def test_non_loopback_remote_access_accepts_strong_auth_secret(self) -> None:
        settings = Settings(
            _env_file=None,
            bind_host="0.0.0.0",
            remote_access_enabled=True,
            auth_secret_key="a" * 32,
            bootstrap_admin_password="b" * 24,
        )

        assert settings.bind_host == "0.0.0.0"
        assert settings.remote_access_enabled is True

    def test_remote_access_requires_bootstrap_admin_password(self) -> None:
        with pytest.raises(ValidationError, match="BOOTSTRAP_ADMIN_PASSWORD"):
            Settings(
                _env_file=None,
                remote_access_enabled=True,
                auth_secret_key="a" * 32,
            )

    def test_local_proxy_secret_requires_strong_value_when_configured(self) -> None:
        with pytest.raises(ValidationError, match="LOCAL_PROXY_SECRET must be at least 32 bytes"):
            Settings(_env_file=None, local_proxy_secret="too-short")

    @pytest.mark.parametrize("origin", ["*", "null", "https://example.com/path"])
    def test_cors_origins_require_explicit_http_origins(self, origin: str) -> None:
        with pytest.raises(ValidationError, match="CORS origin"):
            Settings(_env_file=None, cors_origins=[origin])


# ---------------------------------------------------------------------------
# Nested OpenAI config via env vars
# ---------------------------------------------------------------------------


class TestOpenAIEnvVarResolution:
    def test_shared_api_key_via_env(self, monkeypatch):
        monkeypatch.setenv("PLANAGENT_OPENAI_SHARED_API_KEY", "sk-shared-test")
        s = Settings(_env_file=None)
        assert s.openai.shared_api_key == "sk-shared-test"
        assert s.openai_api_key == "sk-shared-test"

    def test_target_specific_model_via_env(self, monkeypatch):
        monkeypatch.setenv("PLANAGENT_OPENAI_PRIMARY_MODEL", "gpt-5-test")
        s = Settings(_env_file=None)
        assert s.openai.primary.model == "gpt-5-test"
        assert s.openai_primary_model == "gpt-5-test"

    def test_extraction_target_api_key_via_env(self, monkeypatch):
        monkeypatch.setenv("PLANAGENT_OPENAI_EXTRACTION_API_KEY", "sk-extraction")
        s = Settings(_env_file=None)
        assert s.openai.extraction.api_key == "sk-extraction"


# ---------------------------------------------------------------------------
# OpenAI target model resolution (openai_model_source)
# ---------------------------------------------------------------------------


class TestOpenAIModelSource:
    def test_primary_target_returns_primary_env_var(self, settings):
        assert settings.openai_model_source("primary") == "unset"

    def test_extraction_with_own_model(self, monkeypatch):
        monkeypatch.setenv("PLANAGENT_OPENAI_EXTRACTION_MODEL", "provider-model-alpha")
        s = Settings(_env_file=None)
        assert s.openai_model_source("extraction") == "PLANAGENT_OPENAI_EXTRACTION_MODEL"

    def test_extraction_falls_back_to_primary(self, settings):
        assert settings.openai_model_source("extraction") == "unset"

    def test_report_with_own_model(self, monkeypatch):
        monkeypatch.setenv("PLANAGENT_OPENAI_REPORT_MODEL", "provider-model-beta")
        s = Settings(_env_file=None)
        assert s.openai_model_source("report") == "PLANAGENT_OPENAI_REPORT_MODEL"

    def test_report_falls_back_to_primary(self, settings):
        assert settings.openai_model_source("report") == "unset"

    def test_debate_advocate_with_own_model(self, monkeypatch):
        monkeypatch.setenv("PLANAGENT_OPENAI_DEBATE_ADVOCATE_MODEL", "provider-model-gamma")
        s = Settings(_env_file=None)
        assert s.openai_model_source("debate_advocate") == "PLANAGENT_OPENAI_DEBATE_ADVOCATE_MODEL"

    def test_debate_advocate_falls_back_to_primary(self, settings):
        assert settings.openai_model_source("debate_advocate") == "unset"

    def test_debate_challenger_with_own_model(self, monkeypatch):
        monkeypatch.setenv("PLANAGENT_OPENAI_DEBATE_CHALLENGER_MODEL", "claude-3")
        s = Settings(_env_file=None)
        assert (
            s.openai_model_source("debate_challenger") == "PLANAGENT_OPENAI_DEBATE_CHALLENGER_MODEL"
        )

    def test_debate_challenger_falls_back_to_extraction_then_primary(self, settings):
        # No extraction model → falls to primary
        assert settings.openai_model_source("debate_challenger") == "unset"

    def test_debate_challenger_prefers_extraction_over_primary(self, monkeypatch):
        monkeypatch.setenv("PLANAGENT_OPENAI_EXTRACTION_MODEL", "provider-model-alpha")
        s = Settings(_env_file=None)
        assert s.openai_model_source("debate_challenger") == "PLANAGENT_OPENAI_EXTRACTION_MODEL"

    def test_debate_arbitrator_falls_back_to_report_then_primary(self, settings):
        # No report model → falls to primary
        assert settings.openai_model_source("debate_arbitrator") == "unset"

    def test_debate_arbitrator_prefers_report_over_primary(self, monkeypatch):
        monkeypatch.setenv("PLANAGENT_OPENAI_REPORT_MODEL", "provider-model-beta")
        s = Settings(_env_file=None)
        assert s.openai_model_source("debate_arbitrator") == "PLANAGENT_OPENAI_REPORT_MODEL"

    def test_unsupported_target_raises(self, settings):
        with pytest.raises((ValueError, KeyError)):
            settings.openai_model_source("nonexistent")


# ---------------------------------------------------------------------------
# Resolved OpenAI model / key / base_url chain
# ---------------------------------------------------------------------------


class TestResolvedOpenAIFields:
    def test_primary_model_default(self, settings):
        assert settings.openai_primary_model is None
        assert settings.resolved_openai_extraction_model == ""

    def test_extraction_model_overrides_primary(self, monkeypatch):
        monkeypatch.setenv("PLANAGENT_OPENAI_EXTRACTION_MODEL", "custom-extraction")
        s = Settings(_env_file=None)
        assert s.resolved_openai_extraction_model == "custom-extraction"

    def test_report_model_defaults_to_primary(self, settings):
        assert settings.openai_primary_model is None
        assert settings.resolved_openai_report_model == ""

    def test_shared_api_key_propagates_to_targets(self, settings_with_openai_key):
        s = settings_with_openai_key
        assert s.resolved_openai_primary_api_key == "sk-test-fake-key-12345"
        assert s.resolved_openai_extraction_api_key == "sk-test-fake-key-12345"
        assert s.resolved_openai_report_api_key == "sk-test-fake-key-12345"

    def test_target_key_overrides_shared(self, monkeypatch):
        monkeypatch.setenv("PLANAGENT_OPENAI_SHARED_API_KEY", "sk-shared")
        monkeypatch.setenv("PLANAGENT_OPENAI_PRIMARY_API_KEY", "sk-primary")
        s = Settings(_env_file=None)
        assert s.resolved_openai_primary_api_key == "sk-primary"

    def test_extraction_key_inherits_from_primary(self, monkeypatch):
        monkeypatch.setenv("PLANAGENT_OPENAI_SHARED_API_KEY", "sk-shared")
        s = Settings(_env_file=None)
        # No extraction-specific key → should fall through to primary → shared
        assert s.resolved_openai_extraction_api_key == "sk-shared"


# ---------------------------------------------------------------------------
# configured_openai_targets / openai_enabled
# ---------------------------------------------------------------------------


class TestOpenAIEnabled:
    def test_no_keys_disabled(self, settings):
        assert settings.openai_enabled is False
        assert settings.configured_openai_targets == []

    def test_shared_key_enables_all_targets(self, settings_with_openai_key):
        s = settings_with_openai_key
        assert s.openai_enabled is True
        assert "primary" in s.configured_openai_targets
        assert "extraction" in s.configured_openai_targets


# ---------------------------------------------------------------------------
# Nested model defaults
# ---------------------------------------------------------------------------


class TestNestedModelDefaults:
    def test_openai_config_defaults(self):
        cfg = OpenAIConfig()
        assert cfg.shared_api_key is None
        assert cfg.timeout_seconds == 45.0
        assert isinstance(cfg.primary, OpenAITargetConfig)
        assert cfg.primary.model is None

    def test_target_config_defaults(self):
        t = OpenAITargetConfig()
        assert t.model is None
        assert t.api_key is None
        assert t.base_url is None

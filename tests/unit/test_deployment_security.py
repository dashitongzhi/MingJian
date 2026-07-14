from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_compose_publishes_local_stack_only_on_loopback() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())

    published_ports = [
        str(port) for service in compose["services"].values() for port in service.get("ports", [])
    ]

    assert published_ports
    assert all(port.startswith("127.0.0.1:") for port in published_ports)


def test_compose_keeps_local_session_mode_behind_loopback_ports() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    api = compose["services"]["api"]
    api_environment = api["environment"]

    assert "--host 0.0.0.0" in api["command"]
    assert api["ports"] == ["127.0.0.1:8000:8000"]
    assert api_environment.get("PLANAGENT_REMOTE_ACCESS_ENABLED") != "true"


def test_compose_frontend_proxy_uses_server_only_local_credential() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    frontend_environment = compose["services"]["frontend"]["environment"]
    vite_config = (ROOT / "frontend-v2" / "vite.config.ts").read_text()

    assert frontend_environment["MINGJIAN_LOCAL_PROXY_SECRET"] == (
        "${PLANAGENT_LOCAL_PROXY_SECRET:?Set PLANAGENT_LOCAL_PROXY_SECRET or run ./setup.sh}"
    )
    assert "X-MingJian-Local-Proxy" in vite_config
    assert "process.env.MINGJIAN_LOCAL_PROXY_SECRET" in vite_config
    assert "VITE_LOCAL_PROXY_SECRET" not in vite_config


def test_example_environment_defaults_to_loopback_local_mode() -> None:
    example = (ROOT / ".env.example").read_text()

    assert "PLANAGENT_BIND_HOST=127.0.0.1" in example
    assert "PLANAGENT_REMOTE_ACCESS_ENABLED=false" in example
    assert "PLANAGENT_AUTH_SECRET_KEY=" in example
    assert "PLANAGENT_LOCAL_PROXY_SECRET=" in example
    assert "PLANAGENT_BOOTSTRAP_ADMIN_PASSWORD=" in example


def test_readme_development_commands_preserve_loopback_access_boundary() -> None:
    for readme_name in ("README.md", "README.zh-CN.md", "README.ja.md", "README.hi.md"):
        readme = (ROOT / readme_name).read_text()
        assert "uvicorn planagent.main:app --reload --host 127.0.0.1 --port 8000" in readme
        assert "uvicorn planagent.main:app --reload --host 0.0.0.0 --port 8000" not in readme
        assert "PLANAGENT_REMOTE_ACCESS_ENABLED=true" in readme
        assert "PLANAGENT_AUTH_SECRET_KEY" in readme
        assert "PLANAGENT_BOOTSTRAP_ADMIN_PASSWORD" in readme
        assert "/auth/change-password" in readme


def test_setup_generates_persistent_auth_secret_before_compose_start() -> None:
    setup = (ROOT / "setup.sh").read_text()

    secret_write = setup.index('update_env_value "PLANAGENT_AUTH_SECRET_KEY"')
    admin_password_write = setup.index('update_env_value "PLANAGENT_BOOTSTRAP_ADMIN_PASSWORD"')
    proxy_secret_write = setup.index('update_env_value "PLANAGENT_LOCAL_PROXY_SECRET"')
    compose_start = setup.index("docker compose up -d")

    assert secret_write < compose_start
    assert admin_password_write < compose_start
    assert proxy_secret_write < compose_start

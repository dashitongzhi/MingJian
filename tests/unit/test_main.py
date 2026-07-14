from __future__ import annotations

from types import SimpleNamespace

import pytest

from planagent import main


def test_run_uses_configured_loopback_bind_host(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(bind_host="127.0.0.1"))

    def fake_run(app: str, **kwargs: object) -> None:
        captured["app"] = app
        captured.update(kwargs)

    monkeypatch.setattr(main.uvicorn, "run", fake_run)

    main.run()

    assert captured == {
        "app": "planagent.main:app",
        "host": "127.0.0.1",
        "port": 8000,
        "reload": False,
    }

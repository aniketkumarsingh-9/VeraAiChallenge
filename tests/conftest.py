from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_app


@pytest.fixture()
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    db_path = tmp_path / "vera-test.db"
    custom = Settings(database_url=f"sqlite:///{db_path.as_posix()}", team_name="Test Team", team_members="Alice,Bob")
    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", custom.database_url)
    monkeypatch.setenv("TEAM_NAME", custom.team_name)
    monkeypatch.setenv("TEAM_MEMBERS", custom.team_members)
    monkeypatch.setenv("TEAM_MODEL", custom.team_model)
    monkeypatch.setenv("APP_NAME", custom.app_name)
    monkeypatch.setenv("APP_ENV", custom.app_env)
    monkeypatch.setenv("LOG_LEVEL", custom.log_level)
    monkeypatch.setenv("SUPPRESSION_DAYS", str(custom.suppression_days))
    monkeypatch.setenv("MAX_ACTIONS_PER_TICK", str(custom.max_actions_per_tick))
    return custom


@pytest.fixture()
def client(settings: Settings) -> TestClient:
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client

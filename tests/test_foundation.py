import pytest
from fastapi.testclient import TestClient

from delta_contracts.config import Settings
from delta_core.main import create_app as core_app
from delta_tasks.main import create_app as tasks_app
from delta_core.db import Base


@pytest.mark.parametrize("factory", [core_app, tasks_app])
def test_health_checks_database_and_version(factory, tmp_path):
    app = factory(Settings(delta_token="test-token-only-123456", database_url=f"sqlite:///{tmp_path}/test.db"))
    if factory is core_app:
        Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.headers["x-request-id"]
        assert client.get("/api/v1/private").status_code == 401


def test_health_reports_database_failure(tmp_path):
    app = core_app(Settings(delta_token="test-token-only-123456",
                            database_url=f"sqlite:///{tmp_path}/missing/db.sqlite"))
    client = TestClient(app)
    assert client.get("/health").status_code == 503

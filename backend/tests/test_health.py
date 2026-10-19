from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health_returns_liveness_without_external_services():
    app = create_app(Settings(_env_file=None, environment="test"))
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["content-type"] == "application/json"

"""Integration tests for FastAPI endpoints."""
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_today_signals_endpoint():
    with TestClient(app) as c:
        resp = c.get("/signals/today")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


def test_screener_lookback_validation():
    with TestClient(app) as c:
        resp = c.get("/screener/lookback?lookback_days=100")
        assert resp.status_code == 422  # validation error for > 60 days

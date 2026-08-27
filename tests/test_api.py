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


def test_screener_lookback_success():
    with TestClient(app) as c:
        resp = c.get("/screener/lookback?lookback_days=1")
        assert resp.status_code == 200
        data = resp.json()
        assert "lookback_days" in data
        assert "items" in data
        assert "total_scanned" in data


def test_watchlist_list_endpoint():
    with TestClient(app) as c:
        resp = c.get("/watchlist/list")
        assert resp.status_code == 200
        assert isinstance(resp.json(), dict)


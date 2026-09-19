"""Unit and integration tests for Multi-User Authentication and Portfolio/Watchlist Isolation."""
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_auth_registration_and_login():
    # 1. Register Alice
    res_reg = client.post("/auth/register", json={
        "username": "alice_test",
        "password": "password123",
        "display_name": "Alice Trader"
    })
    assert res_reg.status_code == 200, res_reg.text
    data_reg = res_reg.json()
    assert data_reg["success"] is True
    assert "token" in data_reg
    assert data_reg["user"]["username"] == "alice_test"
    alice_token = data_reg["token"]

    # 2. Duplicate registration fails
    res_dup = client.post("/auth/register", json={
        "username": "alice_test",
        "password": "anotherpassword",
        "display_name": "Duplicate Alice"
    })
    assert res_dup.status_code == 400
    assert "already exists" in res_dup.json()["detail"].lower() or "already taken" in res_dup.json()["detail"].lower()


    # 3. Login wrong password fails
    res_bad_pw = client.post("/auth/login", json={
        "username": "alice_test",
        "password": "wrongpassword"
    })
    assert res_bad_pw.status_code == 401

    # 4. Login correct password succeeds
    res_login = client.post("/auth/login", json={
        "username": "alice_test",
        "password": "password123"
    })
    assert res_login.status_code == 200
    login_data = res_login.json()
    assert login_data["success"] is True
    assert login_data["user"]["username"] == "alice_test"

    # 5. /auth/me returns current user profile
    headers = {"Authorization": f"Bearer {alice_token}"}
    res_me = client.get("/auth/me", headers=headers)
    assert res_me.status_code == 200
    assert res_me.json()["user"]["username"] == "alice_test"

    # 6. Logout invalidates token
    res_logout = client.post("/auth/logout", headers=headers)
    assert res_logout.status_code == 200

    # Following request with invalidated token returns 401 Unauthorized
    res_me_after = client.get("/auth/me", headers=headers)
    assert res_me_after.status_code == 401

    # Request with no auth header falls back to default guest user
    res_default = client.get("/auth/me")
    assert res_default.status_code == 200
    assert res_default.json()["user"]["username"] in ("guest", "trader", "jay")




def test_paper_trading_user_isolation():
    # Register two distinct users
    res_a = client.post("/auth/register", json={
        "username": "trader_user_a",
        "password": "passA123",
        "display_name": "Trader User A"
    })
    assert res_a.status_code == 200
    token_a = res_a.json()["token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    res_b = client.post("/auth/register", json={
        "username": "trader_user_b",
        "password": "passB123",
        "display_name": "Trader User B"
    })
    assert res_b.status_code == 200
    token_b = res_b.json()["token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Reset portfolios with different capital
    client.post("/paper/reset", json={"capital": 500000.0}, headers=headers_a)
    client.post("/paper/reset", json={"capital": 1200000.0}, headers=headers_b)

    # Check initial summaries
    sum_a = client.get("/paper/summary", headers=headers_a).json()
    sum_b = client.get("/paper/summary", headers=headers_b).json()
    assert sum_a["cash_balance"] == 500000.0
    assert sum_b["cash_balance"] == 1200000.0
    assert sum_a["open_positions_count"] == 0
    assert sum_b["open_positions_count"] == 0

    # User A places an order for RELIANCE
    order_a = client.post("/paper/order", json={
        "symbol": "RELIANCE",
        "side": "BUY",
        "quantity": 10,
        "entry_price": 2500.0,
        "target_price": 2650.0,
        "stop_loss_price": 2420.0,
        "strategy": "Mean Reversion",
        "notes": "User A trade"
    }, headers=headers_a).json()
    assert order_a["success"] is True
    pos_id_a = order_a["position_id"]

    # Verify User A has 1 position, User B has 0 positions
    pos_a = client.get("/paper/positions", headers=headers_a).json()
    pos_b = client.get("/paper/positions", headers=headers_b).json()
    assert len(pos_a) == 1
    assert pos_a[0]["symbol"] == "RELIANCE"
    assert len(pos_b) == 0

    # Verify User A cash balance reduced, User B cash balance untouched
    sum_a = client.get("/paper/summary", headers=headers_a).json()
    sum_b = client.get("/paper/summary", headers=headers_b).json()
    assert sum_a["cash_balance"] == 500000.0 - (10 * 2500.0)
    assert sum_b["cash_balance"] == 1200000.0

    # User B places an order for INFY
    order_b = client.post("/paper/order", json={
        "symbol": "INFY",
        "side": "BUY",
        "quantity": 25,
        "entry_price": 1600.0,
        "target_price": 1700.0,
        "stop_loss_price": 1550.0,
        "strategy": "Knoxville",
        "notes": "User B trade"
    }, headers=headers_b).json()
    assert order_b["success"] is True

    # Check both have their own positions and ONLY their own
    pos_a = client.get("/paper/positions", headers=headers_a).json()
    pos_b = client.get("/paper/positions", headers=headers_b).json()
    assert len(pos_a) == 1
    assert pos_a[0]["symbol"] == "RELIANCE"
    assert len(pos_b) == 1
    assert pos_b[0]["symbol"] == "INFY"

    # User A closes position
    close_res = client.post("/paper/close", json={
        "position_id": pos_id_a,
        "exit_price": 2600.0,
        "exit_reason": "Target reached"
    }, headers=headers_a).json()
    assert close_res["success"] is True
    assert close_res["pnl_amount"] == 1000.0

    # User A has 0 open, 1 closed trade. User B still has 1 open, 0 closed trades.
    pos_a = client.get("/paper/positions", headers=headers_a).json()
    pos_b = client.get("/paper/positions", headers=headers_b).json()
    assert len(pos_a) == 0
    assert len(pos_b) == 1

    hist_a = client.get("/paper/history", headers=headers_a).json()
    hist_b = client.get("/paper/history", headers=headers_b).json()
    assert len(hist_a) == 1
    assert hist_a[0]["symbol"] == "RELIANCE"
    assert len(hist_b) == 0


def test_custom_watchlist_user_isolation():
    # Register two users for watchlist isolation
    res_wl_a = client.post("/auth/register", json={
        "username": "wl_user_a",
        "password": "passWL123",
        "display_name": "Watchlist User A"
    })
    token_a = res_wl_a.json()["token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    res_wl_b = client.post("/auth/register", json={
        "username": "wl_user_b",
        "password": "passWL123",
        "display_name": "Watchlist User B"
    })
    token_b = res_wl_b.json()["token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User A creates a watchlist
    res_save_a = client.post("/watchlist/custom", json={
        "name": "UserA_Picks",
        "symbols": ["TCS", "INFY"]
    }, headers=headers_a)
    assert res_save_a.status_code == 200

    # User B creates a watchlist
    res_save_b = client.post("/watchlist/custom", json={
        "name": "UserB_Picks",
        "symbols": ["HDFCBANK", "ICICIBANK"]
    }, headers=headers_b)
    assert res_save_b.status_code == 200

    # User A lists watchlists -> should only see UserA_Picks, not UserB_Picks
    lists_a = client.get("/watchlist/list", headers=headers_a).json()
    assert "UserA_Picks" in lists_a
    assert "UserB_Picks" not in lists_a

    # User B lists watchlists -> should only see UserB_Picks, not UserA_Picks
    lists_b = client.get("/watchlist/list", headers=headers_b).json()
    assert "UserB_Picks" in lists_b
    assert "UserA_Picks" not in lists_b

    # Verify /universe/symbols isolates custom watchlist memberships per user
    symbols_a = client.get("/universe/symbols", headers=headers_a).json()
    all_memberships_a = {item["symbol"]: item["membership"] for item in symbols_a}
    assert "UserB_Picks" not in [m for mems in all_memberships_a.values() for m in mems]
    assert "UserA_Picks" in all_memberships_a.get("TCS", [])

    symbols_b = client.get("/universe/symbols", headers=headers_b).json()
    all_memberships_b = {item["symbol"]: item["membership"] for item in symbols_b}
    assert "UserA_Picks" not in [m for mems in all_memberships_b.values() for m in mems]
    assert "UserB_Picks" in all_memberships_b.get("HDFCBANK", [])

    # User A deletes UserA_Picks
    del_res = client.delete("/watchlist/custom/UserA_Picks", headers=headers_a)
    assert del_res.status_code == 200

    # User A custom lists empty, User B still has UserB_Picks
    lists_a = client.get("/watchlist/list", headers=headers_a).json()
    lists_b = client.get("/watchlist/list", headers=headers_b).json()
    assert "UserA_Picks" not in lists_a
    assert "UserB_Picks" in lists_b


def test_login_portal_routes():
    # 1. /login serves login.html with no-cache headers
    res_login = client.get("/login")
    assert res_login.status_code == 200
    assert "no-cache" in res_login.headers.get("Cache-Control", "")
    assert "STRATLAB" in res_login.text
    assert "Sign In" in res_login.text
    assert "form-signin" in res_login.text
    assert "form-register" in res_login.text

    # 2. /login.html alias works
    res_login_html = client.get("/login.html")
    assert res_login_html.status_code == 200
    assert "STRATLAB" in res_login_html.text

    # 3. / (dashboard) has the early auth gate script
    res_root = client.get("/")
    assert res_root.status_code == 200
    assert "stratlab_auth_token" in res_root.text
    assert "window.location.replace('/login')" in res_root.text



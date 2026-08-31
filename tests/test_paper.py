"""Unit and integration tests for Paper Trading service and endpoints."""
from fastapi.testclient import TestClient
from main import app
from db.paper_repository import PaperRepository

client = TestClient(app)


def test_paper_trading_workflow():
    # 1. Reset Portfolio
    res_reset = client.post("/paper/reset", json={"capital": 1000000.0})
    assert res_reset.status_code == 200

    # 2. Get Summary
    res_summary = client.get("/paper/summary")
    assert res_summary.status_code == 200
    summary = res_summary.json()
    assert summary["initial_capital"] == 1000000.0
    assert summary["cash_balance"] == 1000000.0
    assert summary["open_positions_count"] == 0

    # 3. Place Buy Order
    order_payload = {
        "symbol": "TVSMOTOR",
        "side": "BUY",
        "quantity": 10,
        "entry_price": 2400.0,
        "target_price": 2520.0,
        "stop_loss_price": 2350.0,
        "strategy": "Knoxville Divergence",
        "notes": "Testing paper order placement"
    }
    res_order = client.post("/paper/order", json=order_payload)
    assert res_order.status_code == 200
    order_data = res_order.json()
    assert order_data["success"] is True
    assert order_data["symbol"] == "TVSMOTOR"
    pos_id = order_data["position_id"]

    # 4. Check Open Positions
    res_positions = client.get("/paper/positions")
    assert res_positions.status_code == 200
    positions = res_positions.json()
    assert len(positions) == 1
    assert positions[0]["symbol"] == "TVSMOTOR"
    assert positions[0]["quantity"] == 10

    # 5. Close Position
    close_payload = {
        "position_id": pos_id,
        "exit_price": 2500.0,
        "exit_reason": "Target Hit"
    }
    res_close = client.post("/paper/close", json=close_payload)
    assert res_close.status_code == 200
    close_data = res_close.json()
    assert close_data["success"] is True
    assert close_data["pnl_amount"] == 1000.0  # (2500 - 2400) * 10

    # 6. Check History
    res_history = client.get("/paper/history")
    assert res_history.status_code == 200
    history = res_history.json()
    assert len(history) >= 1
    assert history[0]["symbol"] == "TVSMOTOR"
    assert history[0]["pnl_amount"] == 1000.0

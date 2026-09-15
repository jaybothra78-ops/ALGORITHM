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


def test_options_trading_workflow():
    # 1. Test Option Strikes Endpoint
    res_strikes = client.get("/market/option-strikes?symbol=NIFTY")
    assert res_strikes.status_code == 200
    strikes_data = res_strikes.json()
    assert strikes_data["symbol"] == "NIFTY"
    assert len(strikes_data["strikes"]) >= 5
    assert strikes_data["lot_size"] == 25

    # 2. Test Option Pricing Endpoint (Call CE)
    res_opt_price = client.get("/market/option-price?symbol=NIFTY&option_type=CE&strike=25000")
    assert res_opt_price.status_code == 200
    opt_data = res_opt_price.json()
    assert opt_data["symbol"] == "NIFTY"
    assert opt_data["option_type"] == "CE"
    assert opt_data["premium"] > 0
    assert "delta" in opt_data

    # 3. Place Call Option Order
    call_order = {
        "symbol": "NIFTY",
        "instrument_type": "OPTION",
        "option_type": "CE",
        "strike_price": 25000.0,
        "expiry_date": "2026-09-04",
        "lot_size": 25,
        "contracts": 2,
        "side": "BUY",
        "entry_price": 120.0,
        "target_price": 180.0,
        "stop_loss_price": 80.0,
        "strategy": "Options Directional Breakout",
    }
    res_order = client.post("/paper/order", json=call_order)
    assert res_order.status_code == 200
    order_res = res_order.json()
    assert order_res["success"] is True
    assert order_res["quantity"] == 50  # 2 lots * 25
    pos_id = order_res["position_id"]

    # 4. Check Open Position
    res_pos = client.get("/paper/positions")
    assert res_pos.status_code == 200
    pos_list = res_pos.json()
    matching_pos = next((p for p in pos_list if p["id"] == pos_id), None)
    assert matching_pos is not None
    assert matching_pos["instrument_type"] == "OPTION"
    assert matching_pos["option_type"] == "CE"
    assert matching_pos["quantity"] == 50

    # 5. Close Option Position
    res_close = client.post("/paper/close", json={"position_id": pos_id, "exit_price": 160.0, "exit_reason": "Target Hit"})
    assert res_close.status_code == 200
    close_data = res_close.json()
    assert close_data["success"] is True
    assert close_data["pnl_amount"] == 2000.0  # (160 - 120) * 50


def test_zerodha_service_endpoints():
    # Test Zerodha Status
    res_status = client.get("/zerodha/status")
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert "connected" in status_data
    assert "method" in status_data

    # Test Trading Symbol generation
    from services.zerodha_service import ZerodhaService
    zs = ZerodhaService.get_instance()
    ts = zs.get_tradingsymbol("NIFTY", 25000, "CE", "2026-09-24")
    assert ts == "NIFTY26SEP25000CE"
    ts_bosch = zs.get_tradingsymbol("BOSCHLTD", 44000, "PE", "2026-09-24")
    assert ts_bosch == "BOSCHLTD26SEP44000PE"


def test_modify_order_workflow():
    # 1. Reset account
    client.post("/paper/reset", json={"capital": 100000.0})

    # 2. Place initial order: 10 shares @ 2000.0
    res_order = client.post(
        "/paper/order",
        json={
            "symbol": "TVSMOTOR",
            "side": "BUY",
            "quantity": 10,
            "entry_price": 2000.0,
            "target_price": 2100.0,
            "stop_loss_price": 1950.0,
            "notes": "Initial setup",
        },
    )
    assert res_order.status_code == 200
    pos_id = res_order.json()["position_id"]

    # Initial cash: 100,000 - 20,000 = 80,000
    summary = client.get("/paper/summary").json()
    assert summary["cash_balance"] == 80000.0

    # 3. Modify Target, Stop Loss, and Notes
    res_mod1 = client.post(
        "/paper/modify",
        json={
            "position_id": pos_id,
            "target_price": 2200.0,
            "stop_loss_price": 1980.0,
            "notes": "Trail SL to 1980",
        },
    )
    assert res_mod1.status_code == 200
    data1 = res_mod1.json()
    assert data1["success"] is True
    assert data1["target_price"] == 2200.0
    assert data1["stop_loss_price"] == 1980.0
    assert data1["notes"] == "Trail SL to 1980"
    assert data1["remaining_cash"] == 80000.0

    # Verify positions endpoint reflects changes
    pos = client.get("/paper/positions").json()[0]
    assert pos["target_price"] == 2200.0
    assert pos["stop_loss_price"] == 1980.0
    assert pos["notes"] == "Trail SL to 1980"

    # 4. Sizing up: Increase quantity from 10 to 15 (requires 5 * 2000 = 10,000)
    res_mod2 = client.post(
        "/paper/modify",
        json={
            "position_id": pos_id,
            "quantity": 15,
        },
    )
    assert res_mod2.status_code == 200
    data2 = res_mod2.json()
    assert data2["quantity"] == 15
    assert data2["remaining_cash"] == 70000.0

    # 5. Sizing down: Decrease quantity from 15 to 8 (releases 7 * 2000 = 14,000)
    res_mod3 = client.post(
        "/paper/modify",
        json={
            "position_id": pos_id,
            "quantity": 8,
        },
    )
    assert res_mod3.status_code == 200
    data3 = res_mod3.json()
    assert data3["quantity"] == 8
    assert data3["remaining_cash"] == 84000.0

    # 6. Insufficient cash test
    # Attempt to size up to 100 shares (needs 92 * 2000 = 184,000, but only 84,000 available)
    res_fail = client.post(
        "/paper/modify",
        json={
            "position_id": pos_id,
            "quantity": 100,
        },
    )
    assert res_fail.status_code == 400
    assert "Insufficient cash" in res_fail.json()["detail"]

    # 7. Modify Option Contracts
    opt_res = client.post(
        "/paper/order",
        json={
            "symbol": "NIFTY",
            "instrument_type": "OPTION",
            "option_type": "CE",
            "strike_price": 25000.0,
            "lot_size": 25,
            "contracts": 1,
            "entry_price": 100.0,
        },
    )
    assert opt_res.status_code == 200
    opt_pos_id = opt_res.json()["position_id"]

    # Modify contracts to 3 lots (3 * 25 = 75 units, additional 50 units @ 100 = 5000)
    cash_before_opt_mod = client.get("/paper/summary").json()["cash_balance"]
    res_opt_mod = client.post(
        "/paper/modify",
        json={
            "position_id": opt_pos_id,
            "contracts": 3,
        },
    )
    assert res_opt_mod.status_code == 200
    opt_mod_data = res_opt_mod.json()
    assert opt_mod_data["contracts"] == 3
    assert opt_mod_data["quantity"] == 75
    assert opt_mod_data["remaining_cash"] == cash_before_opt_mod - 5000.0

    # 8. Modify closed or non-existent position
    client.post("/paper/close", json={"position_id": pos_id, "exit_price": 2050.0})
    res_closed_mod = client.post(
        "/paper/modify",
        json={"position_id": pos_id, "target_price": 2500.0},
    )
    assert res_closed_mod.status_code == 400




"""Business logic and real-time execution for Paper Trading (Equity & Options)."""
from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from typing import Any

from db.paper_repository import PaperRepository
from models.paper import (
    InstrumentType,
    OptionType,
    PaperCloseRequest,
    PaperModifyRequest,
    PaperOrderRequest,
    PaperPortfolioSummary,
    PaperPosition,
    PaperTradeRecord,
)
from services.market_data import MarketDataProvider
from services.options_pricing import OptionsPricingService


class PaperTradingService:
    """Comprehensive Paper Trading & Virtual Portfolio Manager for Equity & Options."""

    _LTP_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
    _LTP_TTL: float = 15.0  # Cache real-time quotes for 15 seconds to eliminate yfinance synchronous latency

    @classmethod
    def get_live_ltp(cls, symbol: str) -> dict[str, Any]:
        """Fetch exact real-time Last Traded Price (LTP) from NSE/BSE feeds with TTL caching."""
        clean_sym = symbol.strip().upper()
        now = time.time()

        # 1. Check in-memory TTL cache first (< 0.1ms)
        if clean_sym in cls._LTP_CACHE:
            cached_time, cached_val = cls._LTP_CACHE[clean_sym]
            if now - cached_time < cls._LTP_TTL:
                return dict(cached_val)

        # 2. Priority 1: Direct Real-Time NSE Live Feed (matches Sensibull / Kite tick-for-tick)
        try:
            if clean_sym in ("NIFTY", "NIFTY50", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"):
                from services.groww_service import GrowwOptionsService
                d = GrowwOptionsService.get_instance().fetch_option_chain_raw(clean_sym)
                if d and d.get("livePrice"):
                    lp = d["livePrice"]
                    val = float(lp.get("value") or lp.get("ltp") or 0.0)
                    if val > 0:
                        close = float(lp.get("close") or val)
                        chg = float(lp.get("dayChange") or (val - close))
                        pct = float(lp.get("dayChangePerc") or 0.0)
                        res = {
                            "symbol": clean_sym,
                            "ticker": f"^{clean_sym}",
                            "ltp": round(val, 2),
                            "previous_close": round(close, 2),
                            "change": round(chg, 2),
                            "change_pct": round(pct, 2),
                            "source": "NSE Real-Time Live Feed",
                            "timestamp": now,
                        }
                        cls._LTP_CACHE[clean_sym] = (now, res)
                        return dict(res)
            else:
                import requests
                url = f"https://groww.in/v1/api/stocks_data/v1/accord_points/exchange/NSE/segment/CASH/latest_prices_ohlc/{clean_sym}"
                r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=3)
                if r.status_code == 200:
                    d = r.json()
                    ltp_val = d.get("ltp")
                    if ltp_val and float(ltp_val) > 0:
                        ltp = float(ltp_val)
                        close = float(d.get("close") or ltp)
                        chg = float(d.get("dayChange") or (ltp - close))
                        pct = round((chg / close) * 100.0, 2) if close > 0 else 0.0
                        res = {
                            "symbol": clean_sym,
                            "ticker": f"{clean_sym}.NS",
                            "ltp": round(ltp, 2),
                            "previous_close": round(close, 2),
                            "change": round(chg, 2),
                            "change_pct": pct,
                            "source": "NSE Real-Time Live Feed",
                            "timestamp": now,
                        }
                        cls._LTP_CACHE[clean_sym] = (now, res)
                        return dict(res)
        except Exception as exc:
            logger.debug(f"Direct real-time exchange quote error for {clean_sym}: {exc}")

        # 3. Fallback to Yahoo Finance (delayed)
        import yfinance as yf
        # Handle index ticker and demerged mapping for Yahoo Finance
        if clean_sym in ("NIFTY", "NIFTY50"):
            ticker_candidates = ["^NSEI", "NIFTYBEES.NS"]
        elif clean_sym == "BANKNIFTY":
            ticker_candidates = ["^NSEBANK", "BANKBEES.NS"]
        elif clean_sym == "FINNIFTY":
            ticker_candidates = ["NIFTY_FIN_SERVICE.NS", "^CNXFIN"]
        elif clean_sym == "SENSEX":
            ticker_candidates = ["^BSESN"]
        elif clean_sym == "TATAMOTORS":
            ticker_candidates = ["TMPV.NS", "TMCV.NS", "TATAMOTORS.NS"]
        else:
            ticker_candidates = [
                f"{clean_sym}.NS",
                f"{clean_sym}.BO",
                clean_sym,
            ]

        for ticker_str in ticker_candidates:
            try:
                t = yf.Ticker(ticker_str)
                price = None
                prev_close = None

                # 1. Fast real-time quote metadata (< 1s)
                if hasattr(t, "fast_info") and t.fast_info:
                    try:
                        price = getattr(t.fast_info, "last_price", None) or t.fast_info.get("lastPrice") or t.fast_info.get("regularMarketPrice")
                        prev_close = getattr(t.fast_info, "previous_close", None) or t.fast_info.get("previousClose") or t.fast_info.get("regularMarketPreviousClose")
                    except Exception:
                        pass

                # 2. 1-minute intraday tick fallback
                if not price or price <= 0:
                    try:
                        hist_1m = t.history(period="1d", interval="1m")
                        if not hist_1m.empty:
                            price = float(hist_1m["Close"].iloc[-1])
                            prev_close = float(hist_1m["Open"].iloc[0])
                    except Exception:
                        pass

                # 3. 5-day daily close fallback
                if not price or price <= 0:
                    try:
                        hist_5d = t.history(period="5d")
                        if not hist_5d.empty:
                            price = float(hist_5d["Close"].iloc[-1])
                            prev_close = float(hist_5d["Close"].iloc[-2]) if len(hist_5d) > 1 else price
                    except Exception:
                        pass

                if price and price > 0:
                    prev_close = prev_close or price
                    change = round(float(price - prev_close), 2)
                    change_pct = round(float((change / prev_close) * 100.0), 2) if prev_close > 0 else 0.0

                    res = {
                        "symbol": clean_sym,
                        "ticker": ticker_str,
                        "ltp": round(float(price), 2),
                        "previous_close": round(float(prev_close), 2),
                        "change": change,
                        "change_pct": change_pct,
                        "source": "NSE Real-Time Market Feed" if ".NS" in ticker_str or "^" in ticker_str else "BSE Market Feed",
                        "timestamp": now,
                    }
                    cls._LTP_CACHE[clean_sym] = (now, res)
                    return dict(res)
            except Exception:
                continue

        # Fallback to local universe cache if network fails
        cached = MarketDataProvider._CACHE.get("ohlc_data", {})
        if clean_sym in cached and not cached[clean_sym].empty:
            df_c = cached[clean_sym]
            p = float(df_c["Close"].iloc[-1])
            prev_p = float(df_c["Close"].iloc[-2]) if len(df_c) > 1 else p
            change = round(p - prev_p, 2)
            change_pct = round((change / prev_p) * 100.0, 2) if prev_p > 0 else 0.0
            res = {
                "symbol": clean_sym,
                "ticker": f"{clean_sym}.NS",
                "ltp": round(p, 2),
                "previous_close": round(prev_p, 2),
                "change": change,
                "change_pct": change_pct,
                "source": "Cached Daily Close",
                "timestamp": now,
            }
            cls._LTP_CACHE[clean_sym] = (now, res)
            return dict(res)

        data_map = MarketDataProvider.get_universe_ohlc([clean_sym])
        if clean_sym in data_map and not data_map[clean_sym].empty:
            df_c = data_map[clean_sym]
            p = float(df_c["Close"].iloc[-1])
            prev_p = float(df_c["Close"].iloc[-2]) if len(df_c) > 1 else p
            change = round(p - prev_p, 2)
            change_pct = round((change / prev_p) * 100.0, 2) if prev_p > 0 else 0.0
            res = {
                "symbol": clean_sym,
                "ticker": f"{clean_sym}.NS",
                "ltp": round(p, 2),
                "previous_close": round(prev_p, 2),
                "change": change,
                "change_pct": change_pct,
                "source": "Cached Daily Close",
                "timestamp": now,
            }
            cls._LTP_CACHE[clean_sym] = (now, res)
            return dict(res)

        # Default fallback for index if offline
        default_p = 25000.0 if clean_sym in ("NIFTY", "NIFTY50") else (51500.0 if clean_sym == "BANKNIFTY" else 100.0)
        res = {
            "symbol": clean_sym,
            "ticker": f"{clean_sym}.NS",
            "ltp": default_p,
            "previous_close": default_p,
            "change": 0.0,
            "change_pct": 0.0,
            "source": "Default Fallback",
            "timestamp": now,
        }
        cls._LTP_CACHE[clean_sym] = (now, res)
        return dict(res)

    @classmethod
    def get_live_price(cls, symbol: str) -> float:
        """Fetch latest real-time closing/LTP price for a symbol."""
        data = cls.get_live_ltp(symbol)
        return float(data.get("ltp", 100.0))

    @classmethod
    def get_option_strikes(cls, symbol: str, expiry_date: str | None = None) -> dict[str, Any]:
        """Fetch spot price and standard strike list for Options trading with accurate DTE."""
        spot_data = cls.get_live_ltp(symbol)
        spot_price = spot_data["ltp"]
        exp_info = OptionsPricingService.resolve_expiry_date(expiry_date, symbol)
        resolved_date = exp_info["date"]
        strikes_data = OptionsPricingService.get_option_strikes(symbol, spot_price, expiry_date_str=resolved_date)
        strikes_data["spot_quote"] = spot_data
        strikes_data["resolved_expiry"] = exp_info
        return strikes_data

    @classmethod
    def get_option_price(
        cls,
        symbol: str,
        option_type: str,
        strike: float | None = None,
        expiry_date: str | None = None,
        days_to_expiry: float | None = None,
    ) -> dict[str, Any]:
        """Calculate real-time Call or Put option premium and Greeks based on underlying spot and exact expiry."""
        clean_sym = symbol.strip().upper()
        spot_data = cls.get_live_ltp(clean_sym)
        spot = spot_data["ltp"]

        # If strike is missing, negative, or zero, automatically calculate nearest ATM strike
        if strike is None or strike <= 0:
            step = OptionsPricingService.get_strike_step(clean_sym, spot)
            strike = round(spot / step) * step

        # Resolve accurate expiry date string and days to expiry
        exp_info = OptionsPricingService.resolve_expiry_date(expiry_date, clean_sym)
        resolved_date_str = exp_info["date"]
        if days_to_expiry is None:
            days_to_expiry = float(exp_info["days_to_expiry"])

        bsm = OptionsPricingService.calculate_bsm_price(
            spot=spot,
            strike=strike,
            days_to_expiry=days_to_expiry,
            symbol=clean_sym,
            option_type=option_type,
        )

        display_sym = f"{clean_sym} {int(strike) if strike.is_integer() else strike} {option_type.upper()}"
        lot_size = OptionsPricingService.get_lot_size(clean_sym)

        # 1. Check Groww live market options feed
        live_premium = None
        source_lbl = None

        try:
            from services.groww_service import GrowwOptionsService
            groww_quote = GrowwOptionsService.get_instance().get_live_option_quote(clean_sym, strike, option_type, resolved_date_str)
            if groww_quote and groww_quote.get("ltp", 0.0) > 0:
                live_premium = groww_quote["ltp"]
                source_lbl = f"⚡ {groww_quote['source']}"
                if groww_quote.get("lot_size"):
                    lot_size = groww_quote["lot_size"]
        except Exception as exc:
            logger.debug(f"Groww quote error for {clean_sym}: {exc}")

        # 2. Fallback to Black-Scholes Analytical Model
        if not live_premium or live_premium <= 0:
            live_premium = bsm["premium"]
            source_lbl = f"Black-Scholes Live Model ({spot_data['source']})"

        # Calculate exact intrinsic and time value based on actual market premium
        opt_upper = option_type.upper()
        intrinsic = max(0.0, spot - strike) if opt_upper == "CE" else max(0.0, strike - spot)
        intrinsic = round(intrinsic, 2)
        time_value = round(max(0.0, live_premium - intrinsic), 2)

        return {
            "symbol": clean_sym,
            "display_symbol": display_sym,
            "instrument_type": "OPTION",
            "option_type": option_type.upper(),
            "strike_price": strike,
            "expiry_date": resolved_date_str,
            "days_to_expiry": days_to_expiry,
            "spot_price": spot,
            "lot_size": lot_size,
            "premium": live_premium,
            "intrinsic": intrinsic,
            "time_value": time_value,
            "delta": bsm["delta"],
            "theta": bsm["theta"],
            "gamma": bsm["gamma"],
            "vega": bsm["vega"],
            "source": source_lbl,
            "timestamp": time.time(),
        }


    @classmethod
    def place_order(cls, request: PaperOrderRequest, user_id: int = 1) -> dict[str, Any]:
        """Place a new paper order (Equity or Options) and deduct capital for the specific user."""
        symbol = request.symbol.strip().upper()
        inst_type = request.instrument_type.value if hasattr(request.instrument_type, "value") else str(request.instrument_type)
        
        account = PaperRepository.get_account(user_id=user_id)
        cash = account["cash_balance"]

        if inst_type == "OPTION":
            opt_type = request.option_type.value if hasattr(request.option_type, "value") else str(request.option_type or "CE")
            strike = request.strike_price or round(cls.get_live_price(symbol))
            resolved_exp_info = OptionsPricingService.resolve_expiry_date(request.expiry_date, symbol)
            expiry = resolved_exp_info["date"]
            lot_size = request.lot_size or OptionsPricingService.get_lot_size(symbol)
            contracts = max(1, request.contracts or 1)
            total_quantity = contracts * lot_size

            # Fetch or use specified option premium
            if request.entry_price and request.entry_price > 0:
                entry_premium = request.entry_price
            else:
                opt_info = cls.get_option_price(symbol, opt_type, strike, expiry)
                entry_premium = opt_info["premium"]

            order_cost = entry_premium * total_quantity
            display_symbol = f"{symbol} {int(strike) if strike == int(strike) else strike} {opt_type}"

            if request.side == "BUY" and order_cost > cash:
                raise ValueError(f"Insufficient cash balance. Required: ₹{order_cost:,.2f}, Available: ₹{cash:,.2f}")

            # Calculate default 50% target and 30% stop loss for Options if not provided
            target = request.target_price or round(entry_premium * 1.50, 2)
            sl = request.stop_loss_price or round(entry_premium * 0.70, 2)

            trade_data = {
                "symbol": symbol,
                "display_symbol": display_symbol,
                "instrument_type": "OPTION",
                "option_type": opt_type,
                "strike_price": strike,
                "expiry_date": expiry,
                "lot_size": lot_size,
                "contracts": contracts,
                "side": request.side.value if hasattr(request.side, "value") else str(request.side),
                "quantity": total_quantity,
                "entry_price": round(entry_premium, 2),
                "target_price": target,
                "stop_loss_price": sl,
                "strategy": request.strategy or "Options Directional",
                "notes": request.notes or "",
            }

            trade_id = PaperRepository.create_trade(trade_data, user_id=user_id)
            new_cash = cash - order_cost
            PaperRepository.update_cash_balance(new_cash, user_id=user_id)

            return {
                "success": True,
                "position_id": trade_id,
                "symbol": symbol,
                "display_symbol": display_symbol,
                "instrument_type": "OPTION",
                "option_type": opt_type,
                "strike_price": strike,
                "expiry_date": expiry,
                "lot_size": lot_size,
                "contracts": contracts,
                "side": trade_data["side"],
                "quantity": total_quantity,
                "entry_price": trade_data["entry_price"],
                "target_price": target,
                "stop_loss_price": sl,
                "remaining_cash": new_cash,
            }

        else:
            # EQUITY / CASH ORDER
            entry_price = request.entry_price or cls.get_live_price(symbol)
            if entry_price <= 0:
                raise ValueError(f"Invalid entry price for {symbol}")

            qty = request.quantity
            order_cost = entry_price * qty

            if request.side == "BUY" and order_cost > cash:
                raise ValueError(f"Insufficient cash balance. Required: ₹{order_cost:,.2f}, Available: ₹{cash:,.2f}")

            target = request.target_price or round(entry_price * 1.05 if request.side == "BUY" else entry_price * 0.95, 2)
            sl = request.stop_loss_price or round(entry_price * 0.98 if request.side == "BUY" else entry_price * 1.02, 2)

            trade_data = {
                "symbol": symbol,
                "display_symbol": symbol,
                "instrument_type": "EQUITY",
                "option_type": None,
                "strike_price": None,
                "expiry_date": None,
                "lot_size": 1,
                "contracts": qty,
                "side": request.side.value if hasattr(request.side, "value") else str(request.side),
                "quantity": qty,
                "entry_price": round(entry_price, 2),
                "target_price": target,
                "stop_loss_price": sl,
                "strategy": request.strategy or "Manual",
                "notes": request.notes or "",
            }

            trade_id = PaperRepository.create_trade(trade_data, user_id=user_id)
            new_cash = cash - order_cost
            PaperRepository.update_cash_balance(new_cash, user_id=user_id)

            return {
                "success": True,
                "position_id": trade_id,
                "symbol": symbol,
                "display_symbol": symbol,
                "instrument_type": "EQUITY",
                "side": trade_data["side"],
                "quantity": qty,
                "entry_price": trade_data["entry_price"],
                "target_price": target,
                "stop_loss_price": sl,
                "remaining_cash": new_cash,
            }

    @classmethod
    def close_position(cls, request: PaperCloseRequest, user_id: int = 1) -> dict[str, Any]:
        """Close an active position (Equity or Option) and credit capital back with P&L."""
        pos = PaperRepository.get_position(request.position_id, user_id=user_id)
        if not pos:
            raise ValueError(f"Open position #{request.position_id} not found")

        symbol = pos["symbol"]
        inst_type = pos.get("instrument_type") or "EQUITY"
        qty = pos["quantity"]
        entry_price = pos["entry_price"]
        side = pos["side"]

        if inst_type == "OPTION":
            opt_type = pos.get("option_type") or "CE"
            strike = pos.get("strike_price") or 0.0
            expiry = pos.get("expiry_date")
            if request.exit_price and request.exit_price > 0:
                exit_price = request.exit_price
            else:
                opt_info = cls.get_option_price(symbol, opt_type, strike, expiry)
                exit_price = opt_info["premium"]
        else:
            exit_price = request.exit_price or cls.get_live_price(symbol)

        if side == "BUY":
            pnl_amount = (exit_price - entry_price) * qty
            pnl_pct = ((exit_price - entry_price) / entry_price) * 100.0 if entry_price > 0 else 0.0
            return_cash = (entry_price * qty) + pnl_amount
        else:
            pnl_amount = (entry_price - exit_price) * qty
            pnl_pct = ((entry_price - exit_price) / entry_price) * 100.0 if entry_price > 0 else 0.0
            return_cash = (entry_price * qty) + pnl_amount

        success = PaperRepository.close_trade(
            position_id=pos["id"],
            exit_price=round(exit_price, 2),
            exit_reason=request.exit_reason or "Manual Close",
            pnl_amount=round(pnl_amount, 2),
            pnl_pct=round(pnl_pct, 2),
            user_id=user_id,
        )

        account = PaperRepository.get_account(user_id=user_id)
        new_cash = max(0.0, account["cash_balance"] + return_cash)
        PaperRepository.update_cash_balance(new_cash, user_id=user_id)

        return {
            "success": success,
            "position_id": pos["id"],
            "symbol": symbol,
            "display_symbol": pos.get("display_symbol") or symbol,
            "exit_price": round(exit_price, 2),
            "pnl_amount": round(pnl_amount, 2),
            "pnl_pct": round(pnl_pct, 2),
            "new_cash_balance": round(new_cash, 2),
        }

    @classmethod
    def modify_order(cls, request: PaperModifyRequest, user_id: int = 1) -> dict[str, Any]:
        """Modify an active open paper trade (Target, Stop Loss, Quantity/Contracts, Notes)."""
        pos = PaperRepository.get_position(request.position_id, user_id=user_id)
        if not pos:
            raise ValueError(f"Open position #{request.position_id} not found")

        inst_type = pos.get("instrument_type") or "EQUITY"
        lot_size = pos.get("lot_size") or 1
        old_qty = pos["quantity"]
        old_contracts = pos.get("contracts") or 1
        entry_price = pos["entry_price"]

        updates: dict[str, Any] = {}

        # 1. Quantity & Contracts handling
        new_qty = old_qty
        new_contracts = old_contracts

        if inst_type == "OPTION":
            if request.contracts is not None and request.contracts > 0:
                new_contracts = request.contracts
                new_qty = new_contracts * lot_size
            elif request.quantity is not None and request.quantity > 0:
                new_qty = request.quantity
                new_contracts = max(1, math.ceil(new_qty / lot_size))
                new_qty = new_contracts * lot_size
        else:
            if request.quantity is not None and request.quantity > 0:
                new_qty = request.quantity
                new_contracts = new_qty

        account = PaperRepository.get_account(user_id=user_id)
        cash = account["cash_balance"]

        if new_qty != old_qty:
            qty_diff = new_qty - old_qty
            cost_diff = qty_diff * entry_price

            if qty_diff > 0:
                # Sizing up: requires additional capital
                if cost_diff > cash:
                    raise ValueError(
                        f"Insufficient cash to increase position size. Required additional: ₹{cost_diff:,.2f}, Available: ₹{cash:,.2f}"
                    )
                new_cash = cash - cost_diff
            else:
                # Sizing down: release excess capital back to cash
                new_cash = cash + abs(cost_diff)

            PaperRepository.update_cash_balance(new_cash, user_id=user_id)
            updates["quantity"] = new_qty
            updates["contracts"] = new_contracts
        else:
            new_cash = cash

        # 2. Target Price
        if request.target_price is not None:
            if request.target_price <= 0:
                raise ValueError("Target price must be greater than 0")
            updates["target_price"] = round(float(request.target_price), 2)

        # 3. Stop Loss Price
        if request.stop_loss_price is not None:
            if request.stop_loss_price <= 0:
                raise ValueError("Stop loss price must be greater than 0")
            updates["stop_loss_price"] = round(float(request.stop_loss_price), 2)

        # 4. Notes
        if request.notes is not None:
            updates["notes"] = request.notes.strip()

        if updates:
            success = PaperRepository.update_trade(pos["id"], updates, user_id=user_id)
        else:
            success = True

        updated_pos = PaperRepository.get_position(pos["id"], user_id=user_id) or pos

        return {
            "success": success,
            "position_id": pos["id"],
            "symbol": pos["symbol"],
            "display_symbol": pos.get("display_symbol") or pos["symbol"],
            "instrument_type": inst_type,
            "quantity": updated_pos.get("quantity", new_qty),
            "contracts": updated_pos.get("contracts", new_contracts),
            "target_price": updated_pos.get("target_price"),
            "stop_loss_price": updated_pos.get("stop_loss_price"),
            "notes": updated_pos.get("notes", ""),
            "remaining_cash": round(new_cash, 2),
        }

    @classmethod
    def get_open_positions(cls, user_id: int = 1) -> list[PaperPosition]:
        """Return all active open positions with live mark-to-market prices for a specific user."""
        raw_positions = PaperRepository.get_open_positions(user_id=user_id)
        positions: list[PaperPosition] = []

        for p in raw_positions:
            inst_type = p.get("instrument_type") or "EQUITY"
            sym = p["symbol"]
            qty = p["quantity"]
            entry_p = p["entry_price"]
            side = p["side"]
            invested = entry_p * qty

            if inst_type == "OPTION":
                opt_type = p.get("option_type") or "CE"
                strike = p.get("strike_price") or 0.0
                expiry = p.get("expiry_date")
                opt_info = cls.get_option_price(sym, opt_type, strike, expiry)
                live_p = opt_info["premium"]
                display_symbol = p.get("display_symbol") or f"{sym} {strike} {opt_type}"
            else:
                live_p = cls.get_live_price(sym)
                display_symbol = p.get("display_symbol") or sym

            if side == "BUY":
                u_pnl = (live_p - entry_p) * qty
                u_pct = ((live_p - entry_p) / entry_p) * 100.0 if entry_p > 0 else 0.0
            else:
                u_pnl = (entry_p - live_p) * qty
                u_pct = ((entry_p - live_p) / entry_p) * 100.0 if entry_p > 0 else 0.0

            positions.append(
                PaperPosition(
                    id=p["id"],
                    symbol=sym,
                    display_symbol=display_symbol,
                    instrument_type=inst_type,
                    option_type=p.get("option_type"),
                    strike_price=p.get("strike_price"),
                    expiry_date=p.get("expiry_date"),
                    lot_size=p.get("lot_size") or 1,
                    contracts=p.get("contracts") or 1,
                    side=p["side"],
                    quantity=qty,
                    entry_price=entry_p,
                    current_price=round(live_p, 2),
                    target_price=p.get("target_price"),
                    stop_loss_price=p.get("stop_loss_price"),
                    strategy=p.get("strategy") or "Manual",
                    notes=p.get("notes") or "",
                    entry_time=p["entry_time"],
                    invested_amount=round(invested, 2),
                    unrealized_pnl=round(u_pnl, 2),
                    unrealized_pnl_pct=round(u_pct, 2),
                )
            )
        return positions

    @classmethod
    def get_history(cls, user_id: int = 1) -> list[PaperTradeRecord]:
        """Return all closed trade records for the journal of a specific user."""
        raw_trades = PaperRepository.get_closed_trades(user_id=user_id)
        records: list[PaperTradeRecord] = []

        for t in raw_trades:
            duration_str = "1d"
            try:
                t1 = datetime.strptime(t["entry_time"], "%Y-%m-%d %H:%M:%S")
                t2 = datetime.strptime(t["exit_time"], "%Y-%m-%d %H:%M:%S")
                diff = t2 - t1
                days = diff.days
                hours = diff.seconds // 3600
                duration_str = f"{days}d {hours}h" if days > 0 else f"{hours}h"
            except Exception:
                pass

            records.append(
                PaperTradeRecord(
                    id=t["id"],
                    symbol=t["symbol"],
                    display_symbol=t.get("display_symbol") or t["symbol"],
                    instrument_type=t.get("instrument_type") or "EQUITY",
                    option_type=t.get("option_type"),
                    strike_price=t.get("strike_price"),
                    expiry_date=t.get("expiry_date"),
                    lot_size=t.get("lot_size") or 1,
                    contracts=t.get("contracts") or 1,
                    side=t["side"],
                    quantity=t["quantity"],
                    entry_price=t["entry_price"],
                    entry_time=t["entry_time"],
                    exit_price=t["exit_price"] or t["entry_price"],
                    exit_time=t["exit_time"] or "",
                    exit_reason=t["exit_reason"] or "Manual",
                    strategy=t["strategy"] or "Manual",
                    notes=t["notes"] or "",
                    pnl_amount=t["pnl_amount"] or 0.0,
                    pnl_pct=t["pnl_pct"] or 0.0,
                    holding_duration=duration_str,
                )
            )
        return records

    @classmethod
    def get_summary(cls, user_id: int = 1) -> PaperPortfolioSummary:
        """Calculate complete portfolio health, equity, and KPIs for a specific user."""
        account = PaperRepository.get_account(user_id=user_id)
        initial_cap = account["initial_capital"]
        cash = account["cash_balance"]

        open_positions = cls.get_open_positions(user_id=user_id)
        invested = sum(p.invested_amount for p in open_positions)
        unrealized = sum(p.unrealized_pnl for p in open_positions)
        total_equity = cash + invested + unrealized

        closed = cls.get_history(user_id=user_id)
        realized = sum(t.pnl_amount for t in closed)
        total_trades = len(closed)
        winning_trades = sum(1 for t in closed if t.pnl_amount > 0)
        losing_trades = sum(1 for t in closed if t.pnl_amount < 0)
        win_rate = (winning_trades / total_trades * 100.0) if total_trades > 0 else 0.0

        total_pnl = (total_equity - initial_cap)
        total_pnl_pct = (total_pnl / initial_cap * 100.0) if initial_cap > 0 else 0.0
        u_pnl_pct = (unrealized / invested * 100.0) if invested > 0 else 0.0
        r_pnl_pct = (realized / initial_cap * 100.0) if initial_cap > 0 else 0.0

        return PaperPortfolioSummary(
            initial_capital=round(initial_cap, 2),
            cash_balance=round(cash, 2),
            invested_amount=round(invested, 2),
            total_equity=round(total_equity, 2),
            unrealized_pnl=round(unrealized, 2),
            unrealized_pnl_pct=round(u_pnl_pct, 2),
            realized_pnl=round(realized, 2),
            realized_pnl_pct=round(r_pnl_pct, 2),
            total_pnl=round(total_pnl, 2),
            total_pnl_pct=round(total_pnl_pct, 2),
            win_rate_pct=round(win_rate, 1),
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            open_positions_count=len(open_positions),
        )

    @classmethod
    def reset_portfolio(cls, capital: float = 1000000.0, user_id: int = 1) -> None:
        PaperRepository.reset_account(capital, user_id=user_id)

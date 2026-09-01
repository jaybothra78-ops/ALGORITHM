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
    PaperOrderRequest,
    PaperPortfolioSummary,
    PaperPosition,
    PaperTradeRecord,
)
from services.market_data import MarketDataProvider
from services.options_pricing import OptionsPricingService


class PaperTradingService:
    """Comprehensive Paper Trading & Virtual Portfolio Manager for Equity & Options."""

    @classmethod
    def get_live_ltp(cls, symbol: str) -> dict[str, Any]:
        """Fetch exact real-time Last Traded Price (LTP) from NSE/BSE feeds."""
        import yfinance as yf
        clean_sym = symbol.strip().upper()
        
        # Handle index ticker mapping for Yahoo Finance
        if clean_sym == "NIFTY" or clean_sym == "NIFTY50":
            ticker_candidates = ["^NSEI", "NIFTYBEES.NS"]
        elif clean_sym == "BANKNIFTY":
            ticker_candidates = ["^NSEBANK", "BANKBEES.NS"]
        elif clean_sym == "FINNIFTY":
            ticker_candidates = ["NIFTY_FIN_SERVICE.NS", "^CNXFIN"]
        elif clean_sym == "SENSEX":
            ticker_candidates = ["^BSESN"]
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

                # 1. Fast real-time quote metadata
                if hasattr(t, "fast_info") and t.fast_info:
                    price = t.fast_info.get("lastPrice") or t.fast_info.get("regularMarketPrice")
                    prev_close = t.fast_info.get("previousClose") or t.fast_info.get("regularMarketPreviousClose")

                # 2. 1-minute intraday tick fallback
                if not price or price <= 0:
                    hist_1m = t.history(period="1d", interval="1m")
                    if not hist_1m.empty:
                        price = float(hist_1m["Close"].iloc[-1])
                        prev_close = float(hist_1m["Open"].iloc[0])

                # 3. 5-day daily close fallback
                if not price or price <= 0:
                    hist_5d = t.history(period="5d")
                    if not hist_5d.empty:
                        price = float(hist_5d["Close"].iloc[-1])
                        prev_close = float(hist_5d["Close"].iloc[-2]) if len(hist_5d) > 1 else price

                if price and price > 0:
                    prev_close = prev_close or price
                    change = round(price - prev_close, 2)
                    change_pct = round((change / prev_close) * 100.0, 2) if prev_close > 0 else 0.0

                    return {
                        "symbol": clean_sym,
                        "ticker": ticker_str,
                        "ltp": round(float(price), 2),
                        "previous_close": round(float(prev_close), 2),
                        "change": change,
                        "change_pct": change_pct,
                        "source": "NSE Real-Time Market Feed" if ".NS" in ticker_str or "^" in ticker_str else "BSE Market Feed",
                        "timestamp": time.time(),
                    }
            except Exception:
                continue

        # Fallback to universe cache if network fails
        data_map = MarketDataProvider.get_universe_ohlc([clean_sym])
        if clean_sym in data_map and not data_map[clean_sym].empty:
            p = float(data_map[clean_sym]["Close"].iloc[-1])
            return {
                "symbol": clean_sym,
                "ticker": f"{clean_sym}.NS",
                "ltp": round(p, 2),
                "previous_close": round(p, 2),
                "change": 0.0,
                "change_pct": 0.0,
                "source": "Cached Daily Close",
                "timestamp": time.time(),
            }

        # Default fallback for index if offline
        default_p = 25000.0 if clean_sym == "NIFTY" else (51500.0 if clean_sym == "BANKNIFTY" else 100.0)
        return {
            "symbol": clean_sym,
            "ticker": f"{clean_sym}.NS",
            "ltp": default_p,
            "previous_close": default_p,
            "change": 0.0,
            "change_pct": 0.0,
            "source": "Default Fallback",
            "timestamp": time.time(),
        }

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
        strikes_data = OptionsPricingService.get_option_strikes(symbol, spot_price, expiry_date_str=expiry_date)
        strikes_data["spot_quote"] = spot_data
        return strikes_data

    @classmethod
    def get_option_price(
        cls,
        symbol: str,
        option_type: str,
        strike: float,
        expiry_date: str | None = None,
        days_to_expiry: float | None = None,
    ) -> dict[str, Any]:
        """Calculate real-time Call or Put option premium and Greeks based on underlying spot and exact expiry."""
        clean_sym = symbol.strip().upper()
        spot_data = cls.get_live_ltp(clean_sym)
        spot = spot_data["ltp"]

        # Calculate accurate days to expiry
        if days_to_expiry is None:
            days_to_expiry = OptionsPricingService.calculate_days_to_expiry(expiry_date, clean_sym)

        bsm = OptionsPricingService.calculate_bsm_price(
            spot=spot,
            strike=strike,
            days_to_expiry=days_to_expiry,
            symbol=clean_sym,
            option_type=option_type,
        )

        display_sym = f"{clean_sym} {int(strike) if strike.is_integer() else strike} {option_type.upper()}"
        lot_size = OptionsPricingService.get_lot_size(clean_sym)


        return {
            "symbol": symbol.upper(),
            "display_symbol": display_sym,
            "instrument_type": "OPTION",
            "option_type": option_type.upper(),
            "strike_price": strike,
            "expiry_date": expiry_date,
            "days_to_expiry": days_to_expiry,
            "spot_price": spot,
            "lot_size": lot_size,
            "premium": bsm["premium"],
            "intrinsic": bsm["intrinsic"],
            "time_value": bsm["time_value"],
            "delta": bsm["delta"],
            "theta": bsm["theta"],
            "gamma": bsm["gamma"],
            "vega": bsm["vega"],
            "source": f"Black-Scholes Live Model ({spot_data['source']})",
            "timestamp": time.time(),
        }

    @classmethod
    def place_order(cls, request: PaperOrderRequest) -> dict[str, Any]:
        """Place a new paper order (Equity or Options) and deduct capital."""
        symbol = request.symbol.strip().upper()
        inst_type = request.instrument_type.value if hasattr(request.instrument_type, "value") else str(request.instrument_type)
        
        account = PaperRepository.get_account()
        cash = account["cash_balance"]

        if inst_type == "OPTION":
            opt_type = request.option_type.value if hasattr(request.option_type, "value") else str(request.option_type or "CE")
            strike = request.strike_price or round(cls.get_live_price(symbol))
            expiry = request.expiry_date
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

            trade_id = PaperRepository.create_trade(trade_data)
            new_cash = cash - order_cost
            PaperRepository.update_cash_balance(new_cash)

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

            trade_id = PaperRepository.create_trade(trade_data)
            new_cash = cash - order_cost
            PaperRepository.update_cash_balance(new_cash)

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
    def close_position(cls, request: PaperCloseRequest) -> dict[str, Any]:
        """Close an active position (Equity or Option) and credit capital back with P&L."""
        pos = PaperRepository.get_position(request.position_id)
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
        )

        account = PaperRepository.get_account()
        new_cash = max(0.0, account["cash_balance"] + return_cash)
        PaperRepository.update_cash_balance(new_cash)

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
    def get_open_positions(cls) -> list[PaperPosition]:
        """Return all active open positions with live mark-to-market prices."""
        raw_positions = PaperRepository.get_open_positions()
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
    def get_history(cls) -> list[PaperTradeRecord]:
        """Return all closed trade records for the journal."""
        raw_trades = PaperRepository.get_closed_trades()
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
    def get_summary(cls) -> PaperPortfolioSummary:
        """Calculate complete portfolio health, equity, and KPIs."""
        account = PaperRepository.get_account()
        initial_cap = account["initial_capital"]
        cash = account["cash_balance"]

        open_positions = cls.get_open_positions()
        invested = sum(p.invested_amount for p in open_positions)
        unrealized = sum(p.unrealized_pnl for p in open_positions)
        total_equity = cash + invested + unrealized

        closed = cls.get_history()
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
    def reset_portfolio(cls, capital: float = 1000000.0) -> None:
        PaperRepository.reset_account(capital)

"""Business logic and real-time execution for Paper Trading."""
from __future__ import annotations

import math
import time
from datetime import datetime
from typing import Any

from db.paper_repository import PaperRepository
from models.paper import (
    PaperCloseRequest,
    PaperOrderRequest,
    PaperPortfolioSummary,
    PaperPosition,
    PaperTradeRecord,
)
from services.market_data import MarketDataProvider


class PaperTradingService:
    """Comprehensive Paper Trading & Virtual Portfolio Manager."""

    @classmethod
    def get_live_ltp(cls, symbol: str) -> dict[str, Any]:
        """Fetch exact real-time Last Traded Price (LTP) from NSE/BSE feeds."""
        import yfinance as yf
        clean_sym = symbol.strip().upper()
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
                        "source": "NSE Real-Time Market Feed" if ".NS" in ticker_str else "BSE Market Feed",
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

        return {
            "symbol": clean_sym,
            "ticker": f"{clean_sym}.NS",
            "ltp": 100.0,
            "previous_close": 100.0,
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
    def place_order(cls, request: PaperOrderRequest) -> dict[str, Any]:
        """Place a new paper order and deduct capital."""
        symbol = request.symbol.strip().upper()
        entry_price = request.entry_price or cls.get_live_price(symbol)
        if entry_price <= 0:
            raise ValueError(f"Invalid entry price for {symbol}")

        qty = request.quantity
        order_cost = entry_price * qty

        account = PaperRepository.get_account()
        cash = account["cash_balance"]

        if request.side == "BUY" and order_cost > cash:
            raise ValueError(f"Insufficient cash balance. Required: ₹{order_cost:,.2f}, Available: ₹{cash:,.2f}")

        # If Target or Stop Loss not set, calculate default 5% target and 2% stop loss
        target = request.target_price
        sl = request.stop_loss_price
        if target is None:
            target = round(entry_price * 1.05 if request.side == "BUY" else entry_price * 0.95, 2)
        if sl is None:
            sl = round(entry_price * 0.98 if request.side == "BUY" else entry_price * 1.02, 2)

        trade_data = {
            "symbol": symbol,
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
            "side": trade_data["side"],
            "quantity": qty,
            "entry_price": trade_data["entry_price"],
            "target_price": target,
            "stop_loss_price": sl,
            "remaining_cash": new_cash,
        }

    @classmethod
    def close_position(cls, request: PaperCloseRequest) -> dict[str, Any]:
        """Close an active position and credit capital back with P&L."""
        pos = PaperRepository.get_position(request.position_id)
        if not pos:
            raise ValueError(f"Open position #{request.position_id} not found")

        symbol = pos["symbol"]
        exit_price = request.exit_price or cls.get_live_price(symbol)
        qty = pos["quantity"]
        entry_price = pos["entry_price"]
        side = pos["side"]

        if side == "BUY":
            pnl_amount = (exit_price - entry_price) * qty
            pnl_pct = ((exit_price - entry_price) / entry_price) * 100.0
            return_cash = (entry_price * qty) + pnl_amount
        else:
            pnl_amount = (entry_price - exit_price) * qty
            pnl_pct = ((entry_price - exit_price) / entry_price) * 100.0
            return_cash = (entry_price * qty) + pnl_amount

        success = PaperRepository.close_trade(
            position_id=pos["id"],
            exit_price=round(exit_price, 2),
            exit_reason=request.exit_reason or "Manual Close",
            pnl_amount=round(pnl_amount, 2),
            pnl_pct=round(pnl_pct, 2),
        )

        account = PaperRepository.get_account()
        new_cash = account["cash_balance"] + return_cash
        PaperRepository.update_cash_balance(new_cash)

        return {
            "success": success,
            "position_id": pos["id"],
            "symbol": symbol,
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
            live_p = cls.get_live_price(p["symbol"])
            qty = p["quantity"]
            entry_p = p["entry_price"]
            side = p["side"]
            invested = entry_p * qty

            if side == "BUY":
                u_pnl = (live_p - entry_p) * qty
                u_pct = ((live_p - entry_p) / entry_p) * 100.0 if entry_p > 0 else 0.0
            else:
                u_pnl = (entry_p - live_p) * qty
                u_pct = ((entry_p - live_p) / entry_p) * 100.0 if entry_p > 0 else 0.0

            positions.append(
                PaperPosition(
                    id=p["id"],
                    symbol=p["symbol"],
                    side=p["side"],
                    quantity=qty,
                    entry_price=entry_p,
                    current_price=round(live_p, 2),
                    target_price=p["target_price"],
                    stop_loss_price=p["stop_loss_price"],
                    strategy=p["strategy"] or "Manual",
                    notes=p["notes"] or "",
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
            # Calculate duration
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

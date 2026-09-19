"""FastAPI application routes and endpoint handlers."""
from __future__ import annotations

from datetime import date
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from api.auth_routes import get_current_user
from db.repository import SignalRepository
from models.backtest import BacktestRequest, BacktestResponse
from models.news import NewsAnalysisRequest, NewsAnalysisResponse
from models.paper import (
    PaperCloseRequest,
    PaperModifyRequest,
    PaperOrderRequest,
    PaperPortfolioSummary,
    PaperPosition,
    PaperTradeRecord,
)
from models.signal import LookbackResponse, ScanResponse
from services.scanner import ScannerEngine




router = APIRouter(tags=["Scanner & Screener"])


@router.get("/signals/today", response_model=list[dict[str, Any]])
def get_today_signals(
    strategy: str | None = Query(None, description="Filter by strategy (RSI, RB_KnoxDiv)"),
    index: str | None = Query(None, description="Filter by index/watchlist (FNO, Watchlist, Nifty50, etc.)"),
    signal_type: str | None = Query(None, description="Filter by signal type (buy, sell)"),
) -> list[dict[str, Any]]:
    """Retrieve all confirmed signals recorded for today."""
    return SignalRepository.get_signals(
        scan_date=date.today().isoformat(),
        index=index,
        signal_type=signal_type,
        strategy=strategy,
    )


@router.get("/signals/history", response_model=list[dict[str, Any]])
def get_signals_history(
    date_str: str = Query(..., alias="date", description="Date formatted as YYYY-MM-DD"),
    strategy: str | None = Query(None),
    index: str | None = Query(None),
    signal_type: str | None = Query(None),
) -> list[dict[str, Any]]:
    """Retrieve historical signals for any given date."""
    try:
        parsed_date = date.fromisoformat(date_str)
    except ValueError as exc:
        raise HTTPException(422, "Invalid date format. Must be YYYY-MM-DD.") from exc

    return SignalRepository.get_signals(
        scan_date=parsed_date.isoformat(),
        index=index,
        signal_type=signal_type,
        strategy=strategy,
    )


@router.get("/screener/lookback", response_model=dict[str, Any])
@router.get("/signals/lookback", response_model=dict[str, Any])
def get_lookback_screener(
    lookback_days: int | None = Query(None, ge=1, le=60, description="Historical lookback window in trading days"),
    days: int | None = Query(None, ge=1, le=60, description="Alias for lookback_days"),
    rsi_length: int = Query(14, ge=2, le=100, description="RSI period length"),

    index: str | None = Query(None, description="Index or Watchlist filter"),
    index_name: str | None = Query(None, description="Alias for index"),
    signal_filter: str | None = Query(None, description="Filter: oversold, overbought, buy, sell, signals_only"),
    filter: str | None = Query(None, description="Alias for signal_filter"),
    symbol: str | None = Query(None, description="Specific ticker search"),
    include_neutral: bool = Query(False, description="Include neutral unflagged stocks"),
    refresh: bool = Query(False, description="Force fresh market data download"),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Multi-condition lookback screener for RSI extremes and strategy signals."""
    effective_days = days or lookback_days or 1
    effective_index = index or index_name or None
    effective_filter = filter or signal_filter or None

    try:
        resp = ScannerEngine.screen_lookback(
            lookback_days=effective_days,
            rsi_length=rsi_length,
            index_filter=effective_index,
            signal_filter=effective_filter,
            symbol=symbol,
            include_neutral=include_neutral,
            force_refresh=refresh,
            user_id=user["id"],
        )
        res_dict = resp.model_dump()

        items = res_dict.get("items", [])
        oversold = sum(1 for it in items if it.get("primary_type") in ("oversold", "buy") or (it.get("rsi") is not None and it["rsi"] <= 30))
        overbought = sum(1 for it in items if it.get("primary_type") in ("overbought", "sell") or (it.get("rsi") is not None and it["rsi"] >= 70))
        knoxville = sum(1 for it in items if any((r.get("category") == "Strategy_Signal" and r.get("strategy") == "RB_KnoxDiv") or "knox" in r.get("text", "").lower() for r in it.get("reasons", [])))

        import time
        from services.paper_service import PaperTradingService
        cached_ltps = PaperTradingService._LTP_CACHE
        now_ts = time.time()

        signals_list = []
        for it in items:
            sym = it["symbol"]
            close_p = it.get("current_price", 0.0)
            ltp = close_p
            is_live = False

            if sym in cached_ltps:
                c_time, c_val = cached_ltps[sym]
                if now_ts - c_time < PaperTradingService._LTP_TTL and c_val.get("ltp"):
                    ltp = c_val["ltp"]
                    is_live = True

            reasons = it.get("reasons", [])
            is_knox = any((r.get("category") == "Strategy_Signal" and r.get("strategy") == "RB_KnoxDiv") or "knox" in r.get("text", "").lower() for r in reasons)
            is_ma200 = any(r.get("category") == "MA200" or "200" in r.get("text", "") for r in reasons)

            if is_knox:
                strat_label = "Knoxville"
            elif is_ma200:
                strat_label = "200SMA"
            else:
                strat_label = "RSI"

            signals_list.append({
                "symbol": sym,
                "universe": it.get("index_membership", ""),
                "signal_type": it.get("primary_type", "neutral"),
                "close_price": ltp,
                "daily_close": close_p,
                "is_live_price": is_live,
                "rsi": it.get("rsi"),
                "rsi_ma": it.get("rsi_ma"),
                "sma_200": it.get("sma_200"),
                "is_knox_divergence": is_knox,
                "is_touching_200sma": is_ma200,
                "scan_date": it.get("signal_date") or date.today().isoformat(),
                "strategy": strat_label,
                "reason_summary": it.get("reason_summary", ""),
            })

        return {
            **res_dict,
            "total_signals": len(signals_list),
            "oversold_count": oversold,
            "overbought_count": overbought,
            "knoxville_count": knoxville,
            "signals": signals_list,
        }
    except Exception as exc:
        raise HTTPException(500, f"Lookback screener failed: {exc}") from exc



@router.get("/universe/symbols", response_model=list[dict[str, Any]])
def get_universe_symbols_endpoint(
    user: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Retrieve full list of universe symbols and index memberships for auto-complete."""
    try:
        from services.universe import load_universe
        universe = load_universe(user_id=user["id"])
        return [{"symbol": s, "membership": sorted(list(m))} for s, m in sorted(universe.items())]
    except Exception as exc:
        raise HTTPException(500, f"Failed to retrieve universe symbols: {exc}") from exc



@router.post("/scan/run", response_model=ScanResponse)
@router.post("/signals/scan", response_model=ScanResponse)
def trigger_scan_now(

    strategy: str = Query("RSI", description="Strategy to execute (RSI, RB_KnoxDiv, ALL)"),
) -> ScanResponse:
    """Manually trigger daily market scan and signal persistence."""
    try:
        return ScannerEngine.run_daily_scan(strategy_name=strategy)
    except Exception as exc:
        raise HTTPException(500, f"Scan execution failed: {exc}") from exc


@router.post("/watchlist/import", response_model=dict[str, Any])
@router.post("/watchlist/import-tradingview", response_model=dict[str, Any])
def import_watchlist_endpoint(
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Import a TradingView public watchlist via URL for the authenticated user."""
    url = payload.get("url", "").strip()
    custom_name = payload.get("custom_name") or payload.get("name")
    if not url:
        raise HTTPException(400, "TradingView watchlist URL is required.")

    try:
        from services.universe import import_tradingview_watchlist
        res = import_tradingview_watchlist(url=url, custom_name=custom_name, user_id=user["id"])
        return {
            "status": "success",
            "watchlist_name": res["name"],
            "symbols_count": res["count"],
            "symbols": res["symbols"],
            "url": res.get("url", url),
        }
    except Exception as exc:
        raise HTTPException(400, f"Failed to import watchlist: {exc}") from exc


@router.get("/watchlist/list", response_model=dict[str, Any])
def list_watchlists_endpoint(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Return all custom imported watchlists as dictionary for the authenticated user."""
    from services.universe import load_custom_watchlists
    return load_custom_watchlists(user_id=user["id"])


@router.get("/watchlist/custom", response_model=dict[str, Any])
def list_custom_watchlists_endpoint(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Return all custom imported watchlists as array for the authenticated user."""
    from services.universe import load_custom_watchlists
    cw = load_custom_watchlists(user_id=user["id"])
    return {
        "watchlists": [{"name": k, "count": len(v), "symbols": v} for k, v in cw.items()]
    }


@router.post("/watchlist/custom", response_model=dict[str, Any])
def create_custom_watchlist_endpoint(
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Create or update a custom watchlist for the authenticated user."""
    name = payload.get("name", "").strip()
    symbols = payload.get("symbols", [])
    if not name:
        raise HTTPException(400, "Watchlist name is required.")
    from services.universe import save_custom_watchlist
    save_custom_watchlist(name, symbols, user_id=user["id"])
    return {"status": "success", "name": name, "symbols": symbols, "count": len(symbols)}



@router.delete("/watchlist/{name}")
@router.delete("/watchlist/custom/{name}")
def delete_watchlist_endpoint(
    name: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    """Delete an imported custom watchlist for the authenticated user."""
    from services.universe import delete_custom_watchlist
    success = delete_custom_watchlist(name, user_id=user["id"])
    if not success:
        raise HTTPException(404, f"Watchlist '{name}' not found.")
    return {"status": "success", "message": f"Watchlist '{name}' deleted."}



@router.post("/backtest/run", response_model=BacktestResponse)
def run_backtest_endpoint(
    payload: BacktestRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> BacktestResponse:
    """Run simulated strategy backtest on historical market data."""
    try:
        from services.backtester import BacktesterEngine
        return BacktesterEngine.run_backtest(payload, user_id=user["id"])
    except Exception as exc:
        raise HTTPException(500, f"Backtest simulation failed: {exc}") from exc


@router.get("/market/ohlc/{symbol}", response_model=list[dict[str, Any]])
def get_symbol_ohlc(
    symbol: str,
    period: str = Query("1y", description="Time period window (3mo, 6mo, 1y, 2y, 3y, 5y, max, or 60d for intraday)"),
    interval: str = Query("1d", description="Candle interval: 1d (daily) or 30m (30-minute intraday)"),
) -> list[dict[str, Any]]:
    """Return historical OHLC candles (daily or 30-minute interval) for candlestick chart rendering."""
    s_clean = symbol.strip().upper()
    try:
        from services.market_data import MarketDataProvider

        if interval == "30m":
            ohlc_dict = MarketDataProvider.get_intraday_30m_data([s_clean], period="60d")
            if s_clean not in ohlc_dict or ohlc_dict[s_clean].empty:
                raise HTTPException(404, f"No 30-minute intraday OHLC history available for {s_clean}")

            df = ohlc_dict[s_clean]
            candles = []
            for idx, row in df.iterrows():
                ts_sec = int(idx.timestamp())
                dt_str = idx.strftime("%Y-%m-%d %H:%M") if hasattr(idx, "strftime") else str(idx)[:16]
                candles.append({
                    "time": ts_sec,
                    "datetime": dt_str,
                    "open": round(float(row["Open"]), 2),
                    "high": round(float(row["High"]), 2),
                    "low": round(float(row["Low"]), 2),
                    "close": round(float(row["Close"]), 2),
                })
            return candles
        else:
            ohlc_dict = MarketDataProvider.get_universe_ohlc([s_clean], period=period)
            if s_clean not in ohlc_dict or ohlc_dict[s_clean].empty:
                raise HTTPException(404, f"No OHLC history available for {s_clean}")

            df = ohlc_dict[s_clean]
            candles = []
            for idx, row in df.iterrows():
                date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
                candles.append({
                    "time": date_str,
                    "datetime": date_str,
                    "open": round(float(row["Open"]), 2),
                    "high": round(float(row["High"]), 2),
                    "low": round(float(row["Low"]), 2),
                    "close": round(float(row["Close"]), 2),
                })
            return candles
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Failed to fetch OHLC for {s_clean}: {exc}") from exc



@router.get("/news/analyze", response_model=NewsAnalysisResponse)
def analyze_news_get_endpoint(
    symbol: str = Query(..., description="Stock ticker symbol (e.g. TVSMOTOR, RELIANCE)"),
    days: int = Query(7, ge=1, le=30, description="Lookback window in days for news search"),
) -> NewsAnalysisResponse:
    """Fetch live financial news and perform AI sentiment synthesis via GET query params."""
    try:
        from services.news_service import NewsService
        req = NewsAnalysisRequest(symbol=symbol, days=days)
        return NewsService.analyze_news(req)
    except Exception as exc:
        raise HTTPException(500, f"News analysis failed for {symbol}: {exc}") from exc


@router.post("/news/analyze", response_model=NewsAnalysisResponse)
def analyze_news_endpoint(
    payload: NewsAnalysisRequest,
) -> NewsAnalysisResponse:
    """Fetch live financial news and perform AI sentiment synthesis."""
    try:
        from services.news_service import NewsService
        return NewsService.analyze_news(payload)
    except Exception as exc:
        raise HTTPException(500, f"News analysis failed: {exc}") from exc


@router.post("/news/article-chat", response_model=dict[str, Any])
def analyze_article_chat_endpoint(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Provide a 100-150 word deep dive, key bullet points, and interactive Q&A for an individual news article."""
    try:
        from services.news_service import NewsService
        symbol = payload.get("symbol", "NIFTY")
        title = payload.get("article_title", "")
        summary = payload.get("article_summary", "")
        link = payload.get("article_link", "")
        question = payload.get("user_question", None)

        if not title:
            raise HTTPException(400, "Article title is required.")

        return NewsService.analyze_article_chat(
            symbol=symbol,
            article_title=title,
            article_summary=summary,
            article_link=link,
            user_question=question,
        )
    except Exception as exc:
        raise HTTPException(500, f"Article analysis failed: {exc}") from exc


# -------------------------------------------------------------
# Paper Trading & Virtual Portfolio Endpoints
# -------------------------------------------------------------
@router.get("/market/ltp", response_model=dict[str, Any])
def get_market_ltp_endpoint(
    symbol: str = Query(..., description="Stock or Index ticker symbol (e.g. TVSMOTOR, NIFTY)"),
) -> dict[str, Any]:
    """Fetch exact live Last Traded Price (LTP) and market quote."""
    try:
        from services.paper_service import PaperTradingService
        return PaperTradingService.get_live_ltp(symbol)
    except Exception as exc:
        raise HTTPException(500, f"Failed to fetch live price for {symbol}: {exc}") from exc


@router.get("/market/option-strikes", response_model=dict[str, Any])
def get_option_strikes_endpoint(
    symbol: str = Query(..., description="Stock or Index ticker (e.g. NIFTY, TVSMOTOR, RELIANCE)"),
    expiry_date: str | None = Query(None, description="Expiry date in YYYY-MM-DD format"),
) -> dict[str, Any]:
    """Return spot price, ATM strike, standard step size, exact NSE expiries, and strike ladder for Options trading."""
    try:
        from services.paper_service import PaperTradingService
        return PaperTradingService.get_option_strikes(symbol, expiry_date=expiry_date)
    except Exception as exc:
        raise HTTPException(500, f"Failed to fetch option strikes for {symbol}: {exc}") from exc



@router.get("/market/option-price", response_model=dict[str, Any])
def get_option_price_endpoint(
    symbol: str = Query(..., description="Underlying Stock or Index (e.g. NIFTY, TVSMOTOR)"),
    option_type: str = Query("CE", description="CE (Call) or PE (Put)"),
    strike: float | None = Query(None, description="Strike price (e.g. 25000, optional: auto-calculated ATM strike if omitted)"),
    expiry_date: str | None = Query(None, description="Expiry date in YYYY-MM-DD or alias ('weekly', 'monthly')"),
) -> dict[str, Any]:
    """Fetch live option premium, intrinsic value, time value, and Greeks for a specific Call or Put strike."""
    try:
        from services.paper_service import PaperTradingService
        return PaperTradingService.get_option_price(
            symbol=symbol,
            option_type=option_type,
            strike=strike,
            expiry_date=expiry_date,
        )
    except Exception as exc:
        raise HTTPException(500, f"Failed to calculate option price for {symbol}: {exc}") from exc


@router.get("/market/fno-symbols", response_model=list[dict[str, str]])
def get_fno_symbols_endpoint() -> list[dict[str, str]]:
    """Return all available F&O tradeable indices and equity symbols in the user universe."""
    try:
        from services.groww_service import GrowwOptionsService
        slugs = GrowwOptionsService.get_instance()._SLUG_CACHE
        indices = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"]
        result = []
        for idx in indices:
            result.append({"symbol": idx, "type": "INDEX"})
        for sym in sorted(slugs.keys()):
            if sym not in indices and sym not in ("NIFTY50",):
                result.append({"symbol": sym, "type": "STOCK"})
        return result
    except Exception as exc:
        raise HTTPException(500, f"Failed to fetch F&O symbols: {exc}") from exc


@router.get("/paper/summary", response_model=PaperPortfolioSummary)
def get_paper_summary_endpoint(user: dict[str, Any] = Depends(get_current_user)) -> PaperPortfolioSummary:
    """Return overall virtual portfolio summary and KPIs for the authenticated user."""
    try:
        from services.paper_service import PaperTradingService
        return PaperTradingService.get_summary(user_id=user["id"])
    except Exception as exc:
        raise HTTPException(500, f"Failed to calculate paper summary: {exc}") from exc


@router.get("/paper/positions", response_model=list[PaperPosition])
def get_paper_positions_endpoint(user: dict[str, Any] = Depends(get_current_user)) -> list[PaperPosition]:
    """Return active open paper positions with live mark-to-market prices for the authenticated user."""
    try:
        from services.paper_service import PaperTradingService
        return PaperTradingService.get_open_positions(user_id=user["id"])
    except Exception as exc:
        raise HTTPException(500, f"Failed to get paper positions: {exc}") from exc


@router.post("/paper/order", response_model=dict[str, Any])
def place_paper_order_endpoint(
    payload: PaperOrderRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Execute a new paper trade order for the authenticated user."""
    try:
        from services.paper_service import PaperTradingService
        return PaperTradingService.place_order(payload, user_id=user["id"])
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Order placement failed: {exc}") from exc


@router.post("/paper/close", response_model=dict[str, Any])
def close_paper_position_endpoint(
    payload: PaperCloseRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Close an open paper position for the authenticated user."""
    try:
        from services.paper_service import PaperTradingService
        return PaperTradingService.close_position(payload, user_id=user["id"])
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Failed to close position: {exc}") from exc


@router.post("/paper/modify", response_model=dict[str, Any])
def modify_paper_order_endpoint(
    payload: PaperModifyRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Modify an active open paper trade order or position for the authenticated user."""
    try:
        from services.paper_service import PaperTradingService
        return PaperTradingService.modify_order(payload, user_id=user["id"])
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Failed to modify position: {exc}") from exc


@router.get("/paper/history", response_model=list[PaperTradeRecord])
def get_paper_history_endpoint(user: dict[str, Any] = Depends(get_current_user)) -> list[PaperTradeRecord]:
    """Return completed trade history journal for the authenticated user."""
    try:
        from services.paper_service import PaperTradingService
        return PaperTradingService.get_history(user_id=user["id"])
    except Exception as exc:
        raise HTTPException(500, f"Failed to get paper trade history: {exc}") from exc


@router.post("/paper/reset", response_model=dict[str, Any])
def reset_paper_portfolio_endpoint(
    payload: dict[str, Any] | None = None,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Reset virtual account balance to initial capital for the authenticated user."""
    capital = float((payload or {}).get("capital", 1000000.0))
    try:
        from services.paper_service import PaperTradingService
        PaperTradingService.reset_portfolio(capital, user_id=user["id"])
        return {"status": "success", "message": f"Portfolio reset to ₹{capital:,.2f}"}
    except Exception as exc:
        raise HTTPException(500, f"Failed to reset portfolio: {exc}") from exc

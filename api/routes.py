"""FastAPI application routes and endpoint handlers."""
from __future__ import annotations

from datetime import date
from typing import Any
from fastapi import APIRouter, HTTPException, Query
from db.repository import SignalRepository
from models.backtest import BacktestRequest, BacktestResponse
from models.news import NewsAnalysisRequest, NewsAnalysisResponse
from models.paper import (
    PaperCloseRequest,
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
        )
        res_dict = resp.model_dump()

        items = res_dict.get("items", [])
        oversold = sum(1 for it in items if it.get("primary_type") in ("oversold", "buy") or (it.get("rsi") is not None and it["rsi"] <= 30))
        overbought = sum(1 for it in items if it.get("primary_type") in ("overbought", "sell") or (it.get("rsi") is not None and it["rsi"] >= 70))
        knoxville = sum(1 for it in items if any(r.get("category") == "Strategy_Signal" or "knox" in r.get("tag", "").lower() for r in it.get("reasons", [])))

        signals_list = []
        for it in items:
            reasons = it.get("reasons", [])
            is_knox = any(r.get("category") == "Strategy_Signal" or "knox" in r.get("tag", "").lower() for r in reasons)
            is_ma200 = any(r.get("category") == "MA200" or "200" in r.get("tag", "") for r in reasons)
            signals_list.append({
                "symbol": it["symbol"],
                "universe": it.get("index_membership", ""),
                "signal_type": it.get("primary_type", "neutral"),
                "close_price": it.get("current_price", 0.0),
                "rsi": it.get("rsi"),
                "rsi_ma": it.get("rsi_ma"),
                "sma_200": it.get("sma_200"),
                "is_knox_divergence": is_knox,
                "is_touching_200sma": is_ma200,
                "scan_date": it.get("signal_date") or datetime.date.today().isoformat(),
                "strategy": "Knoxville" if is_knox else ("200SMA" if is_ma200 else "RSI"),
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
def get_universe_symbols_endpoint() -> list[dict[str, Any]]:
    """Retrieve full list of universe symbols and index memberships for auto-complete."""
    try:
        from services.universe import load_universe
        universe = load_universe()
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
) -> dict[str, Any]:
    """Import a TradingView public watchlist via URL."""
    url = payload.get("url", "").strip()
    custom_name = payload.get("custom_name") or payload.get("name")
    if not url:
        raise HTTPException(400, "TradingView watchlist URL is required.")

    try:
        from services.universe import import_tradingview_watchlist
        res = import_tradingview_watchlist(url=url, custom_name=custom_name)
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
def list_watchlists_endpoint() -> dict[str, Any]:
    """Return all custom imported watchlists as dictionary."""
    from services.universe import load_custom_watchlists
    return load_custom_watchlists()


@router.get("/watchlist/custom", response_model=dict[str, Any])
def list_custom_watchlists_endpoint() -> dict[str, Any]:
    """Return all custom imported watchlists as array."""
    from services.universe import load_custom_watchlists
    cw = load_custom_watchlists()
    return {
        "watchlists": [{"name": k, "count": len(v), "symbols": v} for k, v in cw.items()]
    }


@router.delete("/watchlist/{name}")
@router.delete("/watchlist/custom/{name}")
def delete_watchlist_endpoint(name: str) -> dict[str, str]:
    """Delete an imported custom watchlist."""
    from services.universe import delete_custom_watchlist
    success = delete_custom_watchlist(name)
    if not success:
        raise HTTPException(404, f"Watchlist '{name}' not found.")
    return {"status": "success", "message": f"Watchlist '{name}' deleted."}



@router.post("/backtest/run", response_model=BacktestResponse)
def run_backtest_endpoint(
    payload: BacktestRequest,
) -> BacktestResponse:
    """Run simulated strategy backtest on historical market data."""
    try:
        from services.backtester import BacktesterEngine
        return BacktesterEngine.run_backtest(payload)
    except Exception as exc:
        raise HTTPException(500, f"Backtest simulation failed: {exc}") from exc


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
        api_key = payload.get("api_key", None)

        if not title:
            raise HTTPException(400, "Article title is required.")

        return NewsService.analyze_article_chat(
            symbol=symbol,
            article_title=title,
            article_summary=summary,
            article_link=link,
            user_question=question,
            api_key=api_key or NewsService.get_api_key(),
        )
    except Exception as exc:
        raise HTTPException(500, f"Article analysis failed: {exc}") from exc


@router.get("/news/key", response_model=dict[str, Any])
def get_news_key_status() -> dict[str, Any]:
    """Check whether a Claude API key has been registered."""
    from services.news_service import NewsService
    key = NewsService.get_api_key()
    return {
        "has_key": bool(key),
        "key_masked": f"{key[:7]}...{key[-4:]}" if key and len(key) > 12 else None,
    }


@router.post("/news/key", response_model=dict[str, Any])
def save_news_key_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    """Register or update Anthropic Claude API key for live deep-dive synthesis."""
    from services.news_service import NewsService
    key = (payload.get("api_key") or "").strip()
    if not key:
        raise HTTPException(400, "API key cannot be empty.")
    NewsService.set_api_key(key)
    return {"status": "success", "message": "Claude API key registered successfully."}


@router.delete("/news/key", response_model=dict[str, Any])
def clear_news_key_endpoint() -> dict[str, Any]:
    """Clear registered Anthropic Claude API key."""
    from services.news_service import NewsService
    NewsService.set_api_key("")
    return {"status": "success", "message": "Claude API key cleared."}





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
    strike: float = Query(..., description="Strike price (e.g. 25000)"),
    expiry_date: str | None = Query(None, description="Expiry date in YYYY-MM-DD format"),
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


@router.get("/paper/summary", response_model=PaperPortfolioSummary)
def get_paper_summary_endpoint() -> PaperPortfolioSummary:


    """Return overall virtual portfolio summary and KPIs."""
    try:
        from services.paper_service import PaperTradingService
        return PaperTradingService.get_summary()
    except Exception as exc:
        raise HTTPException(500, f"Failed to calculate paper summary: {exc}") from exc


@router.get("/paper/positions", response_model=list[PaperPosition])
def get_paper_positions_endpoint() -> list[PaperPosition]:
    """Return active open paper positions with live mark-to-market prices."""
    try:
        from services.paper_service import PaperTradingService
        return PaperTradingService.get_open_positions()
    except Exception as exc:
        raise HTTPException(500, f"Failed to get paper positions: {exc}") from exc


@router.post("/paper/order", response_model=dict[str, Any])
def place_paper_order_endpoint(
    payload: PaperOrderRequest,
) -> dict[str, Any]:
    """Execute a new paper trade order."""
    try:
        from services.paper_service import PaperTradingService
        return PaperTradingService.place_order(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Order placement failed: {exc}") from exc


@router.post("/paper/close", response_model=dict[str, Any])
def close_paper_position_endpoint(
    payload: PaperCloseRequest,
) -> dict[str, Any]:
    """Close an open paper position."""
    try:
        from services.paper_service import PaperTradingService
        return PaperTradingService.close_position(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Failed to close position: {exc}") from exc


@router.get("/paper/history", response_model=list[PaperTradeRecord])
def get_paper_history_endpoint() -> list[PaperTradeRecord]:
    """Return completed trade history journal."""
    try:
        from services.paper_service import PaperTradingService
        return PaperTradingService.get_history()
    except Exception as exc:
        raise HTTPException(500, f"Failed to get paper trade history: {exc}") from exc


@router.post("/paper/reset", response_model=dict[str, Any])
def reset_paper_portfolio_endpoint(
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Reset virtual account balance to initial capital."""
    capital = float((payload or {}).get("capital", 1000000.0))
    try:
        from services.paper_service import PaperTradingService
        PaperTradingService.reset_portfolio(capital)
        return {"status": "success", "message": f"Portfolio reset to ₹{capital:,.2f}"}
    except Exception as exc:
        raise HTTPException(500, f"Failed to reset portfolio: {exc}") from exc


# -------------------------------------------------------------
# Zerodha Live Stream Connection Endpoints
# -------------------------------------------------------------
@router.get("/zerodha/status", response_model=dict[str, Any])
def get_zerodha_status_endpoint() -> dict[str, Any]:
    """Return whether Zerodha live broker feed is connected."""
    try:
        from services.zerodha_service import ZerodhaService
        zs = ZerodhaService.get_instance()
        return {
            "connected": zs.is_connected,
            "method": "KiteConnect" if zs._kite_client else ("Web Enctoken" if zs._enctoken else "Disconnected"),
            "user_id": zs._user_id or (zs._kite_client.user_id if zs._kite_client and hasattr(zs._kite_client, "user_id") else None),
        }
    except Exception as exc:
        return {"connected": False, "method": "Disconnected", "error": str(exc)}


@router.post("/zerodha/connect", response_model=dict[str, Any])
def connect_zerodha_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    """Connect Zerodha via Enctoken or KiteConnect API."""
    try:
        from services.zerodha_service import ZerodhaService
        zs = ZerodhaService.get_instance()
        
        enctoken = payload.get("enctoken")
        user_id = payload.get("user_id")
        api_key = payload.get("api_key")
        access_token = payload.get("access_token")

        if enctoken and user_id:
            os.environ["ZERODHA_ENCTOKEN"] = str(enctoken).strip()
            os.environ["ZERODHA_USER_ID"] = str(user_id).strip()
            zs.initialize()
            return {"status": "success", "message": "Zerodha Web Enctoken session connected successfully!"}
        elif api_key and access_token:
            os.environ["KITE_API_KEY"] = str(api_key).strip()
            os.environ["KITE_ACCESS_TOKEN"] = str(access_token).strip()
            zs.initialize()
            return {"status": "success", "message": "Zerodha KiteConnect developer session connected successfully!"}
        else:
            raise HTTPException(400, "Provide either (enctoken + user_id) or (api_key + access_token).")
    except Exception as exc:
        raise HTTPException(500, f"Failed to connect Zerodha: {exc}") from exc






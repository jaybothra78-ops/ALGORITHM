"""FastAPI application routes and endpoint handlers."""
from __future__ import annotations

from datetime import date
from typing import Any
from fastapi import APIRouter, HTTPException, Query
from db.repository import SignalRepository
from models.backtest import BacktestRequest, BacktestResponse
from models.news import NewsAnalysisRequest, NewsAnalysisResponse
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


@router.get("/screener/lookback", response_model=LookbackResponse)
def get_lookback_screener(
    lookback_days: int = Query(1, ge=1, le=60, description="Historical lookback window in trading days"),
    rsi_length: int = Query(14, ge=2, le=100, description="RSI period length"),
    index: str | None = Query(None, description="Index or Watchlist filter"),
    signal_filter: str | None = Query(None, description="Filter: oversold, overbought, buy, sell, signals_only"),
    symbol: str | None = Query(None, description="Specific ticker search"),
    include_neutral: bool = Query(False, description="Include neutral unflagged stocks"),
    refresh: bool = Query(False, description="Force fresh market data download"),
) -> LookbackResponse:
    """Multi-condition lookback screener for RSI extremes and strategy signals."""
    try:
        return ScannerEngine.screen_lookback(
            lookback_days=lookback_days,
            rsi_length=rsi_length,
            index_filter=index,
            signal_filter=signal_filter,
            symbol=symbol,
            include_neutral=include_neutral,
            force_refresh=refresh,
        )
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
def trigger_scan_now(
    strategy: str = Query("RSI", description="Strategy to execute (RSI, RB_KnoxDiv, ALL)"),
) -> ScanResponse:
    """Manually trigger daily market scan and signal persistence."""
    try:
        return ScannerEngine.run_daily_scan(strategy_name=strategy)
    except Exception as exc:
        raise HTTPException(500, f"Scan execution failed: {exc}") from exc


@router.post("/watchlist/import", response_model=dict[str, Any])
def import_watchlist_endpoint(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Import a TradingView public watchlist via URL."""
    url = payload.get("url", "").strip()
    custom_name = payload.get("custom_name", None)
    if not url:
        raise HTTPException(400, "TradingView watchlist URL is required.")

    try:
        from services.universe import import_tradingview_watchlist
        res = import_tradingview_watchlist(url=url, custom_name=custom_name)
        return res
    except Exception as exc:
        raise HTTPException(400, f"Failed to import watchlist: {exc}") from exc


@router.get("/watchlist/list", response_model=dict[str, Any])
def list_watchlists_endpoint() -> dict[str, Any]:
    """Return all custom imported watchlists."""
    from services.universe import load_custom_watchlists
    return load_custom_watchlists()


@router.delete("/watchlist/{name}")
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




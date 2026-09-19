"""Backward-compatible facade for services.scanner."""
from services.scanner import ScannerEngine

def scan_lookback(
    lookback_days: int = 1,
    rsi_length: int = 14,
    index_filter: str | None = None,
    signal_filter: str | None = None,
    force_refresh: bool = False,
    user_id: int | None = None,
):
    res = ScannerEngine.screen_lookback(
        lookback_days=lookback_days,
        rsi_length=rsi_length,
        index_filter=index_filter,
        signal_filter=signal_filter,
        force_refresh=force_refresh,
        user_id=user_id,
    )
    return res.model_dump()

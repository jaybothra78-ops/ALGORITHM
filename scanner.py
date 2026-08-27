"""Backward-compatible facade for services.scanner."""
from services.scanner import ScannerEngine

def run_scan(strategy_name="RSI"):
    res = ScannerEngine.run_daily_scan(strategy_name)
    return res.model_dump()

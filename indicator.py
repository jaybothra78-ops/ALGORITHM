"""Backward-compatible facade for services.indicators."""
from services.indicators import (
    calculate_rsi,
    calculate_rsi_ma,
    rsi_signals,
    rb_knox_divergence,
)

class PineSourceRequiredError(RuntimeError):
    pass

"""Backward-compatible facade for services.market_data."""
from services.market_data import MarketDataProvider

def fetch_universe_ohlc(symbols, period="1y"):
    return MarketDataProvider.get_universe_ohlc(symbols)

def fetch_daily_ohlc(symbol, period="1y"):
    data = MarketDataProvider.get_universe_ohlc([symbol])
    return data.get(symbol)

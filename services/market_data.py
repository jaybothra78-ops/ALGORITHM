"""Market data provider with caching, ticker mapping, and data normalization."""
from __future__ import annotations

import time
from typing import Any
import pandas as pd
import yfinance as yf
from core.config import settings
from core.logging import logger


class MarketDataProvider:
    """Thread-safe cached provider for equity and futures OHLC market data."""

    _CACHE: dict[str, Any] = {
        "ohlc_data": {},
        "ohlc_timestamp": 0.0,
    }

    @staticmethod
    def normalize_ticker(symbol: str) -> str:
        """Convert exchange-prefixed or bare symbol to Yahoo Finance ticker format."""
        s = symbol.strip().upper()
        if s.startswith("BSE:"):
            return s.replace("BSE:", "") + ".BO"
        if s.startswith("NSE:"):
            return s.replace("NSE:", "") + ".NS"
        if s.endswith(".BO") or s.endswith(".NS"):
            return s
        return f"{s}.NS"

    @staticmethod
    def normalize_ohlc(data: pd.DataFrame, min_rows: int = settings.MIN_OHLC_ROWS) -> pd.DataFrame:
        """Validate and clean OHLC DataFrame."""
        if data.empty:
            raise ValueError("No data returned")

        if isinstance(data.columns, pd.MultiIndex):
            data = data.copy()
            data.columns = data.columns.get_level_values(0)

        def _get_col(name: str) -> pd.Series:
            if name not in data.columns:
                raise ValueError(f"Missing {name} column")
            col = data[name]
            if isinstance(col, pd.DataFrame):
                col = col.iloc[:, 0]
            return pd.to_numeric(pd.Series(col).squeeze(), errors="coerce")


        result = pd.DataFrame(
            {
                "Open": _get_col("Open"),
                "High": _get_col("High"),
                "Low": _get_col("Low"),
                "Close": _get_col("Close"),
            },
            index=pd.to_datetime(data.index).tz_localize(None),
        )
        result = result.dropna().sort_index()
        if len(result) < min_rows:
            raise ValueError(f"Only {len(result)} bars returned; minimum {min_rows} required")
        return result

    @classmethod
    def get_universe_ohlc(
        cls, symbols: list[str], force_refresh: bool = False
    ) -> dict[str, pd.DataFrame]:
        """Fetch or return cached OHLC history for the requested universe."""
        now = time.time()
        cached = cls._CACHE.get("ohlc_data", {})
        cache_time = cls._CACHE.get("ohlc_timestamp", 0.0)

        if not force_refresh and cached and (now - cache_time < settings.CACHE_TTL_SECONDS):
            return cached

        if not symbols:
            return {}

        ticker_map = {cls.normalize_ticker(s): s for s in symbols}
        tickers_list = list(ticker_map.keys())

        logger.info(f"Fetching fresh market data for {len(tickers_list)} tickers from Yahoo Finance...")
        raw_data = yf.download(
            tickers_list,
            period=settings.DATA_PERIOD,
            interval=settings.DATA_INTERVAL,
            auto_adjust=False,
            group_by="ticker",
            threads=True,
            progress=False,
        )

        result: dict[str, pd.DataFrame] = {}
        if isinstance(raw_data.columns, pd.MultiIndex):
            lvl0 = set(raw_data.columns.get_level_values(0))
            lvl1 = set(raw_data.columns.get_level_values(1))
            for ticker, sym in ticker_map.items():
                try:
                    if ticker in lvl0:
                        df = raw_data[ticker]
                    elif ticker in lvl1:
                        df = raw_data.xs(ticker, level=1, axis=1)
                    else:
                        continue
                    result[sym] = cls.normalize_ohlc(df)
                except Exception as exc:
                    logger.debug(f"Failed to normalize {sym}: {exc}")
                    continue
        else:
            if len(symbols) == 1:
                try:
                    result[symbols[0]] = cls.normalize_ohlc(raw_data)
                except Exception as exc:
                    logger.debug(f"Failed to normalize single symbol {symbols[0]}: {exc}")


        cls._CACHE["ohlc_data"] = result
        cls._CACHE["ohlc_timestamp"] = now
        logger.info(f"Market data cache updated with {len(result)} valid symbols.")
        return result

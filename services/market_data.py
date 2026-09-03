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

    INVALID_SYMBOLS: set[str] = {
        "NIFTY", "BANKNIFTY", "SENSEX", "INDIAVIX", "CNX500", "CNXMIDCAP", 
        "CNXSMALLCAP", "RUDRAECO", "RAJESH", "TATAMOTORS", "KUBERJI", "ASMTEC", 
        "GUJGASLTD", "ANTHEM", "ACUTAAS"
    }


    @classmethod
    def load_disk_cache(cls) -> bool:
        """Load OHLC cache from disk if available and fresh."""
        import pickle
        p = settings.DISK_CACHE_PATH
        if not p.exists():
            return False
        try:
            now = time.time()
            mtime = p.stat().st_mtime
            if now - mtime < settings.CACHE_TTL_SECONDS:
                with open(p, "rb") as f:
                    data = pickle.load(f)
                if isinstance(data, dict) and data:
                    cls._CACHE["ohlc_data"] = data
                    cls._CACHE["ohlc_timestamp"] = mtime
                    logger.info(f"Loaded {len(data)} cached symbols instantly from disk ({p.name}).")
                    return True
        except Exception as exc:
            logger.warning(f"Could not load disk cache: {exc}")
        return False

    @classmethod
    def save_disk_cache(cls, data: dict[str, pd.DataFrame]) -> None:
        """Save memory cache to disk atomically for instant restart recovery."""
        import os
        import pickle
        p = settings.DISK_CACHE_PATH
        tmp_path = p.with_suffix(".tmp")
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp_path, "wb") as f:
                pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp_path, p)
            logger.debug(f"Saved {len(data)} symbols atomically to disk cache at {p.name}.")
        except Exception as exc:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            logger.warning(f"Could not save disk cache: {exc}")


    PERIOD_MIN_BARS: dict[str, int] = {
        "1mo": 20,
        "3mo": 60,
        "6mo": 120,
        "1y": 240,
        "2y": 480,
        "3y": 720,
        "5y": 1200,
        "10y": 2400,
        "max": 2400,
    }

    @classmethod
    def get_universe_ohlc(
        cls, symbols: list[str], period: str = "1y", force_refresh: bool = False
    ) -> dict[str, pd.DataFrame]:
        """Fetch or return cached OHLC history for the requested universe and time period."""
        now = time.time()
        p_clean = period.lower().strip() or "1y"
        min_required_bars = cls.PERIOD_MIN_BARS.get(p_clean, 240)

        # Ensure disk cache is loaded if in-memory is empty
        if not cls._CACHE.get("ohlc_data"):
            cls.load_disk_cache()

        cached: dict[str, pd.DataFrame] = cls._CACHE.get("ohlc_data", {})

        # Check which requested symbols are missing from cache or need longer history
        if force_refresh:
            missing_symbols = [s for s in symbols if s.upper() not in cls.INVALID_SYMBOLS]
        else:
            missing_symbols = [
                s for s in symbols
                if s.upper() not in cls.INVALID_SYMBOLS and (s not in cached or cached[s].empty or len(cached[s]) < min_required_bars)
            ]

        # If all requested symbols are already cached with sufficient bars, return them
        if not missing_symbols and cached:
            if symbols:
                return {s: cached[s] for s in symbols if s in cached}
            return cached

        if not missing_symbols and not symbols:
            return cached

        valid_symbols = missing_symbols
        if not valid_symbols:
            return {s: cached[s] for s in symbols if s in cached}

        ticker_map = {cls.normalize_ticker(s): s for s in valid_symbols}
        tickers_list = list(ticker_map.keys())

        logger.info(f"Fetching market data for {len(tickers_list)} tickers ({p_clean} period) from Yahoo Finance...")
        try:
            raw_data = yf.download(
                tickers_list,
                period=p_clean if p_clean in cls.PERIOD_MIN_BARS else settings.DATA_PERIOD,
                interval=settings.DATA_INTERVAL,
                auto_adjust=False,
                group_by="ticker",
                threads=True,
                progress=False,
            )

            new_results: dict[str, pd.DataFrame] = {}
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
                        new_results[sym] = cls.normalize_ohlc(df)
                    except Exception as exc:
                        logger.debug(f"Failed to normalize {sym}: {exc}")
                        continue
            else:
                if len(valid_symbols) == 1:
                    try:
                        new_results[valid_symbols[0]] = cls.normalize_ohlc(raw_data)
                    except Exception as exc:
                        logger.debug(f"Failed to normalize single symbol {valid_symbols[0]}: {exc}")


            if "ohlc_data" not in cls._CACHE:
                cls._CACHE["ohlc_data"] = {}
            cls._CACHE["ohlc_data"].update(new_results)
            cls._CACHE["ohlc_timestamp"] = now
            cls.save_disk_cache(cls._CACHE["ohlc_data"])
            logger.info(f"Market data cache updated with {len(new_results)} new symbols (total {len(cls._CACHE['ohlc_data'])}).")
        except Exception as exc:
            logger.error(f"Failed to download OHLC data: {exc}")

        cached = cls._CACHE.get("ohlc_data", {})
        if symbols:
            return {s: cached[s] for s in symbols if s in cached}
        return cached



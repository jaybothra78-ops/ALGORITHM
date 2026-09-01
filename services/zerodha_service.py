"""Zerodha Kite Connect & Enctoken live options quote provider."""
from __future__ import annotations

import os
import time
from typing import Any
import requests
from core.logging import logger

try:
    from kiteconnect import KiteConnect
except ImportError:
    KiteConnect = None


class ZerodhaService:
    """Live quote engine connecting directly to Zerodha Kite."""

    _instance: ZerodhaService | None = None
    _kite_client: Any = None
    _enctoken: str | None = None
    _user_id: str | None = None

    @classmethod
    def get_instance(cls) -> ZerodhaService:
        if cls._instance is None:
            cls._instance = ZerodhaService()
            cls._instance.initialize()
        return cls._instance

    def initialize(self) -> None:
        """Initialize Kite SDK or Web Enctoken from environment or config."""
        self._enctoken = os.getenv("ZERODHA_ENCTOKEN") or os.getenv("KITE_ENCTOKEN")
        self._user_id = os.getenv("ZERODHA_USER_ID") or os.getenv("KITE_USER_ID")

        api_key = os.getenv("KITE_API_KEY")
        access_token = os.getenv("KITE_ACCESS_TOKEN")

        if api_key and access_token and KiteConnect:
            try:
                self._kite_client = KiteConnect(api_key=api_key)
                self._kite_client.set_access_token(access_token)
                logger.info("Zerodha KiteConnect client initialized successfully.")
            except Exception as e:
                logger.warning(f"Failed to initialize KiteConnect: {e}")

    @property
    def is_connected(self) -> bool:
        """Check if any valid Zerodha connection method is available."""
        return bool(self._kite_client or (self._enctoken and self._user_id))

    def get_tradingsymbol(self, symbol: str, strike: float, option_type: str, expiry_date_str: str | None = None) -> str:
        """
        Generate official NSE/NFO trading symbol (e.g. NIFTY24SEP25000CE or BOSCHLTD24SEP44000PE).
        """
        from datetime import datetime
        clean_sym = symbol.strip().upper()
        opt = option_type.strip().upper()
        strike_int = int(strike) if strike.is_integer() else int(round(strike))

        if expiry_date_str:
            try:
                exp_dt = datetime.strptime(expiry_date_str.strip(), "%Y-%m-%d")
                year_short = exp_dt.strftime("%y")
                month_code = exp_dt.strftime("%b").upper()
                return f"{clean_sym}{year_short}{month_code}{strike_int}{opt}"
            except Exception:
                pass

        now = datetime.now()
        year_short = now.strftime("%y")
        month_code = now.strftime("%b").upper()
        return f"{clean_sym}{year_short}{month_code}{strike_int}{opt}"

    def get_live_option_quote(
        self,
        symbol: str,
        strike: float,
        option_type: str,
        expiry_date_str: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Fetch real-time option LTP, bid, ask, and volume from Zerodha.
        Returns None if not connected or symbol not found.
        """
        tradingsymbol = self.get_tradingsymbol(symbol, strike, option_type, expiry_date_str)
        nfo_instrument = f"NFO:{tradingsymbol}"

        # 1. Try KiteConnect SDK
        if self._kite_client:
            try:
                quotes = self._kite_client.quote([nfo_instrument])
                if nfo_instrument in quotes:
                    q = quotes[nfo_instrument]
                    return {
                        "source": "Zerodha KiteConnect",
                        "tradingsymbol": tradingsymbol,
                        "instrument": nfo_instrument,
                        "ltp": float(q.get("last_price", 0.0)),
                        "open": float(q.get("ohlc", {}).get("open", 0.0)),
                        "high": float(q.get("ohlc", {}).get("high", 0.0)),
                        "low": float(q.get("ohlc", {}).get("low", 0.0)),
                        "close": float(q.get("ohlc", {}).get("close", 0.0)),
                        "volume": int(q.get("volume", 0)),
                        "oi": int(q.get("oi", 0)),
                        "buy_quantity": int(q.get("buy_quantity", 0)),
                        "sell_quantity": int(q.get("sell_quantity", 0)),
                        "timestamp": time.time(),
                    }
            except Exception as e:
                logger.warning(f"KiteConnect quote fetch failed for {nfo_instrument}: {e}")

        # 2. Try Enctoken Session
        if self._enctoken and self._user_id:
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Authorization": f"enctoken {self._enctoken}",
                }
                url = f"https://kite.zerodha.com/oms/quote/ltp?i={nfo_instrument}"
                resp = requests.get(url, headers=headers, timeout=4)
                if resp.status_code == 200:
                    data = resp.json().get("data", {})
                    if nfo_instrument in data:
                        item = data[nfo_instrument]
                        return {
                            "source": "Zerodha Live Web Feed",
                            "tradingsymbol": tradingsymbol,
                            "instrument": nfo_instrument,
                            "ltp": float(item.get("last_price", 0.0)),
                            "instrument_token": item.get("instrument_token"),
                            "timestamp": time.time(),
                        }
            except Exception as e:
                logger.warning(f"Zerodha enctoken quote fetch failed: {e}")

        return None

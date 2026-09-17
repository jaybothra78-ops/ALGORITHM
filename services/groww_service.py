"""Groww live options chain and real-time market data service."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
import requests
from core.logging import logger


class GrowwOptionsService:
    """Fetches real-time NSE/BSE options chains, live Greeks, and exchange expiry calendars from Groww."""

    _instance: GrowwOptionsService | None = None
    _HEADERS: dict[str, str] = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }
    _SLUG_CACHE: dict[str, str] = {
        "NIFTY": "nifty",
        "NIFTY50": "nifty",
        "BANKNIFTY": "nifty-bank",
        "FINNIFTY": "nifty-financial-services",
        "MIDCPNIFTY": "nifty-midcap-select",
        "SENSEX": "bse-sensex",
    }
    _CHAIN_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
    _CHAIN_TTL: float = 15.0  # 15-second TTL cache for high performance

    @classmethod
    def get_instance(cls) -> GrowwOptionsService:
        if cls._instance is None:
            cls._instance = GrowwOptionsService()
            cls._instance._load_slugs()
        return cls._instance

    def _load_slugs(self) -> None:
        """Load pre-compiled universe F&O slugs from config/groww_fno_slugs.json."""
        import json
        from pathlib import Path
        slug_file = Path("config/groww_fno_slugs.json")
        if slug_file.exists():
            try:
                data = json.loads(slug_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._SLUG_CACHE.update(data)
                    logger.debug(f"Loaded {len(data)} pre-resolved F&O stock slugs from {slug_file}")
            except Exception as e:
                logger.warning(f"Failed to load {slug_file}: {e}")

    def get_slug(self, symbol: str) -> str:
        """Resolve NSE ticker symbol to Groww derivatives slug."""
        clean_sym = symbol.strip().upper()
        if clean_sym in self._SLUG_CACHE:
            return self._SLUG_CACHE[clean_sym]

        try:
            url = f"https://groww.in/v1/api/search/v1/entity?app=false&entity_type=Stocks&query={clean_sym}"
            resp = requests.get(url, headers=self._HEADERS, timeout=4)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("content", []):
                    if item.get("nse_scrip_code") == clean_sym or item.get("search_id") == clean_sym.lower():
                        slug = item.get("search_id")
                        self._SLUG_CACHE[clean_sym] = slug
                        self._persist_slug(clean_sym, slug)
                        return slug
                if data.get("content"):
                    slug = data["content"][0].get("search_id")
                    if slug:
                        self._SLUG_CACHE[clean_sym] = slug
                        self._persist_slug(clean_sym, slug)
                        return slug
        except Exception as exc:
            logger.debug(f"Groww search error for {clean_sym}: {exc}")

        slug = clean_sym.lower()
        self._SLUG_CACHE[clean_sym] = slug
        return slug

    def _persist_slug(self, symbol: str, slug: str) -> None:
        """Persist dynamically discovered slug to disk."""
        import json
        from pathlib import Path
        try:
            slug_file = Path("config/groww_fno_slugs.json")
            data = {}
            if slug_file.exists():
                data = json.loads(slug_file.read_text(encoding="utf-8"))
            data[symbol] = slug
            slug_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def fetch_option_chain_raw(self, symbol: str, expiry: str | None = None) -> dict[str, Any] | None:
        """Fetch raw JSON option chain from Groww with 15-second TTL cache."""
        clean_sym = symbol.strip().upper()
        cache_key = f"{clean_sym}:{expiry or 'default'}"
        now = time.time()

        if cache_key in self._CHAIN_CACHE:
            cached_time, cached_data = self._CHAIN_CACHE[cache_key]
            if now - cached_time < self._CHAIN_TTL:
                return cached_data

        slug = self.get_slug(clean_sym)
        url = f"https://groww.in/v1/api/option_chain_service/v1/option_chain/derivatives/{slug}"
        if expiry:
            url += f"?expiry={expiry}"

        try:
            resp = requests.get(url, headers=self._HEADERS, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                self._CHAIN_CACHE[cache_key] = (now, data)
                return data
        except Exception as exc:
            logger.warning(f"Groww option chain fetch failed for {clean_sym} ({url}): {exc}")

        return None

    def get_expiry_calendar(self, symbol: str) -> list[dict[str, Any]] | None:
        """Fetch exact real-world exchange expiry dates and remaining DTE for any symbol."""
        data = self.fetch_option_chain_raw(symbol)
        if not data:
            return None

        oc = data.get("optionChain", {})
        exp_dto = oc.get("expiryDetailsDto", {})
        expiry_dates: list[str] = exp_dto.get("expiryDates", [])
        if not expiry_dates:
            return None

        current_expiry = exp_dto.get("currentExpiry")
        today = datetime.now(timezone.utc).date()
        expiries: list[dict[str, Any]] = []

        for idx, date_str in enumerate(expiry_dates):
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d").date()
                diff_days = (dt - today).days
                dte = max(0.5, float(diff_days))

                is_curr = (date_str == current_expiry) or (idx == 0)
                tag = "Current Weekly" if idx == 0 else ("Next Weekly" if idx == 1 else ("Monthly" if dte > 20 else "Weekly"))
                label = f"{dt.strftime('%d %b %Y')} ({int(dte)}d - {tag})"

                expiries.append({
                    "label": label,
                    "date": date_str,
                    "days_to_expiry": dte,
                    "type": tag,
                    "is_current": is_curr,
                })
            except Exception:
                continue

        return expiries if expiries else None

    def get_option_strikes(self, symbol: str, spot_price: float, expiry_date_str: str | None = None) -> dict[str, Any] | None:
        """
        Generate live strike ladder from real exchange options feed.
        Includes real CE & PE market LTPs, open interest, and lot size.
        """
        clean_sym = symbol.strip().upper()
        data = self.fetch_option_chain_raw(clean_sym, expiry=expiry_date_str)
        if not data:
            return None

        oc = data.get("optionChain", {})
        chains = oc.get("optionChains", [])
        if not chains:
            return None

        exp_dto = oc.get("expiryDetailsDto", {})
        live_price_data = data.get("livePrice", {})
        actual_spot = float(live_price_data.get("value") or spot_price)
        lot_size = int(exp_dto.get("expiryLotSize") or 50)

        parsed_strikes: list[dict[str, Any]] = []
        for item in chains:
            ce = item.get("callOption") or {}
            pe = item.get("putOption") or {}
            raw_s = ce.get("strikePrice") or pe.get("strikePrice") or 0
            strike = float(raw_s / 100.0 if raw_s > 100000 else raw_s)
            if strike <= 0:
                continue

            ce_ltp = round(float(ce.get("ltp") or 0.0), 2)
            pe_ltp = round(float(pe.get("ltp") or 0.0), 2)
            ce_oi = int(ce.get("openInterest") or 0)
            pe_oi = int(pe.get("openInterest") or 0)
            ce_vol = int(ce.get("volume") or 0)
            pe_vol = int(pe.get("volume") or 0)

            parsed_strikes.append({
                "strike": strike,
                "ce_premium": ce_ltp,
                "pe_premium": pe_ltp,
                "ce_oi": ce_oi,
                "pe_oi": pe_oi,
                "ce_vol": ce_vol,
                "pe_vol": pe_vol,
                "ce_contract": ce.get("growwContractId"),
                "pe_contract": pe.get("growwContractId"),
            })

        if not parsed_strikes:
            return None

        parsed_strikes.sort(key=lambda s: s["strike"])

        closest_strike = min(parsed_strikes, key=lambda s: abs(s["strike"] - actual_spot))
        atm_strike = closest_strike["strike"]

        atm_idx = parsed_strikes.index(closest_strike)
        start_idx = max(0, atm_idx - 8)
        end_idx = min(len(parsed_strikes), atm_idx + 9)
        ladder = parsed_strikes[start_idx:end_idx]

        ladder_result = []
        for s in ladder:
            is_atm = (s["strike"] == atm_strike)
            ce_tag = "ATM" if is_atm else ("ITM" if s["strike"] < actual_spot else "OTM")
            pe_tag = "ATM" if is_atm else ("ITM" if s["strike"] > actual_spot else "OTM")

            ladder_result.append({
                "strike": s["strike"],
                "ce_premium": s["ce_premium"],
                "pe_premium": s["pe_premium"],
                "ce_tag": ce_tag,
                "pe_tag": pe_tag,
                "is_atm": is_atm,
                "ce_oi": s["ce_oi"],
                "pe_oi": s["pe_oi"],
            })

        expiries = self.get_expiry_calendar(clean_sym) or []

        return {
            "symbol": clean_sym,
            "spot_price": actual_spot,
            "atm_strike": atm_strike,
            "lot_size": lot_size,
            "expiries": expiries,
            "strikes": ladder_result,
            "source": "Groww Live Options Feed",
        }

    def get_live_option_quote(
        self,
        symbol: str,
        strike: float,
        option_type: str,
        expiry_date_str: str | None = None,
    ) -> dict[str, Any] | None:
        """Fetch real-time option LTP, bid, ask, and volume for a specific strike from Groww."""
        clean_sym = symbol.strip().upper()
        opt_type = option_type.strip().upper()
        data = self.fetch_option_chain_raw(clean_sym, expiry=expiry_date_str)
        if not data:
            return None

        oc = data.get("optionChain", {})
        chains = oc.get("optionChains", [])
        if not chains:
            return None

        exp_dto = oc.get("expiryDetailsDto", {})
        live_price_data = data.get("livePrice", {})
        spot = float(live_price_data.get("value") or 0.0)
        lot_size = int(exp_dto.get("expiryLotSize") or 50)

        for item in chains:
            opt = item.get("callOption" if opt_type == "CE" else "putOption") or {}
            raw_s = opt.get("strikePrice", 0)
            s = float(raw_s / 100.0 if raw_s > 100000 else raw_s)

            if abs(s - strike) < 0.01:
                ltp = float(opt.get("ltp") or 0.0)
                if ltp > 0:
                    return {
                        "source": "Groww Live Market Feed",
                        "tradingsymbol": opt.get("growwContractId") or f"{clean_sym} {int(strike)} {opt_type}",
                        "ltp": round(ltp, 2),
                        "open": round(float(opt.get("open") or 0.0), 2),
                        "high": round(float(opt.get("high") or 0.0), 2),
                        "low": round(float(opt.get("low") or 0.0), 2),
                        "close": round(float(opt.get("close") or 0.0), 2),
                        "volume": int(opt.get("volume") or 0),
                        "oi": int(opt.get("openInterest") or 0),
                        "lot_size": lot_size,
                        "spot_price": spot,
                        "timestamp": time.time(),
                    }

        return None

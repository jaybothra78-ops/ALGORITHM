"""Options pricing and derivatives analytics engine for NSE/BSE markets."""
from __future__ import annotations

import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any


class OptionsPricingService:
    """Institutional Black-Scholes-Merton (BSM) Options Pricing Engine."""

    # Standard NSE Lot Sizes
    LOT_SIZES: dict[str, int] = {
        "NIFTY": 25,
        "BANKNIFTY": 15,
        "FINNIFTY": 25,
        "MIDCPNIFTY": 50,
        "SENSEX": 10,
        "BANKEX": 15,
        "RELIANCE": 250,
        "TCS": 175,
        "INFY": 400,
        "HDFCBANK": 550,
        "ICICIBANK": 700,
        "SBIN": 750,
        "BHARTIARTL": 475,
        "ITC": 1600,
        "KOTAKBANK": 400,
        "LT": 175,
        "AXISBANK": 625,
        "TVSMOTOR": 175,
        "TRENT": 100,
        "TATAMOTORS": 700,
        "BAJFINANCE": 125,
        "MARUTI": 50,
        "SUNPHARMA": 350,
        "TITAN": 175,
        "ASIANPAINT": 200,
        "HCLTECH": 350,
        "WIPRO": 1500,
        "M&M": 200,
        "NTPC": 1500,
        "POWERGRID": 1800,
        "ULTRACEMCO": 100,
        "COALINDIA": 2100,
        "TATASTEEL": 5500,
        "INDUSINDBK": 500,
        "IDFCFIRSTB": 7500,
        "BOSCHLTD": 25,
        "MRF": 10,
        "PAGEIND": 15,
        "BAJAJ-AUTO": 125,
        "HEROMOTOCO": 150,
        "EICHERMOT": 175,
        "PFC": 1300,
        "RECLTD": 1500,
        "HAL": 150,
        "BEL": 2850,
        "DLF": 825,
        "VEDL": 1150,
        "ADANIENT": 300,
        "ADANIPORTS": 400,
        "NESTLEIND": 25,
    }

    # Standard Strike Step Sizes
    STRIKE_STEPS: dict[str, float] = {
        "NIFTY": 50.0,
        "BANKNIFTY": 100.0,
        "FINNIFTY": 50.0,
        "MIDCPNIFTY": 25.0,
        "SENSEX": 100.0,
        "BANKEX": 100.0,
        "BOSCHLTD": 200.0,
        "MRF": 500.0,
    }

    @classmethod
    def get_lot_size(cls, symbol: str, spot_price: float = 0.0) -> int:
        clean_sym = symbol.strip().upper()
        if clean_sym in cls.LOT_SIZES:
            return cls.LOT_SIZES[clean_sym]
        
        # Dynamic lot sizing based on spot price for unlisted F&O stocks
        if spot_price >= 30000:
            return 25
        elif spot_price >= 10000:
            return 50
        elif spot_price >= 3000:
            return 125
        elif spot_price >= 1000:
            return 250
        elif spot_price >= 500:
            return 500
        else:
            return 1000


    @classmethod
    def get_strike_step(cls, symbol: str, spot_price: float) -> float:
        clean_sym = symbol.strip().upper()
        if clean_sym in cls.STRIKE_STEPS:
            return cls.STRIKE_STEPS[clean_sym]
        
        # Dynamic step size based on spot price for stocks
        if spot_price < 200:
            return 5.0
        elif spot_price < 500:
            return 10.0
        elif spot_price < 1000:
            return 20.0
        elif spot_price < 2500:
            return 50.0
        elif spot_price < 5000:
            return 100.0
        else:
            return 200.0

    @classmethod
    def get_asset_iv(cls, symbol: str) -> float:
        """Return calibrated baseline implied volatility for NSE index or stock."""
        clean_sym = symbol.strip().upper()
        if clean_sym in ["NIFTY", "NIFTY50", "SENSEX"]:
            return 0.135
        elif clean_sym in ["BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "BANKEX"]:
            return 0.155
        elif clean_sym in ["ITC", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "BHARTIARTL", "LT", "KOTAKBANK"]:
            return 0.22
        elif clean_sym in ["BOSCHLTD", "MARUTI", "BAJAJ-AUTO", "HEROMOTOCO", "EICHERMOT"]:
            return 0.29
        elif clean_sym in ["TVSMOTOR", "TRENT", "TATAMOTORS", "BAJFINANCE", "PFC", "IDFCFIRSTB", "COALINDIA", "TATASTEEL", "ADANIENT"]:
            return 0.33
        else:
            return 0.28

    @staticmethod
    def _norm_cdf(x: float) -> float:
        """Standard cumulative normal distribution function."""
        return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0

    @staticmethod
    def _norm_pdf(x: float) -> float:
        """Standard normal probability density function."""
        return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)

    @classmethod
    def calculate_bsm_price(
        cls,
        spot: float,
        strike: float,
        days_to_expiry: float,
        symbol: str = "NIFTY",
        iv: float | None = None,
        r: float = 0.065,
        option_type: str = "CE",
    ) -> dict[str, Any]:
        """
        Compute Black-Scholes-Merton theoretical option premium, Greeks, and volatility skew.
        option_type: 'CE' (Call) or 'PE' (Put)
        """
        opt_type = option_type.strip().upper()
        T = max(days_to_expiry, 0.25) / 365.0
        r_rate = max(r, 0.01)

        base_iv = iv if (iv is not None and iv > 0) else cls.get_asset_iv(symbol)
        
        # Volatility smile / skew factor based on moneyness ln(K / S)
        moneyness = math.log(max(strike, 0.01) / max(spot, 0.01))
        
        # Asymmetric put/call skew (OTM Puts have elevated downside crash risk in Indian F&O)
        if opt_type == "PE" and strike < spot:
            skew_adjust = 0.35 * (moneyness ** 2) - 0.25 * moneyness
        elif opt_type == "CE" and strike > spot:
            skew_adjust = 0.20 * (moneyness ** 2) + 0.05 * moneyness
        else:
            skew_adjust = 0.15 * (moneyness ** 2)

        sigma = max(base_iv * (1.0 + skew_adjust), 0.08)


        # In case of immediate expiry
        if T <= 0.001:
            intrinsic = max(0.0, spot - strike) if opt_type == "CE" else max(0.0, strike - spot)
            return {
                "premium": round(intrinsic, 2),
                "intrinsic": round(intrinsic, 2),
                "time_value": 0.0,
                "delta": 1.0 if opt_type == "CE" and spot > strike else (-1.0 if opt_type == "PE" and spot < strike else 0.0),
                "theta": 0.0,
                "gamma": 0.0,
                "vega": 0.0,
                "iv": round(sigma * 100, 1),
            }

        d1 = (math.log(max(spot, 0.01) / max(strike, 0.01)) + (r_rate + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)

        if opt_type == "CE":
            price = spot * cls._norm_cdf(d1) - strike * math.exp(-r_rate * T) * cls._norm_cdf(d2)
            delta = cls._norm_cdf(d1)
            intrinsic = max(0.0, spot - strike)
        else:
            price = strike * math.exp(-r_rate * T) * cls._norm_cdf(-d2) - spot * cls._norm_cdf(-d1)
            delta = cls._norm_cdf(d1) - 1.0
            intrinsic = max(0.0, strike - spot)

        # Clean pricing bounds
        price = max(price, intrinsic, 0.05)
        time_value = max(0.0, price - intrinsic)

        # Greeks
        gamma = cls._norm_pdf(d1) / (spot * sigma * math.sqrt(T))
        vega = spot * math.sqrt(T) * cls._norm_pdf(d1) * 0.01
        
        # 1-day theta decay
        theta_part1 = -(spot * cls._norm_pdf(d1) * sigma) / (2.0 * math.sqrt(T))
        if opt_type == "CE":
            theta_part2 = -r_rate * strike * math.exp(-r_rate * T) * cls._norm_cdf(d2)
        else:
            theta_part2 = r_rate * strike * math.exp(-r_rate * T) * cls._norm_cdf(-d2)
        theta_daily = (theta_part1 + theta_part2) / 365.0

        return {
            "premium": round(price, 2),
            "intrinsic": round(intrinsic, 2),
            "time_value": round(time_value, 2),
            "delta": round(delta, 3),
            "theta": round(theta_daily, 2),
            "gamma": round(gamma, 5),
            "vega": round(vega, 2),
            "iv": round(sigma * 100, 1),
        }

    @classmethod
    def get_expiry_calendar_for_symbol(cls, symbol: str) -> list[dict[str, Any]]:
        """
        Generate exact NSE expiry dates based on Indian market regulations:
        - Indices (NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, SENSEX): Weekly expiries on specific weekday.
        - F&O Equities (RELIANCE, TVSMOTOR, ITC, PFC, etc.): Monthly expiries (Last Thursday of Current, Next, Far month).
        """
        clean_sym = symbol.strip().upper()
        today = datetime.now(timezone.utc).date()
        expiries = []

        is_stock = clean_sym not in ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX", "NIFTY50"]

        if not is_stock:
            # Determine specific weekly expiry weekday:
            # NIFTY: Thursday (3), BANKNIFTY: Wednesday (2), FINNIFTY: Tuesday (1), MIDCPNIFTY: Monday (0), SENSEX: Friday (4)
            if clean_sym in ["NIFTY", "NIFTY50"]:
                target_weekday = 3
            elif clean_sym == "BANKNIFTY":
                target_weekday = 2
            elif clean_sym == "FINNIFTY":
                target_weekday = 1
            elif clean_sym == "MIDCPNIFTY":
                target_weekday = 0
            else:
                target_weekday = 4

            curr = today
            while len(expiries) < 4:
                days_ahead = (target_weekday - curr.weekday() + 7) % 7
                exp_date = curr if days_ahead == 0 else curr + timedelta(days=days_ahead)
                dte = max(0.5, float((exp_date - today).days))
                
                tag = "Current Weekly" if len(expiries) == 0 else "Next Weekly"
                label = f"{exp_date.strftime('%d %b %Y')} ({int(dte)}d - {tag})"
                
                expiries.append({
                    "label": label,
                    "date": exp_date.strftime("%Y-%m-%d"),
                    "days_to_expiry": dte,
                    "type": "Weekly",
                    "is_current": len(expiries) == 0,
                })
                curr = exp_date + timedelta(days=1)
        else:
            # Equities / Stocks: Exactly Current Month Last Thursday, Next Month Last Thursday, Far Month
            for month_offset in range(3):
                y = today.year + (today.month + month_offset - 1) // 12
                m = (today.month + month_offset - 1) % 12 + 1
                next_m_first = datetime(y + 1, 1, 1).date() if m == 12 else datetime(y, m + 1, 1).date()
                last_day = next_m_first - timedelta(days=1)
                days_back = (last_day.weekday() - 3 + 7) % 7
                last_thursday = last_day - timedelta(days=days_back)
                
                if last_thursday >= today:
                    dte = max(0.5, float((last_thursday - today).days))
                    tag = "Current Monthly" if month_offset == 0 else ("Next Month" if month_offset == 1 else "Far Month")
                    label = f"{last_thursday.strftime('%d %b %Y')} ({int(dte)}d - {tag})"
                    
                    expiries.append({
                        "label": label,
                        "date": last_thursday.strftime("%Y-%m-%d"),
                        "days_to_expiry": dte,
                        "type": tag,
                        "is_current": len(expiries) == 0,
                    })

        return expiries

    @classmethod
    def calculate_days_to_expiry(cls, expiry_date_str: str | None, symbol: str = "NIFTY") -> float:
        """Parse expiry date string (YYYY-MM-DD) and return fractional days remaining."""
        if not expiry_date_str:
            # Use default first expiry for the symbol
            expiries = cls.get_expiry_calendar_for_symbol(symbol)
            return expiries[0]["days_to_expiry"] if expiries else 3.0

        try:
            exp_date = datetime.strptime(expiry_date_str.strip(), "%Y-%m-%d").date()
            today = datetime.now(timezone.utc).date()
            diff_days = (exp_date - today).days
            return max(0.5, float(diff_days))
        except Exception:
            return 3.0

    @classmethod
    def get_option_strikes(
        cls,
        symbol: str,
        spot_price: float,
        expiry_date_str: str | None = None,
    ) -> dict[str, Any]:
        """Generate standard ATM, ITM, and OTM strike ladder around spot price with accurate DTE."""
        clean_sym = symbol.strip().upper()
        step = cls.get_strike_step(clean_sym, spot_price)
        lot_size = cls.get_lot_size(clean_sym)
        expiries = cls.get_expiry_calendar_for_symbol(clean_sym)

        # Determine effective days to expiry from selected or nearest expiry
        if expiry_date_str:
            days_to_expiry = cls.calculate_days_to_expiry(expiry_date_str, clean_sym)
        elif expiries:
            days_to_expiry = expiries[0]["days_to_expiry"]
        else:
            days_to_expiry = 3.0

        # Calculate nearest round ATM strike
        atm_strike = round(spot_price / step) * step

        strikes = []
        # Generate 11 strikes (-5 to +5 around ATM)
        for offset in range(-5, 6):
            strike = round(atm_strike + (offset * step), 2)
            ce_calc = cls.calculate_bsm_price(spot_price, strike, days_to_expiry, symbol=clean_sym, option_type="CE")
            pe_calc = cls.calculate_bsm_price(spot_price, strike, days_to_expiry, symbol=clean_sym, option_type="PE")

            tag = "ATM" if offset == 0 else (f"ITM {abs(offset)}" if offset < 0 else f"OTM +{offset}")
            pe_tag = "ATM" if offset == 0 else (f"OTM +{abs(offset)}" if offset < 0 else f"ITM {offset}")

            strikes.append({
                "strike": strike,
                "is_atm": offset == 0,
                "ce_tag": tag,
                "pe_tag": pe_tag,
                "ce_premium": ce_calc["premium"],
                "ce_delta": ce_calc["delta"],
                "pe_premium": pe_calc["premium"],
                "pe_delta": pe_calc["delta"],
            })

        return {
            "symbol": clean_sym,
            "spot_price": spot_price,
            "atm_strike": atm_strike,
            "strike_step": step,
            "lot_size": lot_size,
            "days_to_expiry": days_to_expiry,
            "strikes": strikes,
            "expiries": expiries,
        }


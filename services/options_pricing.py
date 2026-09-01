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
    }

    # Standard Strike Step Sizes
    STRIKE_STEPS: dict[str, float] = {
        "NIFTY": 50.0,
        "BANKNIFTY": 100.0,
        "FINNIFTY": 50.0,
        "MIDCPNIFTY": 25.0,
        "SENSEX": 100.0,
        "BANKEX": 100.0,
    }

    @classmethod
    def get_lot_size(cls, symbol: str) -> int:
        clean_sym = symbol.strip().upper()
        return cls.LOT_SIZES.get(clean_sym, 100)

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
        iv: float = 0.18,
        r: float = 0.065,
        option_type: str = "CE",
    ) -> dict[str, Any]:
        """
        Compute Black-Scholes-Merton theoretical option premium and Greeks.
        option_type: 'CE' (Call) or 'PE' (Put)
        """
        opt_type = option_type.strip().upper()
        T = max(days_to_expiry, 0.2) / 365.0
        sigma = max(iv, 0.05)
        r_rate = max(r, 0.01)

        # In case of immediate expiry
        if T <= 0:
            intrinsic = max(0.0, spot - strike) if opt_type == "CE" else max(0.0, strike - spot)
            return {
                "premium": round(intrinsic, 2),
                "intrinsic": round(intrinsic, 2),
                "time_value": 0.0,
                "delta": 1.0 if opt_type == "CE" and spot > strike else ( -1.0 if opt_type == "PE" and spot < strike else 0.0 ),
                "theta": 0.0,
                "gamma": 0.0,
                "vega": 0.0,
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
        }

    @classmethod
    def get_expiry_calendar(cls) -> list[dict[str, Any]]:
        """Generate near-term NSE weekly and monthly Thursday expiry dates."""
        today = datetime.now(timezone.utc).date()
        expiries = []

        # Find upcoming Thursdays
        days_ahead = (3 - today.weekday() + 7) % 7
        if days_ahead == 0:
            # If today is Thursday, check time or count as today
            first_thursday = today
        else:
            first_thursday = today + timedelta(days=days_ahead)

        expiries.append({
            "label": f"Weekly Expiry ({first_thursday.strftime('%d %b %Y')})",
            "date": first_thursday.strftime("%Y-%m-%d"),
            "days_to_expiry": max(1, (first_thursday - today).days),
            "is_current": True,
        })

        second_thursday = first_thursday + timedelta(days=7)
        expiries.append({
            "label": f"Next Week ({second_thursday.strftime('%d %b %Y')})",
            "date": second_thursday.strftime("%Y-%m-%d"),
            "days_to_expiry": max(8, (second_thursday - today).days),
            "is_current": False,
        })

        # Monthly expiry (approx 30 days)
        monthly_date = today + timedelta(days=28)
        monthly_thursday = monthly_date + timedelta(days=((3 - monthly_date.weekday() + 7) % 7))
        expiries.append({
            "label": f"Monthly Expiry ({monthly_thursday.strftime('%d %b %Y')})",
            "date": monthly_thursday.strftime("%Y-%m-%d"),
            "days_to_expiry": max(20, (monthly_thursday - today).days),
            "is_current": False,
        })

        return expiries

    @classmethod
    def get_option_strikes(cls, symbol: str, spot_price: float, days_to_expiry: float = 3.0) -> dict[str, Any]:
        """Generate standard ATM, ITM, and OTM strike ladder around spot price."""
        clean_sym = symbol.strip().upper()
        step = cls.get_strike_step(clean_sym, spot_price)
        lot_size = cls.get_lot_size(clean_sym)

        # Calculate nearest round ATM strike
        atm_strike = round(spot_price / step) * step

        strikes = []
        # Generate 11 strikes (-5 to +5 around ATM)
        for offset in range(-5, 6):
            strike = round(atm_strike + (offset * step), 2)
            ce_calc = cls.calculate_bsm_price(spot_price, strike, days_to_expiry, option_type="CE")
            pe_calc = cls.calculate_bsm_price(spot_price, strike, days_to_expiry, option_type="PE")

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
            "strikes": strikes,
            "expiries": cls.get_expiry_calendar(),
        }

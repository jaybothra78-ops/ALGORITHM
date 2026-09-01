"""Institutional Black-Scholes-Merton (BSM) Options Pricing and Derivatives Engine for NSE/BSE markets."""
from __future__ import annotations

import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any


# =====================================================================
# 1. Analytic Black-Scholes Mathematical Kernel
# =====================================================================
class BlackScholesPricer:
    """Pure mathematical Black-Scholes-Merton valuation kernel with closed-form Greeks."""

    @staticmethod
    def norm_cdf(x: float) -> float:
        """Standard cumulative normal distribution function N(x)."""
        return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0

    @staticmethod
    def norm_pdf(x: float) -> float:
        """Standard normal probability density function N'(x)."""
        return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)

    @classmethod
    def price_and_greeks(
        cls,
        spot: float,
        strike: float,
        time_to_expiry_years: float,
        volatility: float,
        risk_free_rate: float = 0.065,
        option_type: str = "CE",
    ) -> dict[str, Any]:
        """
        Calculate theoretical option premium and analytical Greeks.
        
        Parameters:
            spot: Current underlying asset price (S)
            strike: Option strike price (K)
            time_to_expiry_years: Time remaining until expiration in years (T)
            volatility: Annualized implied volatility (sigma)
            risk_free_rate: Annualized risk-free interest rate (r)
            option_type: 'CE' (Call) or 'PE' (Put)
        """
        opt_type = option_type.strip().upper()
        S = max(float(spot), 0.01)
        K = max(float(strike), 0.01)
        T = max(float(time_to_expiry_years), 0.0001)
        sigma = max(float(volatility), 0.01)
        r = max(float(risk_free_rate), 0.001)

        # Intrinsic value bounds
        if opt_type == "CE":
            intrinsic = max(0.0, S - K)
        else:
            intrinsic = max(0.0, K - S)

        # Near-zero time to expiry edge case
        if T <= 0.0005:
            return {
                "premium": round(intrinsic, 2),
                "intrinsic": round(intrinsic, 2),
                "time_value": 0.0,
                "delta": 1.0 if (opt_type == "CE" and S > K) else (-1.0 if (opt_type == "PE" and S < K) else 0.0),
                "theta": 0.0,
                "gamma": 0.0,
                "vega": 0.0,
                "rho": 0.0,
                "iv": round(sigma * 100, 1),
            }

        # BSM d1 and d2 calculations
        sqrt_T = math.sqrt(T)
        d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrt_T)
        d2 = d1 - sigma * sqrt_T

        exp_rT = math.exp(-r * T)
        pdf_d1 = cls.norm_pdf(d1)

        if opt_type == "CE":
            price = S * cls.norm_cdf(d1) - K * exp_rT * cls.norm_cdf(d2)
            delta = cls.norm_cdf(d1)
            rho = (K * T * exp_rT * cls.norm_cdf(d2)) * 0.01
            theta_part2 = -r * K * exp_rT * cls.norm_cdf(d2)
        else:
            price = K * exp_rT * cls.norm_cdf(-d2) - S * cls.norm_cdf(-d1)
            delta = cls.norm_cdf(d1) - 1.0
            rho = (-K * T * exp_rT * cls.norm_cdf(-d2)) * 0.01
            theta_part2 = r * K * exp_rT * cls.norm_cdf(-d2)

        # Analytical Greeks
        gamma = pdf_d1 / (S * sigma * sqrt_T)
        vega = (S * sqrt_T * pdf_d1) * 0.01  # 1% IV change sensitivity
        
        # 1-day theta decay
        theta_part1 = -(S * pdf_d1 * sigma) / (2.0 * sqrt_T)
        theta_daily = (theta_part1 + theta_part2) / 365.0

        # Enforce no-arbitrage boundary conditions
        final_premium = max(price, intrinsic, 0.05)
        time_value = max(0.0, final_premium - intrinsic)

        return {
            "premium": round(final_premium, 2),
            "intrinsic": round(intrinsic, 2),
            "time_value": round(time_value, 2),
            "delta": round(delta, 3),
            "theta": round(theta_daily, 2),
            "gamma": round(gamma, 5),
            "vega": round(vega, 2),
            "rho": round(rho, 3),
            "iv": round(sigma * 100, 1),
        }


# =====================================================================
# 2. Implied Volatility & Moneyness Skew Model
# =====================================================================
class VolatilityModel:
    """Asset-class calibrated implied volatility mapping with parametric volatility skew."""

    # Baseline IV for Indian Market Asset Classes
    ASSET_CLASS_IV: dict[str, float] = {
        # Broad Market Indices
        "NIFTY": 0.135,
        "NIFTY50": 0.135,
        "SENSEX": 0.130,
        "BANKNIFTY": 0.155,
        "FINNIFTY": 0.145,
        "MIDCPNIFTY": 0.150,
        "BANKEX": 0.150,

        # Low Beta / Defensive Equities
        "ITC": 0.220,
        "TCS": 0.210,
        "INFY": 0.230,
        "HDFCBANK": 0.220,
        "ICICIBANK": 0.230,
        "SBIN": 0.240,
        "BHARTIARTL": 0.230,
        "LT": 0.220,
        "KOTAKBANK": 0.220,
        "HINDUNILVR": 0.200,

        # Auto & Ancillaries
        "BOSCHLTD": 0.290,
        "MARUTI": 0.250,
        "BAJAJ-AUTO": 0.260,
        "HEROMOTOCO": 0.270,
        "EICHERMOT": 0.280,
        "TVSMOTOR": 0.320,
        "TATAMOTORS": 0.330,

        # High Beta / Volatile Growth Equities
        "TRENT": 0.340,
        "BAJFINANCE": 0.300,
        "PFC": 0.320,
        "RECLTD": 0.330,
        "IDFCFIRSTB": 0.340,
        "COALINDIA": 0.290,
        "TATASTEEL": 0.320,
        "ADANIENT": 0.360,
        "ADANIPORTS": 0.320,
        "DLF": 0.320,
        "VEDL": 0.340,
    }

    DEFAULT_EQUITY_IV: float = 0.280

    @classmethod
    def get_base_iv(cls, symbol: str) -> float:
        """Fetch baseline implied volatility for symbol."""
        clean_sym = symbol.strip().upper()
        return cls.ASSET_CLASS_IV.get(clean_sym, cls.DEFAULT_EQUITY_IV)

    @classmethod
    def calculate_skewed_iv(
        cls,
        symbol: str,
        spot: float,
        strike: float,
        option_type: str = "CE",
        base_iv_override: float | None = None,
    ) -> float:
        """
        Calculate moneyness-adjusted implied volatility incorporating the Indian market volatility skew.
        
        Moneyness m = ln(K / S)
        Deep OTM Puts (K < S) carry significant crash hedging premiums.
        """
        base_iv = base_iv_override if (base_iv_override and base_iv_override > 0) else cls.get_base_iv(symbol)
        opt_type = option_type.strip().upper()

        if spot <= 0 or strike <= 0:
            return base_iv

        moneyness = math.log(strike / spot)

        # Asymmetric Skew Formula calibrated against NSE F&O smile
        if opt_type == "PE" and strike < spot:
            # OTM Put: Strong downside skew
            skew_factor = 0.35 * (moneyness ** 2) - 0.25 * moneyness
        elif opt_type == "CE" and strike > spot:
            # OTM Call: Moderate upside skew
            skew_factor = 0.20 * (moneyness ** 2) + 0.05 * moneyness
        else:
            # ITM Options: Convexity smile
            skew_factor = 0.15 * (moneyness ** 2)

        adjusted_sigma = base_iv * (1.0 + skew_factor)
        return max(adjusted_sigma, 0.08)


# =====================================================================
# 3. NSE Derivatives Master Registry & Expiry Engine
# =====================================================================
class NSEDerivativesMaster:
    """Registry of NSE contract specifications, lot sizes, and regulatory expiry calendar."""

    LOT_SIZES: dict[str, int] = {
        # Major Indices
        "NIFTY": 25,
        "BANKNIFTY": 15,
        "FINNIFTY": 25,
        "MIDCPNIFTY": 50,
        "SENSEX": 10,
        "BANKEX": 15,

        # Standard Equities
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

    INDEX_SYMBOLS: set[str] = {
        "NIFTY", "NIFTY50", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"
    }

    @classmethod
    def is_index(cls, symbol: str) -> bool:
        """Check if ticker is an index derivative."""
        return symbol.strip().upper() in cls.INDEX_SYMBOLS

    @classmethod
    def get_lot_size(cls, symbol: str, spot_price: float = 0.0) -> int:
        """Fetch standard lot size with spot-price fallback for unmapped equities."""
        clean_sym = symbol.strip().upper()
        if clean_sym in cls.LOT_SIZES:
            return cls.LOT_SIZES[clean_sym]

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
        """Calculate regular strike ladder step based on ticker and price range."""
        clean_sym = symbol.strip().upper()
        if clean_sym in cls.STRIKE_STEPS:
            return cls.STRIKE_STEPS[clean_sym]

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
    def get_expiry_calendar(cls, symbol: str) -> list[dict[str, Any]]:
        """
        Generate exact NSE regulatory expiry calendar:
        - Indices: Weekly cycle on specific weekday (NIFTY=Thu, BANKNIFTY=Wed, FINNIFTY=Tue, MIDCPNIFTY=Mon, SENSEX=Fri).
        - Stock Options: Monthly cycle on the Last Thursday of current, next, and far months.
        """
        clean_sym = symbol.strip().upper()
        today = datetime.now(timezone.utc).date()
        expiries = []

        if cls.is_index(clean_sym):
            # Index weekly schedule
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
            # Equity monthly schedule (Last Thursday)
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
            expiries = cls.get_expiry_calendar(symbol)
            return expiries[0]["days_to_expiry"] if expiries else 3.0

        try:
            exp_date = datetime.strptime(expiry_date_str.strip(), "%Y-%m-%d").date()
            today = datetime.now(timezone.utc).date()
            diff_days = (exp_date - today).days
            return max(0.5, float(diff_days))
        except Exception:
            return 3.0


# =====================================================================
# 4. Unified Options Pricing Facade
# =====================================================================
class OptionsPricingService:
    """Unified Facade maintaining backward compatibility and high-level option APIs."""

    @classmethod
    def get_lot_size(cls, symbol: str, spot_price: float = 0.0) -> int:
        return NSEDerivativesMaster.get_lot_size(symbol, spot_price)

    @classmethod
    def get_strike_step(cls, symbol: str, spot_price: float) -> float:
        return NSEDerivativesMaster.get_strike_step(symbol, spot_price)

    @classmethod
    def get_asset_iv(cls, symbol: str) -> float:
        return VolatilityModel.get_base_iv(symbol)

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
        """Compute Black-Scholes theoretical option premium, Greeks, and volatility skew."""
        sigma = VolatilityModel.calculate_skewed_iv(
            symbol=symbol,
            spot=spot,
            strike=strike,
            option_type=option_type,
            base_iv_override=iv,
        )

        T_years = max(days_to_expiry, 0.25) / 365.0
        return BlackScholesPricer.price_and_greeks(
            spot=spot,
            strike=strike,
            time_to_expiry_years=T_years,
            volatility=sigma,
            risk_free_rate=r,
            option_type=option_type,
        )

    @classmethod
    def get_expiry_calendar_for_symbol(cls, symbol: str) -> list[dict[str, Any]]:
        return NSEDerivativesMaster.get_expiry_calendar(symbol)

    @classmethod
    def calculate_days_to_expiry(cls, expiry_date_str: str | None, symbol: str = "NIFTY") -> float:
        return NSEDerivativesMaster.calculate_days_to_expiry(expiry_date_str, symbol)

    @classmethod
    def get_option_strikes(
        cls,
        symbol: str,
        spot_price: float,
        expiry_date_str: str | None = None,
    ) -> dict[str, Any]:
        """Generate standard ATM, ITM, and OTM strike ladder around spot price with accurate DTE."""
        clean_sym = symbol.strip().upper()
        step = NSEDerivativesMaster.get_strike_step(clean_sym, spot_price)
        lot_size = NSEDerivativesMaster.get_lot_size(clean_sym, spot_price)
        expiries = NSEDerivativesMaster.get_expiry_calendar(clean_sym)

        if expiry_date_str:
            days_to_expiry = NSEDerivativesMaster.calculate_days_to_expiry(expiry_date_str, clean_sym)
        elif expiries:
            days_to_expiry = expiries[0]["days_to_expiry"]
        else:
            days_to_expiry = 3.0

        # Calculate nearest round ATM strike
        atm_strike = round(spot_price / step) * step

        strikes = []
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

"""
Black-Scholes Greeks (delta, theta, vega) and PoP.
Uses py_vollib when available; falls back to scipy-based implementation.
"""
from __future__ import division

from datetime import date, datetime, timezone

import numpy as np
import pandas as pd

from backend.config import RISK_FREE_RATE
from backend.models.options import OptionContractWithGreeks


def _time_to_expiry_years(expiration: date) -> float:
    """Years from now to expiration (assume 4pm ET = 21:00 UTC for expiry)."""
    now = datetime.now(timezone.utc)
    # Expiration at market close: same calendar day 4pm ET
    exp_dt = datetime(expiration.year, expiration.month, expiration.day, 21, 0, 0, tzinfo=timezone.utc)
    if exp_dt <= now:
        return 0.0
    delta = (exp_dt - now).total_seconds() / (365.25 * 24 * 3600)
    return max(0.0, min(delta, 2.0))  # cap for sanity


def _bs_d1_d2(S: float, K: float, t: float, r: float, sigma: float):
    if t <= 0 or sigma <= 0:
        return 0.0, 0.0
    sqrt_t = np.sqrt(t)
    d1 = (np.log(S / K) + (r + 0.5 * sigma * sigma) * t) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    return d1, d2


def _greeks_scipy(flag: str, S: float, K: float, t: float, r: float, sigma: float):
    """Delta, theta (per day), vega (per 1% vol) using scipy."""
    from scipy.stats import norm
    if t <= 0 or sigma <= 0:
        return None, None, None
    d1, d2 = _bs_d1_d2(S, K, t, r, sigma)
    sqrt_t = np.sqrt(t)
    # Delta
    if flag == "c":
        delta = norm.cdf(d1)
    else:
        delta = norm.cdf(d1) - 1.0
    # Theta (per day): -dOption/dt / 365
    nd1 = norm.pdf(d1)
    first_term = (-S * nd1 * sigma) / (2 * sqrt_t)
    if flag == "c":
        second_term = r * K * np.exp(-r * t) * norm.cdf(d2)
        theta = (first_term - second_term) / 365.0
    else:
        second_term = r * K * np.exp(-r * t) * norm.cdf(-d2)
        theta = (first_term + second_term) / 365.0
    # Vega: dOption/d(sigma) * 0.01 (per 1% move)
    vega = S * nd1 * sqrt_t * 0.01
    return delta, theta, vega


def _pop_short_put(d2: float) -> float:
    """Probability of profit for short put at expiration: P(S_T > K) = N(-d2)."""
    from scipy.stats import norm
    return float(norm.cdf(-d2))


def _greeks_pyvollib(flag: str, S: float, K: float, t: float, r: float, sigma: float):
    """Delta, theta, vega using py_vollib (if available)."""
    try:
        from py_vollib.black_scholes.greeks import analytical
        delta = analytical.delta(flag, S, K, t, r, sigma)
        theta = analytical.theta(flag, S, K, t, r, sigma)
        vega = analytical.vega(flag, S, K, t, r, sigma)
        return delta, theta, vega
    except Exception:
        return None, None, None


def compute_greeks_and_pop(
    flag: str,
    S: float,
    K: float,
    t: float,
    r: float,
    sigma: float,
) -> tuple[float | None, float | None, float | None, float | None]:
    """
    Returns (delta, theta, vega, pop).
    PoP = probability of profit for short put at expiration (N(-d2)).
    """
    if sigma is None or sigma <= 0 or t <= 0:
        return None, None, None, None
    try:
        delta, theta, vega = _greeks_pyvollib(flag, S, K, t, r, sigma)
    except Exception:
        delta, theta, vega = _greeks_scipy(flag, S, K, t, r, sigma)
    if delta is None:
        return None, None, None, None
    _, d2 = _bs_d1_d2(S, K, t, r, sigma)
    # PoP = probability of profit for short option at expiration: N(-d2) (put: S_T > K, call: S_T < K)
    pop = _pop_short_put(d2)
    return delta, theta, vega, pop


def _safe_float(val) -> float | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _safe_int(val) -> int | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _premium_for_seller(row: pd.Series) -> float | None:
    """Premium credit for seller: bid, or mid (bid+ask)/2, or last price."""
    bid = _safe_float(row.get("bid"))
    ask = _safe_float(row.get("ask"))
    mid = (bid + ask) / 2.0 if (bid is not None and ask is not None) else None
    last = _safe_float(row.get("lastPrice"))
    return bid or mid or last


def _seller_roi(strike: float, premium: float | None) -> float | None:
    """Seller ROI %: (premium_received / capital_per_contract) * 100; capital = strike * 100."""
    if strike <= 0 or premium is None or premium <= 0:
        return None
    return round((premium / strike) * 100.0, 4)


def _row_to_contract_with_greeks(
    row: pd.Series,
    expiration: date,
    spot: float,
    risk_free_rate: float,
    flag: str,
) -> OptionContractWithGreeks:
    r = risk_free_rate
    S = spot
    K = _safe_float(row.get("strike")) or 0.0
    t = _time_to_expiry_years(expiration)
    sigma = _safe_float(row.get("impliedVolatility"))
    delta, theta, vega, pop = compute_greeks_and_pop(flag, S, K, t, r, sigma or 0.2)
    premium = _premium_for_seller(row)
    seller_roi = _seller_roi(K, premium)

    return OptionContractWithGreeks(
        contract_symbol=str(row.get("contractSymbol", "")),
        strike=K,
        bid=_safe_float(row.get("bid")),
        ask=_safe_float(row.get("ask")),
        last_price=_safe_float(row.get("lastPrice")),
        volume=_safe_int(row.get("volume")),
        open_interest=_safe_int(row.get("openInterest")),
        in_the_money=bool(row.get("inTheMoney", False)),
        expiration=expiration,
        seller_roi=seller_roi,
        delta=delta,
        theta=theta,
        vega=vega,
        pop=pop,
    )


def add_greeks_to_chain(
    puts_df: pd.DataFrame | None,
    calls_df: pd.DataFrame | None,
    expiration: date,
    spot: float,
) -> tuple[list[OptionContractWithGreeks], list[OptionContractWithGreeks] | None]:
    """
    Convert chain DataFrames to lists of OptionContractWithGreeks.
    Returns (puts_list, calls_list). calls_list is None if calls_df was None.
    """
    r = RISK_FREE_RATE
    puts_list: list[OptionContractWithGreeks] = []
    if puts_df is not None and not puts_df.empty:
        for _, row in puts_df.iterrows():
            puts_list.append(_row_to_contract_with_greeks(row, expiration, spot, r, "p"))

    calls_list: list[OptionContractWithGreeks] | None = []
    if calls_df is not None and not calls_df.empty:
        for _, row in calls_df.iterrows():
            calls_list.append(_row_to_contract_with_greeks(row, expiration, spot, r, "c"))
    else:
        calls_list = None

    return puts_list, calls_list

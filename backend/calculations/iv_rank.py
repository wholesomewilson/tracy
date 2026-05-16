"""
IV Rank and IV Percentile (V1).
Uses underlying's historical realized volatility as proxy for historical IV.
"""

import numpy as np
import pandas as pd


TRADING_DAYS_52W = 252
ROLLING_WINDOW = 20  # 20-day rolling vol


def get_realized_vol_series_from_history(hist: pd.DataFrame) -> pd.Series | None:
    """
    Compute rolling annualized volatility (log returns) from a history DataFrame with "Close" column.
    Returns a Series of daily realized vol values. Caller provides pre-fetched history.
    """
    if hist is None or len(hist) < ROLLING_WINDOW + 1:
        return None
    if "Close" not in hist.columns:
        return None
    close = hist["Close"].astype(float)
    log_ret = np.log(close / close.shift(1)).dropna()
    rolling_vol = log_ret.rolling(ROLLING_WINDOW).std() * np.sqrt(252)
    return rolling_vol.dropna()


def get_current_iv_from_chain_with_data(
    chain_puts_or_calls_df: pd.DataFrame,
    spot: float,
    strike: float | None = None,
    use_atm: bool = True,
) -> float | None:
    """
    Current IV from an already-fetched option chain DataFrame (puts or calls).
    If use_atm=True, use average IV of 5 options with strike closest to spot; else average of chain.
    """
    if chain_puts_or_calls_df is None or chain_puts_or_calls_df.empty:
        return None
    iv_col = "impliedVolatility"
    if iv_col not in chain_puts_or_calls_df.columns:
        return None
    if strike is not None:
        opts = chain_puts_or_calls_df[chain_puts_or_calls_df["strike"] == strike]
        if opts.empty:
            return None
        val = opts[iv_col].iloc[0]
        return float(val) if pd.notna(val) else None
    if use_atm:
        df = chain_puts_or_calls_df.copy()
        df["dist"] = abs(df["strike"] - spot)
        df = df.sort_values("dist")
        near = df.head(5)
        iv_vals = near[iv_col].dropna()
        if iv_vals.empty:
            return None
        return float(iv_vals.mean())
    iv_vals = chain_puts_or_calls_df[iv_col].dropna()
    if iv_vals.empty:
        return None
    return float(iv_vals.mean())


def iv_rank_and_percentile(
    current_iv: float,
    realized_vol_series: pd.Series,
) -> tuple[float | None, float | None]:
    """
    IV Rank and IV Percentile from a series of realized vol (e.g. 52w rolling).
    IV Rank = (current_iv - min) / (max - min) * 100
    IV Percentile = pct of days where realized vol < current_iv, * 100
    """
    if realized_vol_series is None or realized_vol_series.empty:
        return None, None
    arr = realized_vol_series.values
    vmin = float(np.nanmin(arr))
    vmax = float(np.nanmax(arr))
    if vmax <= vmin:
        return None, None
    rank = (current_iv - vmin) / (vmax - vmin) * 100.0
    rank = max(0.0, min(100.0, rank))
    count_below = np.nansum(arr < current_iv)
    n = len(arr)
    percentile = (count_below / n * 100.0) if n else None
    if percentile is not None:
        percentile = max(0.0, min(100.0, percentile))
    return rank, percentile

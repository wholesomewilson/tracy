"""
Single per-symbol yfinance fetch: one Ticker, all data for the feed.
"""

from dataclasses import dataclass
from datetime import date, timedelta
import logging

import yfinance as yf

logger = logging.getLogger(__name__)

from backend.calculations.iv_rank import (
    get_current_iv_from_chain_with_data,
    get_realized_vol_series_from_history,
    iv_rank_and_percentile,
    TRADING_DAYS_52W,
)
from backend.models.options import IVResponse, OptionChainResponse
from backend.services import options_service, stock_criteria_service


@dataclass
class TickerBundle:
    """All feed data for one symbol from a single yfinance Ticker fetch."""

    quote: float
    option_chain_response: OptionChainResponse
    stock_criteria: dict


def get_ticker_bundle(
    symbol: str,
    expiration: date | None,
    *,
    include_calls: bool = False,
    min_seller_roi: float | None = None,
    percent_below_quote: float = 10.0,
) -> TickerBundle | None:
    """
    Create one yf.Ticker(symbol), fetch quote, option chain, and stock criteria.
    Returns None if quote is missing (symbol should be skipped).
    """
    sym = symbol.strip().upper()
    t = yf.Ticker(sym)

    quote = options_service.get_underlying_price_from_ticker(t)
    if quote is None:
        return None

    expirations = options_service.get_expirations_from_ticker(t)
    use_exp = None
    puts_df = None
    calls_df = None

    if expirations:
        use_exp = (
            expiration if expiration and expiration in expirations else expirations[0]
        )
        exp_str = use_exp.strftime("%Y-%m-%d")
        try:
            chain = t.option_chain(exp_str)
            puts_df = getattr(chain, "puts", None)
            calls_df = getattr(chain, "calls", None)
        except Exception:
            pass

    # IV from same Ticker's data
    iv_metrics = None
    if puts_df is not None and not puts_df.empty and quote is not None:
        current_iv = get_current_iv_from_chain_with_data(puts_df, quote, use_atm=True)
        end = date.today()
        start = end - timedelta(days=int(TRADING_DAYS_52W * 1.5))
        try:
            hist_52w = t.history(
                start=start.isoformat(),
                end=end.isoformat(),
                auto_adjust=True,
            )
        except Exception:
            hist_52w = None
        realized_vol = (
            get_realized_vol_series_from_history(hist_52w)
            if hist_52w is not None
            else None
        )
        iv_rank, iv_percentile = (
            iv_rank_and_percentile(current_iv, realized_vol)
            if current_iv is not None and realized_vol is not None
            else (None, None)
        )
        iv_metrics = IVResponse(
            ticker=sym,
            implied_volatility=current_iv,
            iv_rank=iv_rank,
            iv_percentile=iv_percentile,
            note="V1: IV Rank/Percentile use underlying 20-day realized vol (52w history) as proxy for historical IV.",
        )

    if use_exp is not None and puts_df is not None:
        option_chain_response = options_service._build_option_chain_response(
            ticker=sym,
            puts_df=puts_df,
            calls_df=calls_df,
            underlying=quote,
            expiration=use_exp,
            include_calls=include_calls,
            min_seller_roi=min_seller_roi,
            iv_metrics=iv_metrics,
            percent_below_quote=percent_below_quote,
        )
    else:
        option_chain_response = OptionChainResponse(
            ticker=sym,
            puts=[],
            calls=[] if include_calls else None,
            quote=quote,
            iv=iv_metrics,
        )

    try:
        stock_criteria = stock_criteria_service.get_stock_criteria_from_ticker(t, sym)
    except Exception:
        stock_criteria = {"symbol": sym}

    return TickerBundle(
        quote=quote,
        option_chain_response=option_chain_response,
        stock_criteria=stock_criteria,
    )

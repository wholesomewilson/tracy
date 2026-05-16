"""Pydantic models for options chain, Greeks, and IV API."""
from datetime import date

from pydantic import BaseModel, Field


class OptionContract(BaseModel):
    """Single option contract (put or call) from the chain."""

    contract_symbol: str = Field(..., description="OCC option symbol")
    strike: float = Field(..., description="Strike price")
    bid: float | None = Field(None, description="Bid price")
    ask: float | None = Field(None, description="Ask price")
    last_price: float | None = Field(None, description="Last traded price")
    volume: int | None = Field(None, description="Trading volume")
    open_interest: int | None = Field(None, description="Open interest")
    in_the_money: bool = Field(..., description="Whether the option is in the money")
    expiration: date = Field(..., description="Expiration date")
    seller_roi: float | None = Field(
        None,
        description="Seller ROI %: (premium / strike) * 100; premium = bid or mid (capital = strike * 100).",
    )


class OptionContractWithGreeks(OptionContract):
    """Option contract plus Black-Scholes Greeks and PoP."""

    delta: float | None = Field(None, description="Delta")
    theta: float | None = Field(None, description="Theta (per day)")
    vega: float | None = Field(None, description="Vega (per 1% vol change)")
    pop: float | None = Field(None, description="Probability of profit (short put at expiration)")


class OptionChainResponse(BaseModel):
    """Options chain (puts-focused)."""

    ticker: str = Field(..., description="Underlying symbol")
    puts: list[OptionContract] | list[OptionContractWithGreeks] = Field(..., description="Put contracts")
    calls: list[OptionContract] | list[OptionContractWithGreeks] | None = Field(
        None, description="Call contracts (optional)"
    )
    quote: float | None = Field(None, description="Current underlying price (quote)")
    iv: "IVResponse | None" = Field(
        None,
        description="IV metrics for this chain (implied vol, IV Rank, IV Percentile).",
    )


class IVResponse(BaseModel):
    """Implied volatility and IV Rank/Percentile for a ticker."""

    ticker: str = Field(..., description="Underlying symbol")
    implied_volatility: float | None = Field(None, description="Current IV (e.g. ATM or average)")
    iv_rank: float | None = Field(None, description="IV Rank 0-100 (vs 52w realized vol range)")
    iv_percentile: float | None = Field(None, description="IV Percentile 0-100 (days with lower vol)")
    note: str | None = Field(None, description="Caveat e.g. V1 uses underlying realized vol")

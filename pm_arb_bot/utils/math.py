"""Mathematical helpers for order book analysis."""

from __future__ import annotations

from typing import Iterable, Sequence

from ..types import Level, Side


def vwap_for_size(levels: Sequence[Level], target: float) -> tuple[float | None, float]:
    """Compute the VWAP required to fill ``target`` units from ``levels``."""

    if target <= 0:
        return (None, 0.0)
    filled = 0.0
    notional = 0.0
    for lvl in levels:
        remaining = target - filled
        if remaining <= 0:
            break
        take = min(lvl.size, remaining)
        filled += take
        notional += take * lvl.price
    if filled <= 0:
        return (None, 0.0)
    return (notional / filled, filled)


def fraction_to_bps(value: float) -> int:
    return int(round(value * 10_000))


def bps_to_fraction(bps: int) -> float:
    return bps / 10_000.0


def max_fill_size_with_slippage(levels: Sequence[Level], max_slippage_bps: int, side: Side) -> float:
    """Return the maximum fill size while staying inside the slippage guard."""

    if not levels:
        return 0.0
    if max_slippage_bps < 0:
        raise ValueError("max_slippage_bps must be non-negative")
    limit_multiplier = 1.0 + (bps_to_fraction(max_slippage_bps) if side == Side.BUY else -bps_to_fraction(max_slippage_bps))
    baseline = levels[0].price
    allowed_price = baseline * limit_multiplier
    filled = 0.0
    for lvl in levels:
        if side == Side.BUY and lvl.price > allowed_price + 1e-12:
            break
        if side == Side.SELL and lvl.price < allowed_price - 1e-12:
            break
        filled += lvl.size
    return filled


def capped_size(levels: Iterable[Level], cap: float) -> float:
    total = 0.0
    for lvl in levels:
        total += lvl.size
        if total >= cap:
            return cap
    return total

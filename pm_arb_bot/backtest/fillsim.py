"""VWAP-based fill simulator for backtests."""

from __future__ import annotations

from typing import Sequence

from ..types import Level, Side
from ..utils.math import bps_to_fraction


def simulate_fill(levels: Sequence[Level], target_size: float, side: Side, slippage_bps: int) -> tuple[float, float]:
    """Return (avg_price, filled_size) while respecting slippage guard."""

    if not levels or target_size <= 0:
        return (0.0, 0.0)
    limit_fraction = bps_to_fraction(slippage_bps)
    baseline = levels[0].price
    price_limit = baseline * (1 + limit_fraction if side == Side.BUY else 1 - limit_fraction)
    filled = 0.0
    notional = 0.0
    for level in levels:
        if side == Side.BUY and level.price > price_limit + 1e-12:
            break
        if side == Side.SELL and level.price < price_limit - 1e-12:
            break
        take = min(level.size, target_size - filled)
        filled += take
        notional += take * level.price
        if filled >= target_size:
            break
    if filled <= 0:
        return (0.0, 0.0)
    return (notional / filled, filled)

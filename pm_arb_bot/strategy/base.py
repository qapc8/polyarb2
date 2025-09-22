"""Strategy interfaces and helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Sequence

from ..settings import StrategyConfig
from ..types import BookSnapshot, Level, Side
from ..utils.math import bps_to_fraction, max_fill_size_with_slippage, vwap_for_size

Books = Dict[str, BookSnapshot]


class BaseStrategy(ABC):
    def __init__(self, config: StrategyConfig) -> None:
        self.config = config

    @abstractmethod
    def generate_signals(
        self,
        books: Books,
        discovery_state,
        risk_engine,
        now_ms: int,
    ) -> List:
        raise NotImplementedError

    def _max_fill_for_side(self, levels: Sequence[Level], side: Side) -> float:
        return max_fill_size_with_slippage(levels, self.config.slippage_bps, side)

    def _vwap_guard(self, levels: Sequence[Level], size: float) -> tuple[float | None, float]:
        return vwap_for_size(levels, size)

    def _meets_notional(self, price: float, size: float, legs: int = 1) -> bool:
        return price * size * legs >= self.config.min_notional_usd

    def _slippage_fraction(self) -> float:
        return bps_to_fraction(self.config.slippage_bps)

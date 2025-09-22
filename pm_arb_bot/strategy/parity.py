"""Two-sided parity strategy implementation."""

from __future__ import annotations

from typing import List

from ..data.discovery import DiscoveryState
from ..settings import StrategyConfig
from ..types import OrderIntent, Side, Signal, SignalType, TimeInForce
from ..utils.math import fraction_to_bps
from .base import BaseStrategy, Books


class ParityStrategy(BaseStrategy):
    def __init__(self, config: StrategyConfig) -> None:
        super().__init__(config)

    def generate_signals(
        self,
        books: Books,
        discovery_state: DiscoveryState,
        risk_engine,
        now_ms: int,
    ) -> List[Signal]:
        results: List[Signal] = []
        if not self.config.enable_parity:
            return results

        for yes_market, no_market in discovery_state.iter_yes_no_pairs():
            book_yes = books.get(yes_market.market_id)
            book_no = books.get(no_market.market_id)
            if not book_yes or not book_no or not book_yes.asks or not book_no.asks:
                continue
            ask_yes = book_yes.best_ask()
            ask_no = book_no.best_ask()
            if not ask_yes or not ask_no:
                continue
            edge = 1.0 - (ask_yes.price + ask_no.price)
            edge_bps = fraction_to_bps(edge)
            if edge_bps < self.config.epsilon_bps:
                continue
            size_yes = self._max_fill_for_side(book_yes.asks, Side.BUY)
            size_no = self._max_fill_for_side(book_no.asks, Side.BUY)
            size = min(size_yes, size_no)
            if size <= 0:
                continue
            combined_price = ask_yes.price + ask_no.price
            if not self._meets_notional(combined_price, size):
                continue
            price_cap_yes = ask_yes.price * (1 + self._slippage_fraction())
            price_cap_no = ask_no.price * (1 + self._slippage_fraction())
            legs = [
                OrderIntent(
                    market_id=yes_market.market_id,
                    side=Side.BUY,
                    price=round(price_cap_yes, 4),
                    size=size,
                    tif=TimeInForce.FOK,
                    post_only=False,
                ),
                OrderIntent(
                    market_id=no_market.market_id,
                    side=Side.BUY,
                    price=round(price_cap_no, 4),
                    size=size,
                    tif=TimeInForce.FOK,
                    post_only=False,
                ),
            ]
            signal = Signal.new(
                signal_type=SignalType.PARITY,
                edge_bps=edge_bps,
                size=size,
                legs=legs,
                reason="parity_sum_lt_one",
                event_id=yes_market.event_id,
            )
            if risk_engine and not risk_engine.allow_signal(signal, event_id=yes_market.event_id, now_ms=now_ms):
                continue
            results.append(signal)
        return results

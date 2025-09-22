"""Resolution aware sniping strategy."""

from __future__ import annotations

from typing import List

from ..data.discovery import DiscoveryState
from ..types import OrderIntent, Side, Signal, SignalType, TimeInForce
from ..utils.math import fraction_to_bps
from .base import BaseStrategy, Books


class ResolutionStrategy(BaseStrategy):
    def generate_signals(
        self,
        books: Books,
        discovery_state: DiscoveryState,
        risk_engine,
        now_ms: int,
    ) -> List[Signal]:
        results: List[Signal] = []
        if not self.config.enable_resolution:
            return results

        guard_ms = self.config.resolution_guard_minutes * 60 * 1000
        for event in discovery_state.events.values():
            if event.status not in {"resolving", "resolved", "dispute"}:
                continue
            time_since_clarified = now_ms - event.last_clarified_at
            allow_entry = time_since_clarified >= guard_ms
            clip_scale = 0.2 if not allow_entry else 1.0
            for market in discovery_state.markets_for_event(event.event_id):
                book = books.get(market.market_id)
                if not book or not book.asks:
                    continue
                best = book.best_ask()
                if not best:
                    continue
                edge = max(0.0, 1.0 - best.price)
                edge_bps = fraction_to_bps(edge)
                if edge_bps < self.config.epsilon_bps:
                    continue
                depth = self._max_fill_for_side(book.asks, Side.BUY)
                if depth <= 0:
                    continue
                size = depth * clip_scale
                if size <= 0:
                    continue
                notional = best.price * size
                if notional < self.config.min_notional_usd * clip_scale:
                    size = (self.config.min_notional_usd * clip_scale) / max(best.price, 1e-9)
                legs = [
                    OrderIntent(
                        market_id=market.market_id,
                        side=Side.BUY,
                        price=round(best.price * (1 + self._slippage_fraction()), 4),
                        size=size,
                        tif=TimeInForce.IOC if not allow_entry else TimeInForce.FOK,
                        post_only=False,
                    )
                ]
                signal = Signal.new(
                    signal_type=SignalType.RESOLUTION_SNIPE,
                    edge_bps=edge_bps,
                    size=size,
                    legs=legs,
                    reason="resolution_signal",
                    event_id=event.event_id,
                )
                if risk_engine and not risk_engine.allow_signal(signal, event_id=event.event_id, now_ms=now_ms):
                    continue
                results.append(signal)
        return results

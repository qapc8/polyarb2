"""Negative risk basket strategy."""

from __future__ import annotations

from ..data.discovery import DiscoveryState, EventInfo, MarketInfo
from ..types import OrderIntent, Side, Signal, SignalType, TimeInForce
from ..utils.math import fraction_to_bps
from .base import BaseStrategy, Books


class BasketStrategy(BaseStrategy):
    def generate_signals(
        self,
        books: Books,
        discovery_state: DiscoveryState,
        risk_engine,
        now_ms: int,
    ) -> List[Signal]:
        results: List[Signal] = []
        if not self.config.enable_basket:
            return results

        for event in discovery_state.iter_basket_events():
            markets = [m for m in discovery_state.markets_for_event(event.event_id) if m.status == "open"]
            valid_markets = [m for m in markets if not _is_placeholder_outcome(event, m)]
            if len(valid_markets) < 2:
                continue
            books_present: list[tuple[MarketInfo, float, float]] = []
            for market in valid_markets:
                book = books.get(market.market_id)
                if not book or not book.asks:
                    break
                best = book.best_ask()
                if not best:
                    break
                books_present.append((market, best.price, self._max_fill_for_side(book.asks, Side.BUY)))
            else:
                basket_sum = sum(price for _, price, _ in books_present)
                edge = 1.0 - basket_sum
                edge_bps = fraction_to_bps(edge)
                if edge <= 0 or edge_bps < self.config.epsilon_bps:
                    continue
                size = min(depth for _, _, depth in books_present)
                if size <= 0:
                    continue
                if not self._meets_notional(basket_sum, size):
                    continue
                legs = [
                    OrderIntent(
                        market_id=market.market_id,
                        side=Side.BUY,
                        price=round(price * (1 + self._slippage_fraction()), 4),
                        size=size,
                        tif=TimeInForce.FOK,
                        post_only=False,
                    )
                    for market, price, _ in books_present
                ]
                signal = Signal.new(
                    signal_type=SignalType.BASKET,
                    edge_bps=edge_bps,
                    size=size,
                    legs=legs,
                    reason="basket_sum_lt_one",
                    event_id=event.event_id,
                )
                if risk_engine and not risk_engine.allow_signal(signal, event_id=event.event_id, now_ms=now_ms):
                    continue
                results.append(signal)
        return results


def _is_placeholder_outcome(event: EventInfo, market: MarketInfo) -> bool:
    for outcome in event.outcomes:
        if outcome.outcome_id == market.outcome or outcome.name == market.outcome:
            return outcome.is_placeholder
    # fallback: treat unmatched as named outcome
    return False

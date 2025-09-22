from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pm_arb_bot.data.discovery import build_state
from pm_arb_bot.data.schemas import EventSchema, MarketSchema, OutcomeSchema
from pm_arb_bot.strategy.basket import BasketStrategy
from pm_arb_bot.types import BookSnapshot, Level


def test_basket_generates_multi_leg_signal(risk_engine, strategy_config):
    event_time = datetime.now(timezone.utc) - timedelta(hours=5)
    outcomes = [
        OutcomeSchema(id="A", name="Alpha"),
        OutcomeSchema(id="B", name="Beta"),
        OutcomeSchema(id="C", name="Gamma"),
        OutcomeSchema(id="P", name="Placeholder", is_placeholder=True),
    ]
    event = EventSchema(
        id="ev_basket",
        title="Basket Event",
        outcomes=outcomes,
        status="open",
        last_clarified_at=event_time,
        neg_risk=True,
    )
    markets = [
        MarketSchema(id="m_a", event_id="ev_basket", outcome="A", status="open"),
        MarketSchema(id="m_b", event_id="ev_basket", outcome="B", status="open"),
        MarketSchema(id="m_c", event_id="ev_basket", outcome="C", status="open"),
        MarketSchema(id="m_p", event_id="ev_basket", outcome="P", status="open"),
    ]
    discovery = build_state([event], markets)
    risk_engine.set_discovery_state(discovery)
    books = {
        "m_a": BookSnapshot(
            market_id="m_a",
            ts=1,
            bids=[Level(price=0.3, size=300.0)],
            asks=[Level(price=0.33, size=400.0)],
        ),
        "m_b": BookSnapshot(
            market_id="m_b",
            ts=1,
            bids=[Level(price=0.3, size=300.0)],
            asks=[Level(price=0.33, size=400.0)],
        ),
        "m_c": BookSnapshot(
            market_id="m_c",
            ts=1,
            bids=[Level(price=0.3, size=300.0)],
            asks=[Level(price=0.33, size=400.0)],
        ),
        "m_p": BookSnapshot(
            market_id="m_p",
            ts=1,
            bids=[Level(price=0.3, size=300.0)],
            asks=[Level(price=0.33, size=400.0)],
        ),
    }

    strategy = BasketStrategy(strategy_config)
    now_ms = int((event_time + timedelta(hours=4)).timestamp() * 1000)
    signals = strategy.generate_signals(books, discovery, risk_engine, now_ms=now_ms)
    assert len(signals) == 1
    signal = signals[0]
    assert signal.type.value == "BASKET"
    assert len(signal.legs) == 3
    assert {leg.market_id for leg in signal.legs} == {"m_a", "m_b", "m_c"}

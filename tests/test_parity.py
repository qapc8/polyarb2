from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from pm_arb_bot.data.discovery import build_state
from pm_arb_bot.data.schemas import EventSchema, MarketSchema, OutcomeSchema
from pm_arb_bot.strategy.parity import ParityStrategy
from pm_arb_bot.types import BookSnapshot, Level


@pytest.mark.parametrize("ask_yes, ask_no", [(0.49, 0.49)])
def test_parity_signal_emitted(risk_engine, strategy_config, ask_yes, ask_no):
    event_time = datetime.now(timezone.utc) - timedelta(hours=3)
    event = EventSchema(
        id="ev1",
        title="Parity Event",
        outcomes=[
            OutcomeSchema(id="YES", name="YES"),
            OutcomeSchema(id="NO", name="NO"),
        ],
        status="open",
        last_clarified_at=event_time,
    )
    markets = [
        MarketSchema(id="m_yes", event_id="ev1", outcome="YES", status="open"),
        MarketSchema(id="m_no", event_id="ev1", outcome="NO", status="open"),
    ]
    discovery = build_state([event], markets)
    risk_engine.set_discovery_state(discovery)
    books = {
        "m_yes": BookSnapshot(
            market_id="m_yes",
            ts=1,
            bids=[Level(price=0.48, size=500.0)],
            asks=[Level(price=ask_yes, size=500.0), Level(price=0.5, size=500.0)],
        ),
        "m_no": BookSnapshot(
            market_id="m_no",
            ts=1,
            bids=[Level(price=0.48, size=500.0)],
            asks=[Level(price=ask_no, size=500.0), Level(price=0.5, size=500.0)],
        ),
    }

    strategy = ParityStrategy(strategy_config)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    signals = strategy.generate_signals(books, discovery, risk_engine, now_ms=now_ms)
    assert len(signals) == 1
    signal = signals[0]
    assert signal.edge_bps == 200
    assert signal.size == pytest.approx(500.0)
    assert all(leg.tif.value == "FOK" for leg in signal.legs)
    assert signal.legs[0].price > ask_yes

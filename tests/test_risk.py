from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pm_arb_bot.data.discovery import build_state
from pm_arb_bot.data.schemas import EventSchema, MarketSchema, OutcomeSchema
from pm_arb_bot.exec.risk import RiskEngine
from pm_arb_bot.settings import StrategyConfig
from pm_arb_bot.types import OrderIntent, RiskLimits, Side, Signal, SignalType, TimeInForce


def _make_signal(event_id: str, market_ids: tuple[str, str], price: float, size: float, edge_bps: int) -> Signal:
    legs = [
        OrderIntent(market_id=market_ids[0], side=Side.BUY, price=price, size=size, tif=TimeInForce.FOK, post_only=False),
        OrderIntent(market_id=market_ids[1], side=Side.BUY, price=price, size=size, tif=TimeInForce.FOK, post_only=False),
    ]
    return Signal.new(SignalType.PARITY, edge_bps=edge_bps, size=size, legs=legs, reason="test", event_id=event_id)


def test_risk_engine_enforces_limits():
    strategy_cfg = StrategyConfig()
    limits = RiskLimits(
        max_notional_per_market=120.0,
        max_notional_per_event=220.0,
        max_concurrent_signals=5,
        kill_on_ws_stale_ms=60_000,
    )
    risk = RiskEngine(limits, reentry_threshold_bps=strategy_cfg.reentry_threshold_bps, resolution_guard_minutes=0)
    event_time = datetime.now(timezone.utc) - timedelta(hours=4)
    event = EventSchema(
        id="risk-event",
        title="Risk Event",
        outcomes=[OutcomeSchema(id="YES", name="YES"), OutcomeSchema(id="NO", name="NO")],
        status="open",
        last_clarified_at=event_time,
    )
    markets = [
        MarketSchema(id="m_yes", event_id="risk-event", outcome="YES", status="open"),
        MarketSchema(id="m_no", event_id="risk-event", outcome="NO", status="open"),
    ]
    discovery = build_state([event], markets)
    risk.set_discovery_state(discovery)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    signal1 = _make_signal("risk-event", ("m_yes", "m_no"), price=0.55, size=100.0, edge_bps=20)
    assert risk.allow_signal(signal1, event_id="risk-event", now_ms=now_ms)
    signal2 = _make_signal("risk-event", ("m_yes", "m_no"), price=0.55, size=100.0, edge_bps=22)
    assert not risk.allow_signal(signal2, event_id="risk-event", now_ms=now_ms + 100)
    risk.release_signal(signal1.id)
    signal3 = _make_signal("risk-event", ("m_yes", "m_no"), price=0.55, size=100.0, edge_bps=25)
    # edge improvement is 5 bps, below reentry threshold -> blocked
    assert not risk.allow_signal(signal3, event_id="risk-event", now_ms=now_ms + 200)
    signal4 = _make_signal("risk-event", ("m_yes", "m_no"), price=0.55, size=100.0, edge_bps=40)
    assert risk.allow_signal(signal4, event_id="risk-event", now_ms=now_ms + 300)

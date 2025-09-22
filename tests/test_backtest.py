from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from pm_arb_bot.backtest.replay import ReplayBacktester, load_snapshots
from pm_arb_bot.data.discovery import build_state
from pm_arb_bot.data.schemas import EventSchema, MarketSchema, OutcomeSchema
from pm_arb_bot.exec.risk import RiskEngine
from pm_arb_bot.settings import StrategyConfig
from pm_arb_bot.strategy.parity import ParityStrategy
from pm_arb_bot.types import RiskLimits


def test_replay_backtester_produces_trades(tmp_path):
    strategy_cfg = StrategyConfig()
    strategy_cfg.epsilon_bps = 10
    limits = RiskLimits(
        max_notional_per_market=1_000_000.0,
        max_notional_per_event=1_000_000.0,
        max_concurrent_signals=10,
        kill_on_ws_stale_ms=60_000,
    )
    risk = RiskEngine(limits, reentry_threshold_bps=strategy_cfg.reentry_threshold_bps, resolution_guard_minutes=0)
    event_time = datetime.now(timezone.utc) - timedelta(hours=6)
    event = EventSchema(
        id="sample",
        title="Sample Event",
        outcomes=[OutcomeSchema(id="YES", name="YES"), OutcomeSchema(id="NO", name="NO")],
        status="open",
        last_clarified_at=event_time,
    )
    markets = [
        MarketSchema(id="m_yes", event_id="sample", outcome="YES", status="open"),
        MarketSchema(id="m_no", event_id="sample", outcome="NO", status="open"),
    ]
    discovery = build_state([event], markets)
    risk.set_discovery_state(discovery)
    strategy = ParityStrategy(strategy_cfg)
    sample_path = Path("pm_arb_bot/data/sample_books.ndjson")
    snapshots = load_snapshots(sample_path)
    backtester = ReplayBacktester(discovery, strategy, risk, slippage_bps=strategy_cfg.slippage_bps)
    trades = backtester.run(snapshots)
    assert trades
    trade = trades[0]
    assert pytest.approx(trade["pnl"], rel=1e-5) == 10.0
    assert trade["edge_bps"] >= strategy_cfg.epsilon_bps

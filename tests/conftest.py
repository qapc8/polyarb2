from __future__ import annotations

import pytest

from pm_arb_bot.exec.risk import RiskEngine
from pm_arb_bot.settings import StrategyConfig
from pm_arb_bot.types import RiskLimits


@pytest.fixture
def strategy_config() -> StrategyConfig:
    return StrategyConfig()


@pytest.fixture
def risk_engine(strategy_config: StrategyConfig) -> RiskEngine:
    limits = RiskLimits(
        max_notional_per_market=1_000_000.0,
        max_notional_per_event=2_000_000.0,
        max_concurrent_signals=10,
        kill_on_ws_stale_ms=60_000,
    )
    engine = RiskEngine(
        limits,
        reentry_threshold_bps=strategy_config.reentry_threshold_bps,
        resolution_guard_minutes=strategy_config.resolution_guard_minutes,
    )
    return engine

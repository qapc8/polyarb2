"""Command line interface for the Polymarket arbitrage bot."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import typer

from .config import load as load_config
from .data.discovery import DiscoveryService, build_state
from .data.schemas import EventSchema, MarketSchema, OutcomeSchema
from .data.rest import RestClient
from .data.persistence import Persistence
from .backtest.replay import ReplayBacktester, load_snapshots
from .infra.metrics import Metrics
from .settings import Settings
from .strategy.basket import BasketStrategy
from .strategy.parity import ParityStrategy
from .strategy.resolution import ResolutionStrategy
from .utils.logging import configure_logging, get_logger
from .utils.time import now_ms
from .types import BookSnapshot, RiskLimits
from .exec.risk import RiskEngine

app = typer.Typer(help="Polymarket arbitrage bot")
logger = get_logger(__name__)


def _risk_limits(settings: Settings) -> RiskLimits:
    return RiskLimits(
        max_notional_per_market=settings.risk.max_notional_per_market,
        max_notional_per_event=settings.risk.max_notional_per_event,
        max_concurrent_signals=settings.risk.max_concurrent_signals,
        kill_on_ws_stale_ms=settings.risk.kill_on_ws_stale_ms,
    )


@app.command()
def run(
    config: Path = typer.Option(Path("config.example.yaml"), help="Path to configuration YAML"),
    dry_run: bool = typer.Option(True, help="Operate without submitting live orders"),
    only: Optional[str] = typer.Option(None, help="Restrict to a specific strategy"),
    min_edge_bps: int = typer.Option(0, help="Override minimum edge threshold"),
) -> None:
    """Start the arbitrage bot event loop."""

    settings = load_config(config)
    if min_edge_bps:
        settings.strategy.epsilon_bps = min_edge_bps
    configure_logging(settings.logging.level)
    metrics = Metrics()
    metrics.start(settings.metrics.prometheus_port)
    risk = RiskEngine(
        _risk_limits(settings),
        reentry_threshold_bps=settings.strategy.reentry_threshold_bps,
        resolution_guard_minutes=settings.strategy.resolution_guard_minutes,
    )

    async def _async_main() -> None:
        if dry_run:
            discovery_state = _build_sample_discovery()
        else:
            discovery_service = DiscoveryService(settings)
            try:
                discovery_state = await discovery_service.refresh()
            finally:
                await discovery_service.close()
        risk.set_discovery_state(discovery_state)
        strategies = []
        if only in (None, "parity"):
            strategies.append(ParityStrategy(settings.strategy))
        if only in (None, "basket"):
            strategies.append(BasketStrategy(settings.strategy))
        if only in (None, "res"):
            strategies.append(ResolutionStrategy(settings.strategy))
        rest = RestClient(settings, dry_run=dry_run)
        try:
            books = _load_sample_books() if dry_run else {}
            for strategy in strategies:
                signals = strategy.generate_signals(books, discovery_state, risk, now_ms())
                for signal in signals:
                    metrics.observe_signal(signal.type.value, signal.edge_bps)
                    logger.info("signal", strategy=signal.type.value, edge_bps=signal.edge_bps, size=signal.size)
            if not dry_run:
                logger.info("live_run_started")
            else:
                logger.info("dry_run_complete", signals=len(strategies))
        finally:
            await rest.close()

    asyncio.run(_async_main())


@app.command()
def backtest(
    books: Path = typer.Option(..., exists=True, readable=True),
    strategy: str = typer.Option("parity", help="Strategy name (parity|basket)"),
    epsilon_bps: int = typer.Option(20, help="Edge threshold in bps"),
) -> None:
    """Replay historical books against a strategy."""

    settings = load_config("config.example.yaml")
    settings.strategy.epsilon_bps = epsilon_bps
    discovery_state = _build_sample_discovery()
    risk = RiskEngine(
        _risk_limits(settings),
        reentry_threshold_bps=settings.strategy.reentry_threshold_bps,
        resolution_guard_minutes=settings.strategy.resolution_guard_minutes,
    )
    if strategy == "parity":
        strat = ParityStrategy(settings.strategy)
    elif strategy == "basket":
        strat = BasketStrategy(settings.strategy)
    else:
        raise typer.BadParameter("strategy must be one of parity|basket")
    backtester = ReplayBacktester(discovery_state, strat, risk, slippage_bps=settings.strategy.slippage_bps)
    snapshots = load_snapshots(books)
    trades = backtester.run(snapshots)
    typer.echo(f"Generated {len(trades)} trades with total pnl {sum(t['pnl'] for t in trades):.4f}")


@app.command()
def doctor(config: Path = typer.Option(Path("config.example.yaml"))) -> None:
    """Run connectivity and readiness diagnostics."""

    settings = load_config(config)
    persistence = Persistence(settings.persistence.dsn)
    rest = RestClient(settings, dry_run=True)
    async def _run() -> None:
        await persistence.initialize()
        ok_ping = await rest.ping()
        typer.echo(f"REST ping: {'ok' if ok_ping else 'failed'}")
        typer.echo("Database ready")
        await rest.close()
        await persistence.close()

    asyncio.run(_run())


def _build_sample_discovery():
    outcomes = [
        OutcomeSchema(id="YES", name="YES"),
        OutcomeSchema(id="NO", name="NO"),
        OutcomeSchema(id="A", name="Outcome A"),
        OutcomeSchema(id="B", name="Outcome B"),
        OutcomeSchema(id="C", name="Outcome C"),
    ]
    events = [
        EventSchema(id="event-parity", title="Sample Parity", outcomes=outcomes[:2], status="open"),
        EventSchema(id="event-basket", title="Sample Basket", outcomes=outcomes[2:], status="open"),
    ]
    markets = [
        MarketSchema(id="m_yes", event_id="event-parity", outcome="YES", status="open"),
        MarketSchema(id="m_no", event_id="event-parity", outcome="NO", status="open"),
        MarketSchema(id="m_a", event_id="event-basket", outcome="Outcome A", status="open"),
        MarketSchema(id="m_b", event_id="event-basket", outcome="Outcome B", status="open"),
        MarketSchema(id="m_c", event_id="event-basket", outcome="Outcome C", status="open"),
    ]
    return build_state(events, markets)


def _load_sample_books() -> dict[str, BookSnapshot]:
    sample_path = Path(__file__).resolve().parent / "data" / "sample_books.ndjson"
    if not sample_path.exists():
        return {}
    snapshots = load_snapshots(sample_path)
    return {snap.market_id: snap for snap in snapshots}


if __name__ == "__main__":
    app()

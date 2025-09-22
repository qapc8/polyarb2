# Polymarket Arbitrage Bot

This repository contains a production-ready skeleton for a Polymarket arbitrage bot. It focuses on
three strategies: two-sided parity, negative-risk baskets, and resolution-aware sniping. The code is
structured for clarity and extensibility, and ships with async data ingestion, risk controls,
observability, persistence, and a replay backtester.

## Quickstart (dry-run in <10 minutes)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
cp .env.example .env
python -m pm_arb_bot.cli run --config config.example.yaml --dry-run
```

The dry-run uses bundled sample order books and emits sample parity and basket signals without
submitting live orders.

## Configuration

1. Copy `config.example.yaml` to `config.yaml` and adjust endpoints to your environment.
2. Copy `.env.example` to `.env` and set `PM_API_KEY`.
3. Update the `strategy`, `risk`, and `persistence` sections to match your deployment.

Configuration is validated with Pydantic and environment variables can be referenced via `${VAR}`
syntax.

## Running the bot

### Doctor

```
python -m pm_arb_bot.cli doctor --config config.yaml
```

Performs readiness checks: REST ping and SQLite initialisation.

### Live / Dry-run

```
python -m pm_arb_bot.cli run --config config.yaml --dry-run
python -m pm_arb_bot.cli run --config config.yaml --only parity --min-edge-bps 25
```

By default, the CLI runs in dry-run mode. Disable `--dry-run` to enable live order submission. Use
`--only` to restrict strategies.

### Backtesting

```
python -m pm_arb_bot.cli backtest --books pm_arb_bot/data/sample_books.ndjson --strategy parity
```

Runs the replay backtester against an NDJSON stream of order books and reports deterministic PnL.

## Metrics

The bot exports Prometheus metrics on `:9308/metrics`.

```
# Example scrape output
curl -s localhost:9308/metrics | grep arb_
```

Counters include `arb_signals_total`, `arb_trades_total`, and gauges such as `arb_ws_staleness_ms`.

## Safety Checklist

- **Kill switch**: set `ARB_KILL=1` to immediately block new signals.
- **Websocket heartbeat**: if no updates arrive within `kill_on_ws_stale_ms`, trading is halted.
- **Resolution guard**: new entries are blocked until event rules have been stable for the configured
  duration.
- **Small canaries**: operate in `--dry-run` mode and review signals before going live.

## Docker and Compose

```
docker compose build
docker compose up
```

The compose stack starts the bot and a Prometheus instance that scrapes it at `http://localhost:9090`.

## Development

- `make lint` → run Ruff and mypy
- `make test` → execute pytest
- `make fmt` → auto-fix lint issues

## Known Limitations & Next Steps

- The REST client operates in dry-run by default. Plug in authenticated endpoints before trading.
- Strategy sizing uses simplistic VWAP approximations; extend with inventory-aware sizing for
  production.
- The websocket client and discovery service are minimal and may need schema adjustments if the
  upstream APIs change.
- Resolution-aware sniping uses heuristic triggers; integrate authoritative resolution feeds for
  higher confidence.

Pull requests and extensions are welcome!

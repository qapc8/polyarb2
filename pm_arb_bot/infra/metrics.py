"""Prometheus metrics registry."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, start_http_server


class Metrics:
    def __init__(self) -> None:
        self.signals_total = Counter("arb_signals_total", "Number of emitted signals", ["type"])
        self.trades_total = Counter("arb_trades_total", "Number of executed trades", ["type"])
        self.edge_histogram = Histogram("arb_edge_bps_histogram", "Observed edge in bps", buckets=(10, 25, 50, 75, 100, 200, 400, 800))
        self.pnl_cum = Gauge("arb_pnl_cum", "Cumulative PnL")
        self.inventory_usd = Gauge("arb_inventory_usd", "Inventory in USD")
        self.rejections_total = Counter("arb_rejections_total", "Signals rejected by reason", ["reason"])
        self.ws_staleness = Gauge("arb_ws_staleness_ms", "Order book staleness in ms")
        self.partial_fills = Counter("arb_router_partialfills_total", "Number of partial fills detected")

    def start(self, port: int) -> None:
        start_http_server(port)

    def observe_signal(self, signal_type: str, edge_bps: int) -> None:
        self.signals_total.labels(type=signal_type).inc()
        self.edge_histogram.observe(edge_bps)

    def observe_trade(self, signal_type: str) -> None:
        self.trades_total.labels(type=signal_type).inc()

    def reject(self, reason: str) -> None:
        self.rejections_total.labels(reason=reason).inc()

    def update_ws_staleness(self, value: float) -> None:
        self.ws_staleness.set(value)

    def update_inventory(self, value: float) -> None:
        self.inventory_usd.set(value)

    def update_pnl(self, value: float) -> None:
        self.pnl_cum.set(value)

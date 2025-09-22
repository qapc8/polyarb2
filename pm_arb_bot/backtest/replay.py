"""NDJSON replay backtester."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import List, Sequence

from ..data.discovery import DiscoveryState
from ..types import BookSnapshot, Level, Side
from .fillsim import simulate_fill


def load_snapshots(path: Path | str) -> List[BookSnapshot]:
    snapshots: List[BookSnapshot] = []
    with Path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            payload = json.loads(line)
            snapshots.append(
                BookSnapshot(
                    market_id=payload["market_id"],
                    ts=payload["ts"],
                    bids=[Level(**lvl) for lvl in payload.get("bids", [])],
                    asks=[Level(**lvl) for lvl in payload.get("asks", [])],
                )
            )
    return snapshots


class ReplayBacktester:
    def __init__(
        self,
        discovery_state: DiscoveryState,
        strategy,
        risk_engine,
        *,
        slippage_bps: int,
    ) -> None:
        self._discovery_state = discovery_state
        self._strategy = strategy
        self._risk = risk_engine
        self._slippage_bps = slippage_bps

    def run(self, snapshots: Sequence[BookSnapshot]) -> List[dict]:
        books: dict[str, BookSnapshot] = {}
        trades: List[dict] = []
        for snapshot in snapshots:
            books[snapshot.market_id] = snapshot
            signals = self._strategy.generate_signals(books, self._discovery_state, self._risk, snapshot.ts)
            for signal in signals:
                if not signal.legs:
                    continue
                fills = []
                executed = True
                for leg in signal.legs:
                    book = books.get(leg.market_id)
                    if not book:
                        executed = False
                        break
                    levels = book.asks if leg.side == Side.BUY else book.bids
                    avg_price, filled_size = simulate_fill(levels, leg.size, leg.side, self._slippage_bps)
                    if filled_size < leg.size:
                        executed = False
                        break
                    fills.append((leg.market_id, avg_price, filled_size, leg.side.value))
                if executed:
                    pnl = (signal.edge_bps / 10_000.0) * signal.size
                    trades.append(
                        {
                            "trade_id": f"{signal.id}",
                            "ts": snapshot.ts,
                            "strategy": signal.type.value,
                            "size": signal.size,
                            "edge_bps": signal.edge_bps,
                            "pnl": pnl,
                            "fills": fills,
                        }
                    )
                    self._risk.release_signal(signal.id)
        return trades

    def to_csv(self, trades: Sequence[dict], path: Path | str) -> None:
        if not trades:
            return
        fieldnames = ["trade_id", "ts", "strategy", "size", "edge_bps", "pnl"]
        with Path(path).open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for trade in trades:
                writer.writerow({field: trade.get(field) for field in fieldnames})

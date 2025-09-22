"""Lightweight websocket stream abstraction for CLOB books."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, Optional

import websockets

from ..settings import Settings
from ..types import BookSnapshot, Level, Side
from ..utils.logging import get_logger
from ..utils.math import vwap_for_size
from ..utils.time import now_ms

Logger = get_logger(__name__)


@dataclass(slots=True)
class OrderBook:
    market_id: str
    snapshot: Optional[BookSnapshot] = None

    def update(self, snapshot: BookSnapshot) -> None:
        # enforce depth sorted order
        bids = sorted(snapshot.bids, key=lambda lvl: lvl.price, reverse=True)
        asks = sorted(snapshot.asks, key=lambda lvl: lvl.price)
        self.snapshot = BookSnapshot(
            market_id=snapshot.market_id,
            ts=snapshot.ts,
            bids=bids,
            asks=asks,
        )

    def best_bid(self) -> Optional[Level]:
        if not self.snapshot:
            return None
        return self.snapshot.best_bid()

    def best_ask(self) -> Optional[Level]:
        if not self.snapshot:
            return None
        return self.snapshot.best_ask()

    def vwap(self, side: Side, size: float) -> tuple[float | None, float]:
        if not self.snapshot:
            return (None, 0.0)
        levels = self.snapshot.bids if side == Side.SELL else self.snapshot.asks
        return vwap_for_size(levels, size)

    def age_ms(self) -> int:
        if not self.snapshot:
            return 1_000_000
        return max(0, now_ms() - self.snapshot.ts)


class BookStream:
    """Maintain in-memory L2 books from websocket updates."""

    def __init__(self, settings: Settings, depth: int = 10) -> None:
        self._settings = settings
        self._depth = depth
        self._books: Dict[str, OrderBook] = {}
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._lock = asyncio.Lock()

    def get_book(self, market_id: str) -> Optional[OrderBook]:
        return self._books.get(market_id)

    def ingest_snapshot(self, snapshot: BookSnapshot) -> None:
        book = self._books.setdefault(snapshot.market_id, OrderBook(snapshot.market_id))
        truncated = BookSnapshot(
            market_id=snapshot.market_id,
            ts=snapshot.ts,
            bids=snapshot.bids[: self._depth],
            asks=snapshot.asks[: self._depth],
        )
        book.update(truncated)

    async def run(self, market_ids: Iterable[str], on_update: Optional[Callable[[BookSnapshot], None]] = None) -> None:
        """Connect to the websocket and maintain books for ``market_ids``."""

        payload = {"type": "subscribe", "markets": list(market_ids)}
        async with websockets.connect(self._settings.polymarket.clob_ws_url, ping_interval=None) as ws:
            self._ws = ws
            await ws.send(json.dumps(payload))
            Logger.info("ws_subscribed", markets=len(payload["markets"]))
            async for message in ws:
                data = json.loads(message)
                if data.get("type") == "l2":
                    snapshot = BookSnapshot(
                        market_id=data["market_id"],
                        ts=data.get("ts", now_ms()),
                        bids=[Level(**lvl) for lvl in data.get("bids", [])],
                        asks=[Level(**lvl) for lvl in data.get("asks", [])],
                    )
                    self.ingest_snapshot(snapshot)
                    if on_update:
                        on_update(snapshot)
                elif data.get("type") == "heartbeat":
                    Logger.debug("ws_heartbeat", ts=data.get("ts"))
                else:
                    Logger.debug("ws_message", payload=data)

    async def close(self) -> None:
        if self._ws and not self._ws.closed:
            await self._ws.close()

    def staleness_ms(self, market_id: str) -> Optional[int]:
        book = self.get_book(market_id)
        if not book:
            return None
        return book.age_ms()

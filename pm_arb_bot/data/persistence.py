"""SQLite persistence layer."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import aiosqlite

from ..types import BookSnapshot, OrderAck, Signal

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    neg_risk INTEGER NOT NULL,
    rules_hash TEXT NOT NULL,
    last_clarified_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS markets (
    market_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    outcome TEXT NOT NULL,
    tick REAL NOT NULL,
    min_size REAL NOT NULL,
    status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS books (
    market_id TEXT NOT NULL,
    ts INTEGER NOT NULL,
    side TEXT NOT NULL,
    price REAL NOT NULL,
    size REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_books_market_ts ON books(market_id, ts);
CREATE TABLE IF NOT EXISTS signals (
    id TEXT PRIMARY KEY,
    ts INTEGER NOT NULL,
    type TEXT NOT NULL,
    edge_bps INTEGER NOT NULL,
    size REAL NOT NULL,
    reason TEXT NOT NULL,
    event_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_signals_event_ts ON signals(event_id, ts);
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    ts INTEGER NOT NULL,
    batch_id TEXT,
    market_id TEXT NOT NULL,
    side TEXT NOT NULL,
    price REAL NOT NULL,
    size REAL NOT NULL,
    tif TEXT NOT NULL,
    status TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_orders_market_ts ON orders(market_id, ts);
CREATE TABLE IF NOT EXISTS fills (
    order_id TEXT NOT NULL,
    ts INTEGER NOT NULL,
    price REAL NOT NULL,
    size REAL NOT NULL,
    fee REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS pnl (
    ts INTEGER PRIMARY KEY,
    realized REAL NOT NULL,
    unrealized REAL NOT NULL
);
"""


class Persistence:
    def __init__(self, dsn: str) -> None:
        if not dsn.startswith("sqlite"):
            raise ValueError("Only sqlite DSNs are supported")
        _, _, path = dsn.partition("///")
        if not path:
            raise ValueError("Invalid SQLite DSN")
        self._path = Path(path)
        self._conn: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def record_signal(self, signal: Signal, ts_ms: int) -> None:
        if not self._conn:
            raise RuntimeError("Persistence not initialized")
        async with self._lock:
            await self._conn.execute(
                "INSERT OR REPLACE INTO signals(id, ts, type, edge_bps, size, reason, event_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    signal.id,
                    ts_ms,
                    signal.type.value,
                    signal.edge_bps,
                    signal.size,
                    signal.reason,
                    signal.event_id,
                ),
            )
            await self._conn.commit()

    async def record_order(self, ack: OrderAck, ts_ms: int, batch_id: Optional[str] = None) -> None:
        if not self._conn:
            raise RuntimeError("Persistence not initialized")
        async with self._lock:
            await self._conn.execute(
                """
                INSERT OR REPLACE INTO orders(id, ts, batch_id, market_id, side, price, size, tif, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ack.order_id,
                    ts_ms,
                    batch_id,
                    ack.intent.market_id,
                    ack.intent.side.value,
                    ack.intent.price,
                    ack.intent.size,
                    ack.intent.tif.value,
                    ack.status.value,
                ),
            )
            await self._conn.commit()

    async def record_book(self, snapshot: BookSnapshot) -> None:
        if not self._conn:
            raise RuntimeError("Persistence not initialized")
        async with self._lock:
            await self._conn.execute("DELETE FROM books WHERE market_id = ? AND ts = ?", (snapshot.market_id, snapshot.ts))
            entries = [
                (snapshot.market_id, snapshot.ts, "bid", level.price, level.size)
                for level in snapshot.bids
            ] + [
                (snapshot.market_id, snapshot.ts, "ask", level.price, level.size)
                for level in snapshot.asks
            ]
            await self._conn.executemany(
                "INSERT INTO books(market_id, ts, side, price, size) VALUES (?, ?, ?, ?, ?)", entries
            )
            await self._conn.commit()

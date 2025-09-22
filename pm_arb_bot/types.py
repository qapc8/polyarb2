"""Core data types shared across the arbitrage bot."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, List, Optional
from uuid import uuid4


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class TimeInForce(str, Enum):
    FOK = "FOK"
    IOC = "IOC"
    GTC = "GTC"


class SignalType(str, Enum):
    PARITY = "PARITY"
    BASKET = "BASKET"
    RESOLUTION_SNIPE = "RES_SNIPE"


class OrderStatus(str, Enum):
    ACCEPTED = "accepted"
    FILLED = "filled"
    PARTIAL = "partial"
    REJECTED = "rejected"
    CANCELED = "canceled"


@dataclass(slots=True)
class Level:
    price: float
    size: float


@dataclass(slots=True)
class BookSnapshot:
    market_id: str
    ts: int
    bids: List[Level] = field(default_factory=list)
    asks: List[Level] = field(default_factory=list)

    def best_bid(self) -> Optional[Level]:
        return self.bids[0] if self.bids else None

    def best_ask(self) -> Optional[Level]:
        return self.asks[0] if self.asks else None

    def side(self, side: Side) -> List[Level]:
        return self.bids if side == Side.SELL else self.asks


@dataclass(slots=True)
class OrderIntent:
    market_id: str
    side: Side
    price: float
    size: float
    tif: TimeInForce = TimeInForce.FOK
    post_only: bool = False

    def notional(self) -> float:
        return self.price * self.size


@dataclass(slots=True)
class Signal:
    id: str
    type: SignalType
    edge_bps: int
    size: float
    legs: List[OrderIntent]
    reason: str
    event_id: Optional[str] = None

    @classmethod
    def new(
        cls,
        signal_type: SignalType,
        edge_bps: int,
        size: float,
        legs: Iterable[OrderIntent],
        reason: str,
        event_id: Optional[str] = None,
    ) -> "Signal":
        return cls(
            id=str(uuid4()),
            type=signal_type,
            edge_bps=edge_bps,
            size=size,
            legs=list(legs),
            reason=reason,
            event_id=event_id,
        )


@dataclass(slots=True)
class OrderAck:
    order_id: str
    intent: OrderIntent
    status: OrderStatus
    filled_size: float = 0.0
    avg_price: Optional[float] = None

    def is_filled(self) -> bool:
        return self.status == OrderStatus.FILLED and abs(self.filled_size - self.intent.size) < 1e-9

    def is_partial(self) -> bool:
        return self.status in {OrderStatus.PARTIAL, OrderStatus.ACCEPTED} and 0 < self.filled_size < self.intent.size


@dataclass(slots=True)
class Fill:
    order_id: str
    price: float
    size: float
    fee: float = 0.0


@dataclass(slots=True)
class Position:
    market_id: str
    size: float
    average_price: float


@dataclass(slots=True)
class PnL:
    ts: int
    realized: float
    unrealized: float


@dataclass(slots=True)
class RiskLimits:
    max_notional_per_market: float
    max_notional_per_event: float
    max_concurrent_signals: int
    kill_on_ws_stale_ms: int

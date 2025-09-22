"""Market discovery utilities."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

import httpx

from ..settings import Settings
from ..utils.time import now_ms
from .schemas import EventSchema, MarketSchema, OutcomeSchema


_PLACEHOLDER_TOKENS = {"tbd", "other", "placeholder", "invalid", "null"}


@dataclass(slots=True)
class OutcomeInfo:
    outcome_id: str
    name: str
    is_placeholder: bool = False

    @classmethod
    def from_schema(cls, schema: OutcomeSchema) -> "OutcomeInfo":
        is_placeholder = schema.is_placeholder or any(token in schema.name.lower() for token in _PLACEHOLDER_TOKENS)
        return cls(outcome_id=schema.outcome_id, name=schema.name, is_placeholder=is_placeholder)


@dataclass(slots=True)
class MarketInfo:
    market_id: str
    event_id: str
    outcome: str
    tick_size: float
    min_size: float
    status: str

    @classmethod
    def from_schema(cls, schema: MarketSchema) -> "MarketInfo":
        return cls(
            market_id=schema.market_id,
            event_id=schema.event_id,
            outcome=schema.outcome,
            tick_size=schema.tick_size,
            min_size=schema.min_size,
            status=schema.status,
        )

    def is_yes(self) -> bool:
        return self.outcome.upper() == "YES"

    def is_no(self) -> bool:
        return self.outcome.upper() == "NO"


@dataclass(slots=True)
class EventInfo:
    event_id: str
    title: str
    neg_risk: bool
    outcomes: List[OutcomeInfo]
    rules_text: str
    status: str
    last_clarified_at: int
    rules_hash: str

    @classmethod
    def from_schema(cls, schema: EventSchema) -> "EventInfo":
        outcomes = [OutcomeInfo.from_schema(outcome) for outcome in schema.outcomes]
        neg_risk = _is_neg_risk_event(schema, outcomes)
        rules_text = schema.rules_text or ""
        rules_hash = hashlib.sha256(rules_text.encode("utf-8")).hexdigest()
        last_clarified = int(schema.last_clarified_at.timestamp() * 1000) if schema.last_clarified_at else now_ms()
        return cls(
            event_id=schema.event_id,
            title=schema.title,
            neg_risk=neg_risk,
            outcomes=outcomes,
            rules_text=rules_text,
            status=schema.status,
            last_clarified_at=last_clarified,
            rules_hash=rules_hash,
        )


@dataclass
class DiscoveryState:
    events: Dict[str, EventInfo] = field(default_factory=dict)
    markets: Dict[str, MarketInfo] = field(default_factory=dict)

    def get_event(self, event_id: str) -> Optional[EventInfo]:
        return self.events.get(event_id)

    def get_market(self, market_id: str) -> Optional[MarketInfo]:
        return self.markets.get(market_id)

    def markets_for_event(self, event_id: str) -> List[MarketInfo]:
        return [m for m in self.markets.values() if m.event_id == event_id]

    def iter_yes_no_pairs(self) -> Iterable[Tuple[MarketInfo, MarketInfo]]:
        for event in self.events.values():
            yes = [m for m in self.markets_for_event(event.event_id) if m.is_yes() and m.status == "open"]
            no = [m for m in self.markets_for_event(event.event_id) if m.is_no() and m.status == "open"]
            for y in yes:
                for n in no:
                    if y.market_id != n.market_id:
                        yield y, n

    def iter_basket_events(self) -> Iterable[EventInfo]:
        for event in self.events.values():
            if event.neg_risk:
                yield event

    def event_for_market(self, market_id: str) -> Optional[EventInfo]:
        market = self.get_market(market_id)
        if not market:
            return None
        return self.get_event(market.event_id)

    def update(self, events: Iterable[EventInfo], markets: Iterable[MarketInfo]) -> None:
        for event in events:
            self.events[event.event_id] = event
        for market in markets:
            self.markets[market.market_id] = market


def _is_neg_risk_event(schema: EventSchema, outcomes: List[OutcomeInfo]) -> bool:
    named_outcomes = [o for o in outcomes if not o.is_placeholder]
    if len(named_outcomes) < 2:
        return False
    return schema.status.lower() == "open"


class DiscoveryService:
    """Fetch and track events/markets from the Polymarket catalog."""

    def __init__(self, settings: Settings, client: Optional[httpx.AsyncClient] = None) -> None:
        self._settings = settings
        timeout = httpx.Timeout(settings.polymarket.read_timeout_s)
        self._client = client or httpx.AsyncClient(base_url=settings.polymarket.markets_api_base, timeout=timeout)
        self.state = DiscoveryState()

    async def close(self) -> None:
        await self._client.aclose()

    async def refresh(self) -> DiscoveryState:
        events_data, markets_data = await asyncio.gather(self._fetch_events(), self._fetch_markets())
        events = [EventInfo.from_schema(event) for event in events_data]
        markets = [MarketInfo.from_schema(market) for market in markets_data]
        self.state.update(events, markets)
        return self.state

    async def _fetch_events(self) -> List[EventSchema]:
        resp = await self._client.get("/events")
        resp.raise_for_status()
        payload = resp.json()
        events_raw = payload.get("events", payload)
        return [EventSchema.model_validate(event) for event in events_raw]

    async def _fetch_markets(self) -> List[MarketSchema]:
        resp = await self._client.get("/markets")
        resp.raise_for_status()
        payload = resp.json()
        markets_raw = payload.get("markets", payload)
        return [MarketSchema.model_validate(market) for market in markets_raw]


def build_state(events: Iterable[EventSchema], markets: Iterable[MarketSchema]) -> DiscoveryState:
    state = DiscoveryState()
    state.update([EventInfo.from_schema(event) for event in events], [MarketInfo.from_schema(market) for market in markets])
    return state

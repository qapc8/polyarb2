"""Pydantic models representing discovery and market structures."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class OutcomeSchema(BaseModel):
    outcome_id: str = Field(alias="id")
    name: str
    is_placeholder: bool = False

    model_config = {
        "populate_by_name": True,
    }


class MarketSchema(BaseModel):
    market_id: str = Field(alias="id")
    event_id: str
    outcome: str
    tick_size: float = 0.01
    min_size: float = 1.0
    status: str = "open"

    model_config = {
        "populate_by_name": True,
    }


class EventSchema(BaseModel):
    event_id: str = Field(alias="id")
    title: str
    neg_risk: bool = False
    outcomes: List[OutcomeSchema] = Field(default_factory=list)
    rules_text: str = ""
    status: str = "open"
    last_clarified_at: Optional[datetime] = None

    model_config = {
        "populate_by_name": True,
    }


class BookLevelSchema(BaseModel):
    price: float
    size: float


class BookSnapshotSchema(BaseModel):
    market_id: str
    ts: int
    bids: List[BookLevelSchema]
    asks: List[BookLevelSchema]


class SignalSchema(BaseModel):
    id: str
    type: str
    edge_bps: int
    size: float
    reason: str
    event_id: Optional[str]


class RiskLimitsSchema(BaseModel):
    max_notional_per_market: float
    max_notional_per_event: float
    max_concurrent_signals: int
    kill_on_ws_stale_ms: int

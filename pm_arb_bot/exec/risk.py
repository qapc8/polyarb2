"""Risk management helpers."""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, Optional

from ..data.discovery import DiscoveryState
from ..types import RiskLimits, Signal, SignalType
from ..utils.time import now_ms


@dataclass
class ActiveSignal:
    event_id: str
    legs: Iterable[tuple[str, float]]
    notional: float


class RiskEngine:
    def __init__(
        self,
        limits: RiskLimits,
        *,
        reentry_threshold_bps: int,
        resolution_guard_minutes: int,
    ) -> None:
        self._limits = limits
        self._market_notional: Dict[str, float] = defaultdict(float)
        self._event_notional: Dict[str, float] = defaultdict(float)
        self._active_signals: Dict[str, ActiveSignal] = {}
        self._cooldowns: Dict[str, tuple[int, int]] = {}
        self._last_ws_heartbeat = now_ms()
        self._discovery_state: Optional[DiscoveryState] = None
        self._resolution_guard_ms = resolution_guard_minutes * 60 * 1000
        self._reentry_threshold_bps = reentry_threshold_bps

    def set_discovery_state(self, state: DiscoveryState) -> None:
        self._discovery_state = state

    def update_ws_heartbeat(self, ts_ms: Optional[int] = None) -> None:
        self._last_ws_heartbeat = ts_ms or now_ms()

    def is_killed(self, now_ms_value: Optional[int] = None) -> bool:
        ts = now_ms_value or now_ms()
        if os.getenv("ARB_KILL") == "1":
            return True
        return ts - self._last_ws_heartbeat > self._limits.kill_on_ws_stale_ms

    def allow_signal(self, signal: Signal, *, event_id: Optional[str], now_ms: int) -> bool:
        if self.is_killed(now_ms):
            return False
        if event_id is None:
            return False
        if len(self._active_signals) >= self._limits.max_concurrent_signals:
            return False
        if self._discovery_state:
            event = self._discovery_state.get_event(event_id)
            if event and signal.type != SignalType.RESOLUTION_SNIPE:
                elapsed = max(0, now_ms - event.last_clarified_at)
                if elapsed < self._resolution_guard_ms:
                    return False
        additional = sum(abs(leg.notional()) for leg in signal.legs)
        if self._event_notional[event_id] + additional >= self._limits.max_notional_per_event:
            return False
        for leg in signal.legs:
            market_notional = self._market_notional[leg.market_id] + abs(leg.notional())
            if market_notional >= self._limits.max_notional_per_market:
                return False
        key = self._signal_key(signal, event_id)
        last_entry = self._cooldowns.get(key)
        if last_entry and signal.edge_bps - last_entry[0] < self._reentry_threshold_bps:
            return False
        self._register(signal, event_id, additional)
        self._cooldowns[key] = (signal.edge_bps, now_ms)
        return True

    def release_signal(self, signal_id: str) -> None:
        active = self._active_signals.pop(signal_id, None)
        if not active:
            return
        self._event_notional[active.event_id] = max(0.0, self._event_notional[active.event_id] - active.notional)
        for market_id, amount in active.legs:
            self._market_notional[market_id] = max(0.0, self._market_notional[market_id] - amount)

    def _register(self, signal: Signal, event_id: str, notional: float) -> None:
        self._event_notional[event_id] += notional
        legs_payload = []
        for leg in signal.legs:
            amount = abs(leg.notional())
            self._market_notional[leg.market_id] += amount
            legs_payload.append((leg.market_id, amount))
        self._active_signals[signal.id] = ActiveSignal(event_id=event_id, legs=legs_payload, notional=notional)

    def _signal_key(self, signal: Signal, event_id: str) -> str:
        legs_repr = tuple(sorted((leg.market_id, leg.side.value, round(leg.price, 4)) for leg in signal.legs))
        return f"{event_id}:{legs_repr}"

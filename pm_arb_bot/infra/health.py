"""Simple health monitoring utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..utils.time import now_ms


@dataclass
class Heartbeat:
    name: str
    last_seen_ms: int


class HealthMonitor:
    def __init__(self) -> None:
        self._heartbeats: dict[str, Heartbeat] = {}

    def beat(self, name: str, ts_ms: Optional[int] = None) -> None:
        self._heartbeats[name] = Heartbeat(name=name, last_seen_ms=ts_ms or now_ms())

    def stale(self, name: str, threshold_ms: int, now_ms_value: Optional[int] = None) -> bool:
        hb = self._heartbeats.get(name)
        if not hb:
            return True
        current = now_ms_value or now_ms()
        return current - hb.last_seen_ms > threshold_ms

    def snapshot(self) -> dict[str, int]:
        return {name: hb.last_seen_ms for name, hb in self._heartbeats.items()}

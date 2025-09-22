"""Execution router coordinating atomic batches."""

from __future__ import annotations

import uuid
from typing import Iterable, List, Optional, Tuple

from ..data.rest import RestClient
from ..data.persistence import Persistence
from ..types import OrderAck, OrderIntent, OrderStatus, Side, TimeInForce
from ..utils.logging import get_logger
from ..utils.time import now_ms


class Router:
    def __init__(
        self,
        rest_client: RestClient,
        *,
        persistence: Optional[Persistence] = None,
    ) -> None:
        self._rest = rest_client
        self._persistence = persistence
        self._logger = get_logger(__name__)

    async def place_atomic_batch(
        self,
        legs: Iterable[OrderIntent],
        timeout_ms: int = 1_000,
    ) -> Tuple[bool, List[OrderAck]]:
        batch_id = str(uuid.uuid4())
        intents = list(legs)
        if not intents:
            return True, []
        self._logger.info("router_submit", batch_id=batch_id, legs=len(intents))
        acks = await self._rest.submit_batch(intents)
        await self._persist_orders(acks, batch_id)
        success = self._all_filled(acks)
        if success:
            self._logger.info("router_batch_filled", batch_id=batch_id)
            return True, acks

        self._logger.warning("router_partial", batch_id=batch_id)
        await self._cancel_unfilled(acks)
        flatten_orders = self._build_flatten_orders(acks)
        if flatten_orders:
            flatten_acks = await self._rest.submit_batch(flatten_orders)
            await self._persist_orders(flatten_acks, f"flatten-{batch_id}")
        return False, acks

    async def _persist_orders(self, acks: Iterable[OrderAck], batch_id: str) -> None:
        if not self._persistence:
            return
        ts_ms = now_ms()
        for ack in acks:
            await self._persistence.record_order(ack, ts_ms, batch_id=batch_id)

    async def _cancel_unfilled(self, acks: Iterable[OrderAck]) -> None:
        pending_ids = [ack.order_id for ack in acks if ack.status not in {OrderStatus.FILLED, OrderStatus.CANCELED}]
        if pending_ids:
            await self._rest.cancel_orders(pending_ids)

    def _all_filled(self, acks: Iterable[OrderAck]) -> bool:
        return all(ack.is_filled() for ack in acks)

    def _build_flatten_orders(self, acks: Iterable[OrderAck]) -> List[OrderIntent]:
        flatten: List[OrderIntent] = []
        for ack in acks:
            filled = ack.filled_size or 0.0
            if filled <= 0:
                continue
            flatten_side = Side.SELL if ack.intent.side == Side.BUY else Side.BUY
            price = 0.0 if flatten_side == Side.SELL else 1.0
            flatten.append(
                OrderIntent(
                    market_id=ack.intent.market_id,
                    side=flatten_side,
                    price=price,
                    size=filled,
                    tif=TimeInForce.IOC,
                    post_only=False,
                )
            )
        return flatten

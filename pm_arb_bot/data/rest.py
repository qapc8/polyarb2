"""REST client for interacting with the Polymarket CLOB."""

from __future__ import annotations

import uuid
from typing import Iterable, List, Optional

import httpx

from ..settings import Settings
from ..types import OrderAck, OrderIntent, OrderStatus
from ..utils.logging import get_logger


class RestClient:
    """Minimal REST client with dry-run support."""

    def __init__(
        self,
        settings: Settings,
        *,
        dry_run: bool = True,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._settings = settings
        self._dry_run = dry_run
        timeout = httpx.Timeout(settings.polymarket.write_timeout_s)
        headers = {}
        if settings.polymarket.api_key:
            headers["Authorization"] = f"Bearer {settings.polymarket.api_key}"
        self._client = client or httpx.AsyncClient(base_url=settings.polymarket.clob_rest_base, timeout=timeout, headers=headers)
        self._logger = get_logger(__name__)

    async def close(self) -> None:
        await self._client.aclose()

    async def submit_batch(self, intents: Iterable[OrderIntent]) -> List[OrderAck]:
        intents_list = list(intents)
        if self._dry_run:
            acks = [
                OrderAck(
                    order_id=f"dry-{uuid.uuid4()}",
                    intent=intent,
                    status=OrderStatus.FILLED,
                    filled_size=intent.size,
                    avg_price=intent.price,
                )
                for intent in intents_list
            ]
            self._logger.info("dry_run_batch", legs=len(intents_list))
            return acks

        payload = [
            {
                "marketId": intent.market_id,
                "side": intent.side.value,
                "price": intent.price,
                "size": intent.size,
                "tif": intent.tif.value,
                "postOnly": intent.post_only,
                "clientOrderId": str(uuid.uuid4()),
            }
            for intent in intents_list
        ]
        response = await self._client.post("/orders/batch", json={"orders": payload})
        response.raise_for_status()
        data = response.json()
        orders = data.get("orders", data)
        return [self._parse_order_ack(intent, raw) for intent, raw in zip(intents_list, orders)]

    async def cancel_orders(self, order_ids: Iterable[str]) -> None:
        ids = list(order_ids)
        if not ids:
            return
        if self._dry_run:
            self._logger.info("dry_run_cancel", count=len(ids))
            return
        await self._client.post("/orders/cancel", json={"orderIds": ids})

    async def fetch_balances(self) -> dict:
        if self._dry_run:
            return {"dry_run": True}
        resp = await self._client.get("/balances")
        resp.raise_for_status()
        return resp.json()

    async def fetch_positions(self) -> dict:
        if self._dry_run:
            return {"dry_run": True}
        resp = await self._client.get("/positions")
        resp.raise_for_status()
        return resp.json()

    async def ping(self) -> bool:
        if self._dry_run:
            return True
        try:
            resp = await self._client.get("/ping")
            resp.raise_for_status()
        except httpx.HTTPError:
            return False
        return True

    def _parse_order_ack(self, intent: OrderIntent, payload: dict) -> OrderAck:
        status_raw = str(payload.get("status", "accepted")).lower()
        try:
            status = OrderStatus(status_raw)
        except ValueError:
            status = OrderStatus.ACCEPTED
        filled = float(payload.get("filledSize", 0.0))
        price = float(payload.get("avgPrice", intent.price)) if payload.get("avgPrice") is not None else None
        return OrderAck(
            order_id=str(payload.get("orderId", uuid.uuid4())),
            intent=intent,
            status=status,
            filled_size=filled,
            avg_price=price,
        )

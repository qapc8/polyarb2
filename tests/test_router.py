from __future__ import annotations

import pytest

from pm_arb_bot.exec.router import Router
from pm_arb_bot.types import OrderAck, OrderIntent, OrderStatus, Side, TimeInForce


class FakeRestClient:
    def __init__(self) -> None:
        self.submitted: list[list[OrderIntent]] = []
        self.canceled: list[list[str]] = []

    async def submit_batch(self, intents):
        intents = list(intents)
        self.submitted.append(intents)
        if len(self.submitted) == 1:
            primary_acks = [
                OrderAck(
                    order_id="ord-1",
                    intent=intents[0],
                    status=OrderStatus.FILLED,
                    filled_size=intents[0].size,
                    avg_price=intents[0].price,
                ),
                OrderAck(
                    order_id="ord-2",
                    intent=intents[1],
                    status=OrderStatus.PARTIAL,
                    filled_size=intents[1].size / 2,
                    avg_price=intents[1].price,
                ),
            ]
            return primary_acks
        flatten_acks = [
            OrderAck(
                order_id=f"flatten-{idx}",
                intent=intent,
                status=OrderStatus.FILLED,
                filled_size=intent.size,
                avg_price=intent.price,
            )
            for idx, intent in enumerate(intents)
        ]
        return flatten_acks

    async def cancel_orders(self, order_ids):
        self.canceled.append(list(order_ids))


@pytest.mark.asyncio
async def test_router_cancels_and_flattens_on_partial():
    rest = FakeRestClient()
    router = Router(rest)
    legs = [
        OrderIntent(market_id="m1", side=Side.BUY, price=0.5, size=100.0, tif=TimeInForce.FOK, post_only=False),
        OrderIntent(market_id="m2", side=Side.BUY, price=0.5, size=100.0, tif=TimeInForce.FOK, post_only=False),
    ]
    success, acks = await router.place_atomic_batch(legs)
    assert not success
    assert rest.canceled == [["ord-2"]]
    assert len(rest.submitted) == 2  # primary + flatten
    flatten_orders = rest.submitted[1]
    assert any(intent.side == Side.SELL for intent in flatten_orders)
    assert all(intent.tif == TimeInForce.IOC for intent in flatten_orders)
    sizes = sorted(intent.size for intent in flatten_orders)
    assert sizes == [50.0, 100.0]

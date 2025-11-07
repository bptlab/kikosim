#!/usr/bin/env python3
"""
Seller agent for OrderManagement (ordermanagement_new).

Very simple behavior:
- On order: sends invoice to Buyer and delivery_req to Logistics
- On pay: logs (no further action here)
- On cancel_req: sends cancel_ack
- On confirm: logs final outcome
"""

from bspl.adapter import Adapter
from configuration import systems, agents
from OrderManagement import (
    order, reject, invoice, pay, cancel_req, cancel_ack, delivery_req, confirm
)
from simple_logging import setup_logger

log = setup_logger("seller")
adapter = Adapter("Seller", systems, agents)

# Deferred send wrappers (single-arg for RA deferral)
async def send_invoice(message: invoice):
    await adapter.send(message)

async def send_delivery_req(message: delivery_req):
    await adapter.send(message)

async def send_cancel_ack(message: cancel_ack):
    await adapter.send(message)


@adapter.reaction(order)
async def on_order(msg):
    oid = msg["id"]
    item = msg["item"]

    # Simple policy: never reject; always invoice and request delivery
    inv = invoice(id=oid, price=100)
    await send_invoice(inv)
    log.info(f"SENT invoice: id={oid}, price=100")

    dreq = delivery_req(id=oid, item=item, delivery_req=f"DREQ_{oid}")
    await send_delivery_req(dreq)
    log.info(f"SENT delivery_req: id={oid}, item={item}")
    return msg


@adapter.reaction(pay)
async def on_pay(msg):
    oid = msg["id"]
    pref = msg["payment_ref"]
    log.info(f"RECEIVED pay: id={oid}, payment_ref={pref}")
    return msg


@adapter.reaction(cancel_req)
async def on_cancel_req(msg):
    oid = msg["id"]
    rescind = msg["rescind"]
    ack = cancel_ack(id=oid, rescind=rescind, outcome="CANCELLED")
    await send_cancel_ack(ack)
    log.info(f"SENT cancel_ack: id={oid}, outcome=CANCELLED")
    return msg


@adapter.reaction(confirm)
async def on_confirm(msg):
    oid = msg["id"]
    outcome = msg["outcome"]
    log.info(f"RECEIVED confirm: id={oid}, outcome={outcome}")
    return msg


if __name__ == "__main__":
    log.info("Seller STARTING...")
    try:
        adapter.start()
    except KeyboardInterrupt:
        log.info("Seller INTERRUPTED")
    except Exception as e:
        log.error(f"Seller CRASHED: {e}")
        import traceback; traceback.print_exc()
    finally:
        log.info("Seller ENDING...")

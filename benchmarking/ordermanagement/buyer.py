#!/usr/bin/env python3
"""
Buyer agent for OrderManagement (ordermanagement_new).

Very simple behavior:
- Initiates an order (optional initiator for demos)
- On invoice: sends pay
- On deliver: sends confirm (using stored payment_ref)
- On reject/cancel_ack: logs and does nothing further
"""

import uuid
from bspl.adapter import Adapter
from configuration import systems, agents
from OrderManagement import (
    order, invoice, reject, pay, cancel_req, cancel_ack, deliver, confirm
)
from simple_logging import setup_logger

log = setup_logger("buyer")
adapter = Adapter("Buyer", systems, agents)

# Deferred send wrappers (single-arg for RA deferral)
async def send_order(message: order):
    await adapter.send(message)

async def send_pay(message: pay):
    await adapter.send(message)

async def send_confirm(message: confirm):
    await adapter.send(message)


def _find_payment_ref(oid: str) -> str | None:
    for m in adapter.history.messages(pay):
        if m["id"] == oid:
            return m["payment_ref"]
    return None


@adapter.reaction(invoice)
async def on_invoice(msg):
    """Pay upon receiving an invoice."""
    oid = msg["id"]
    price = msg["price"]
    pref = f"PAY_{uuid.uuid4().hex[:8]}"
    p = pay(id=oid, price=price, payment_ref=pref)
    await send_pay(p)
    log.info(f"SENT pay: id={oid}, price={price}, payment_ref={pref}")
    return msg


@adapter.reaction(deliver)
async def on_deliver(msg):
    """Confirm reception after delivery (uses previously sent payment_ref)."""
    oid = msg["id"]
    ddate = msg["delivery_date"]
    pref = _find_payment_ref(oid)
    c = confirm(id=oid, payment_ref=pref, delivery_date=ddate, outcome="DELIVERED")
    await send_confirm(c)
    log.info(f"SENT confirm: id={oid}, payment_ref={pref}, delivery_date={ddate}, outcome=DELIVERED")
    return msg


@adapter.reaction(reject)
async def on_reject(msg):
    """Handle rejection (no follow-up)."""
    oid = msg["id"]
    outcome = msg["outcome"]
    log.info(f"RECEIVED reject: id={oid}, outcome={outcome}")
    return msg


@adapter.reaction(cancel_ack)
async def on_cancel_ack(msg):
    """Handle cancellation acknowledgement (no follow-up)."""
    oid = msg["id"]
    outcome = msg["outcome"]
    log.info(f"RECEIVED cancel_ack: id={oid}, outcome={outcome}")
    return msg


# Optional: simple initiator to place an example order when run directly
async def initiator():
    oid = f"ORD_{uuid.uuid4().hex[:8]}"
    item = "widget"
    o = order(id=oid, item=item)
    await send_order(o)
    log.info(f"SENT order: id={oid}, item={item}")


if __name__ == "__main__":
    log.info("Buyer STARTING...")
    try:
        adapter.start()
    except KeyboardInterrupt:
        log.info("Buyer INTERRUPTED")
    except Exception as e:
        log.error(f"Buyer CRASHED: {e}")
        import traceback; traceback.print_exc()
    finally:
        log.info("Buyer ENDING...")

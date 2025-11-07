#!/usr/bin/env python3
"""
Seller agent for OrderManagement (ordermanagement_new).

Very simple behavior:
- On order: sends invoice to Buyer and delivery_req to Logistics
- On pay: logs (no further action here)
- On cancel_req: sends cancel_ack
- On confirm: logs final outcome
"""

import random
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

// Simple state store and decision function
state: dict[str, dict] = {}

def _st(oid: str) -> dict:
    s = state.setdefault(oid, {
        "item": None,
        "price_sent": False,
        "delivery_req_sent": False,
        "outcome": None,
        "cancel_req_received": False,
        "rescind": None,
    })
    return s

async def decide_next(oid: str):
    """
    Decide Seller's next action based on BSPL information constraints:
    - cancel_ack[id,rescind,outcome] requires: in id, in rescind, nil delivery_req, nil outcome
    - invoice[id,price] requires: in id, nil outcome
    - delivery_req[id,item,delivery_req] requires: in id, in item, nil outcome
    Policy:
    - If a cancellation is pending and delivery has not been requested, deterministically honor it (send cancel_ack).
    - Otherwise, send invoice and/or delivery_req (order flexible). We keep this flexible and may send either or both over time.
    """
    s = _st(oid)
    if s["outcome"]:
        return
    # Deterministic: if cancellation is possible, honor it (only consistent option to close case)
    if s["cancel_req_received"] and not s["delivery_req_sent"]:
        ack = cancel_ack(id=oid, rescind=s["rescind"], outcome="CANCELLED")
        await send_cancel_ack(ack)
        adapter.info(f"SENT cancel_ack: id={oid}, outcome=CANCELLED")
        s["outcome"] = "CANCELLED"
        return

    # Otherwise, consider sending invoice and/or delivery_req; both keep outcome unset
    if not s["price_sent"]:
        inv = invoice(id=oid, price=100)
        await send_invoice(inv)
        adapter.info(f"SENT invoice: id={oid}, price=100")
        s["price_sent"] = True
        # fallthrough to maybe also send delivery_req this cycle
    if not s["delivery_req_sent"] and s["item"] is not None:
        dreq = delivery_req(id=oid, item=s["item"], delivery_req=f"DREQ_{oid}")
        await send_delivery_req(dreq)
        adapter.info(f"SENT delivery_req: id={oid}, item={s['item']}")
        s["delivery_req_sent"] = True
        return


@adapter.reaction(order)
async def on_order(msg):
    oid = msg["id"]
    item = msg["item"]
    s = _st(oid)
    s["item"] = item
    # Decide whether to reject outright or proceed
    if random.random() < 0.1:
        rej = reject(id=oid, outcome="REJECTED")
        await adapter.send(rej)
        log.info(f"SENT reject: id={oid}, outcome=REJECTED")
        s["outcome"] = "REJECTED"
        return msg

    # Otherwise let decision function choose order of actions
    await decide_next(oid)
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
    s = _st(oid)
    s["cancel_req_received"] = True
    s["rescind"] = rescind
    await decide_next(oid)
    return msg


@adapter.reaction(confirm)
async def on_confirm(msg):
    oid = msg["id"]
    outcome = msg["outcome"]
    s = _st(oid)
    s["outcome"] = outcome
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

#!/usr/bin/env python3
"""
Buyer agent for OrderManagement (ordermanagement_new).

Very simple behavior:
- Initiates an order (optional initiator for demos)
- On invoice: sends pay
- On deliver: sends confirm (using stored payment_ref)
- On reject/cancel_ack: logs and does nothing further
"""

import uuid, random
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
    try:
        oid = message["id"]
        itm = message["item"]
        log.info(f"SENT order: id={oid}, item={itm}")
    except Exception:
        log.info("SENT order")

async def send_pay(message: pay):
    await adapter.send(message)
    try:
        oid = message["id"]
        price = message["price"]
        pref = message["payment_ref"]
        log.info(f"SENT pay: id={oid}, price={price}, payment_ref={pref}")
    except Exception:
        log.info("SENT pay")

async def send_confirm(message: confirm):
    await adapter.send(message)
    try:
        oid = message["id"]
        pref = message["payment_ref"]
        ddate = message["delivery_date"]
        outcome = message["outcome"]
        log.info(f"SENT confirm: id={oid}, payment_ref={pref}, delivery_date={ddate}, outcome={outcome}")
    except Exception:
        log.info("SENT confirm")

async def send_cancel_req(message: cancel_req):
    await adapter.send(message)
    try:
        oid = message["id"]
        resc = message["rescind"]
        log.info(f"SENT cancel_req: id={oid}, rescind={resc}")
    except Exception:
        log.info("SENT cancel_req")

# ───────────────────────────────────────────────────────────────────
# Simple state store and decision function (flexible behavior)
# Maps order id -> known fields and flags
state: dict[str, dict] = {}

def _st(oid: str) -> dict:
    s = state.setdefault(oid, {
        "item": None,
        "price": None,
        "payment_ref": None,
        "delivery_req": None,
        "delivery_date": None,
        "outcome": None,
        "invoice_received": False,
        "pay_sent": False,
        "cancel_sent": False,
        "pre_cancel": False,
        "delivery_received": False,
        "confirm_sent": False,
    })
    return s

async def decide_next(oid: str):
    """
    Decide Buyer's next action based on BSPL info constraints:
    - pay[id,price,payment_ref] requires: in id, in price, nil outcome
    - cancel_req[id,rescind] requires: in id, nil delivery_date, nil outcome
    - confirm[id,payment_ref,delivery_date,outcome] requires: in id, in payment_ref, in delivery_date (sets outcome)
    Policy:
    - If pre_cancel is set and conditions allow, send cancel_req
    - If both payment_ref and delivery_date are known and outcome is unset, deterministically send confirm.
    - If invoice (price) is known and outcome is unset, choose to pay (70%) or request cancellation (30% if no delivery yet).
    """
    s = _st(oid)
    # If we've already requested cancellation, stop taking further actions
    if s["cancel_sent"] or s["outcome"]:
        return
    
    # Handle pre_cancel flag from initiator (before any delivery)
    if s.get("pre_cancel") and not s["delivery_date"] and not s["cancel_sent"] and not s["outcome"]:
        r = cancel_req(id=oid, rescind=f"RESC_{oid}")
        await send_cancel_req(r)
        s["cancel_sent"] = True
        s["pre_cancel"] = False
        return
    
    # If both payment and delivery are known and we haven't confirmed yet → confirm
    if s["payment_ref"] and s["delivery_date"] and not s["confirm_sent"] and not s["outcome"]:
        c = confirm(id=oid, payment_ref=s["payment_ref"], delivery_date=s["delivery_date"], outcome="DELIVERED")
        await send_confirm(c)
        s["confirm_sent"] = True
        return

    # Fallback progress: if delivery already happened and we haven't paid yet, pay now and confirm
    if s["delivery_date"] and not s["pay_sent"] and s["price"] and not s["outcome"] and not s["cancel_sent"]:
        pref = f"PAY_{uuid.uuid4().hex[:8]}"
        p = pay(id=oid, price=s["price"], payment_ref=pref)
        await send_pay(p)
        s["payment_ref"] = pref
        s["pay_sent"] = True
        c = confirm(id=oid, payment_ref=pref, delivery_date=s["delivery_date"], outcome="DELIVERED")
        await send_confirm(c)
        s["confirm_sent"] = True
        return

    # If invoice is in and no outcome: choose to pay or cancel
    if s["invoice_received"] and not s["outcome"] and not s["cancel_sent"]:
        # If not paid yet, randomly decide to pay vs cancel (70/30)
        if not s["pay_sent"]:
            if random.random() < 0.7:
                pref = f"PAY_{uuid.uuid4().hex[:8]}"
                p = pay(id=oid, price=s["price"], payment_ref=pref)
                await send_pay(p)
                s["payment_ref"] = pref
                s["pay_sent"] = True
                # If delivery already arrived, confirm right away
                if s["delivery_date"] and not s["confirm_sent"]:
                    c = confirm(id=oid, payment_ref=pref, delivery_date=s["delivery_date"], outcome="DELIVERED")
                    await send_confirm(c)
                    s["confirm_sent"] = True
                return
            else:
                # Consider cancellation before delivery/outcome
                if not s["delivery_date"] and not s["cancel_sent"]:
                    r = cancel_req(id=oid, rescind=f"RESC_{oid}")
                    await send_cancel_req(r)
                    s["cancel_sent"] = True
                    return

    # If delivery arrived after paying, confirmation handled by the first branch next time
    return

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
    s = _st(oid)
    s["price"] = price
    s["invoice_received"] = True
    # Let decision function choose next step (pay/cancel later/confirm later)
    await decide_next(oid)
    return msg


@adapter.reaction(deliver)
async def on_deliver(msg):
    """Confirm reception after delivery (uses previously sent payment_ref)."""
    oid = msg["id"]
    ddate = msg["delivery_date"]
    s = _st(oid)
    s["delivery_date"] = ddate
    s["delivery_received"] = True
    # If payment exists, decision will confirm; otherwise wait until payment later
    await decide_next(oid)
    return msg


@adapter.reaction(reject)
async def on_reject(msg):
    """Handle rejection (no follow-up)."""
    oid = msg["id"]
    outcome = msg["outcome"]
    s = _st(oid)
    s["outcome"] = outcome
    log.info(f"RECEIVED reject: id={oid}, outcome={outcome}")
    return msg


@adapter.reaction(cancel_ack)
async def on_cancel_ack(msg):
    """Handle cancellation acknowledgement (no follow-up)."""
    oid = msg["id"]
    outcome = msg["outcome"]
    s = _st(oid)
    s["outcome"] = outcome
    log.info(f"RECEIVED cancel_ack: id={oid}, outcome={outcome}")
    return msg


# Optional: simple initiator to place an example order when run directly
async def initiator():
    oid = f"ORD_{uuid.uuid4().hex[:8]}"
    item = "widget"
    o = order(id=oid, item=item)
    await send_order(o)
    # Decide upfront if this case should be pre-cancelled in a later round
    try:
        if random.random() < 0.2:
            s = _st(oid)
            s["pre_cancel"] = True
    except Exception as e:
        log.error(f"Buyer initiator pre-cancel flag failed: {e}")
    
    # Don't immediately send cancel_req here - let decide_next() handle it
    # This prevents race conditions with concurrent CompleteTask messages from multiple RAs


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

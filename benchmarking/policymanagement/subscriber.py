#!/usr/bin/env python3
"""
Subscriber agent for PolicyManagement.

Behavior:
- On offer: randomly accept or reject.
- accept sets 'agreed' (and requires nil date); reject sets 'date' (and requires nil agreed).
"""

import random
from datetime import datetime
from bspl.adapter import Adapter
from configuration import systems, agents
from PolicyManagement import offer, accept, reject
from simple_logging import setup_logger

log = setup_logger("subscriber")
adapter = Adapter("Subscriber", systems, agents)


async def send_accept(message: accept):
    await adapter.send(message)
    try:
        pid = message["id"]
        prem = message["premium"]
        log.info(f"SENT accept: id={pid}, premium={prem}")
    except Exception:
        log.info("SENT accept")


async def send_reject(message: reject):
    await adapter.send(message)
    try:
        pid = message["id"]
        date = message["date"]
        log.info(f"SENT reject: id={pid}, date={date}")
    except Exception:
        log.info("SENT reject")


@adapter.reaction(offer)
async def on_offer(msg):
    pid = msg["id"]
    prem = msg["premium"]

    # 20% acceptance rate
    if random.random() < 0.2:
        a = accept(id=pid, premium=prem, agreed="YES")
        await send_accept(a)
    else:
        # Reject with a date only
        date = datetime.utcnow().isoformat()
        r = reject(id=pid, premium=prem, date=date)
        await send_reject(r)
    return msg


if __name__ == "__main__":
    log.info("Subscriber STARTING...")
    try:
        adapter.start()
    except KeyboardInterrupt:
        log.info("Subscriber INTERRUPTED")
    except Exception as e:
        log.error(f"Subscriber CRASHED: {e}")
        import traceback; traceback.print_exc()
    finally:
        log.info("Subscriber ENDING...")

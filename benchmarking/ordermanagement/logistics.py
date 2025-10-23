#!/usr/bin/env python3
"""
Logistics agent for OrderManagement (ordermanagement_new).

Very simple behavior:
- On delivery_req from Seller: sends deliver to Buyer
"""

from datetime import datetime
from bspl.adapter import Adapter
from configuration import systems, agents
from OrderManagement import delivery_req, deliver
from simple_logging import setup_logger

log = setup_logger("logistics")
adapter = Adapter("Logistics", systems, agents)


@adapter.reaction(delivery_req)
async def on_delivery_req(msg):
    oid = msg["id"]
    item = msg["item"]
    dreq = msg["delivery_req"]
    ddate = datetime.utcnow().isoformat()

    d = deliver(id=oid, item=item, delivery_req=dreq, delivery_date=ddate)
    await adapter.send(d)
    log.info(f"SENT deliver: id={oid}, item={item}, delivery_date={ddate}")
    return msg


if __name__ == "__main__":
    log.info("Logistics STARTING...")
    try:
        adapter.start()
    except KeyboardInterrupt:
        log.info("Logistics INTERRUPTED")
    except Exception as e:
        log.error(f"Logistics CRASHED: {e}")
        import traceback; traceback.print_exc()
    finally:
        log.info("Logistics ENDING...")

#!/usr/bin/env python3
"""
Auditor agent for PolicyManagement.

Behavior:
- Initiates request(r_id, amount) queries.
- On report: logs received policy info.
"""

import uuid, random
from bspl.adapter import Adapter
from configuration import systems, agents
from PolicyManagement import request, report
from simple_logging import setup_logger

log = setup_logger("auditor")
adapter = Adapter("Auditor", systems, agents)


async def send_request(message: request):
    await adapter.send(message)
    try:
        rid = message["r_id"]
        amount = message["amount"]
        # Audit view: request logs include r_id; enactment id for audit is r_id via RA events
        log.info(f"SENT request: id={rid}, amount={amount}")
    except Exception:
        log.info("SENT request")


@adapter.reaction(report)
async def on_report(msg):
    rid = msg["r_id"]
    pid = msg["id"]
    prem = msg["premium"]
    info = msg["info"]
    # Note: keep r_id/id labeling; 'id' in SEND props was set to r_id for export
    log.info(f"RECEIVED report: r_id={rid}, id={pid}, premium={prem}, info={info}")
    return msg


async def initiator():
    # Send a request only every 5 initiator rounds
    state = getattr(initiator, "_state", {"round": 0})
    state["round"] = state.get("round", 0) + 1
    setattr(initiator, "_state", state)

    if state["round"] % 5 != 0:
        return

    rid = f"R{uuid.uuid4().hex[:8]}"
    amount = random.choice([15, 25])
    req = request(r_id=rid, amount=amount)
    await send_request(req)


if __name__ == "__main__":
    log.info("Auditor STARTING...")
    try:
        adapter.start()
    except KeyboardInterrupt:
        log.info("Auditor INTERRUPTED")
    except Exception as e:
        log.error(f"Auditor CRASHED: {e}")
        import traceback; traceback.print_exc()
    finally:
        log.info("Auditor ENDING...")

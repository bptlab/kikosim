#!/usr/bin/env python3
"""
Pharmacist agent for Treatment protocol.

Behavior:
- On prescription(id, rx) from Doctor, sends filledRx to Patient with done flag.
"""

from bspl.adapter import Adapter
from configuration import systems, agents
from Treatment import prescription, filledRx
from simple_logging import setup_logger

log = setup_logger("pharmacist")
adapter = Adapter("Pharmacist", systems, agents)


async def send_filled_rx(message: filledRx):
    await adapter.send(message)
    try:
        sid = message["id"]
        done = message["done"]
        log.info(f"SENT filledRx: id={sid}, done={done}")
    except Exception:
        log.info("SENT filledRx")


@adapter.reaction(prescription)
async def on_prescription(msg):
    sid = msg["id"]
    rx = msg["rx"]
    fr = filledRx(id=sid, rx=rx, done="FILLED")
    await send_filled_rx(fr)
    return msg


if __name__ == "__main__":
    log.info("Pharmacist STARTING...")
    try:
        adapter.start()
    except KeyboardInterrupt:
        log.info("Pharmacist INTERRUPTED")
    except Exception as e:
        log.error(f"Pharmacist CRASHED: {e}")
        import traceback; traceback.print_exc()
    finally:
        log.info("Pharmacist ENDING...")

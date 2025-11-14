#!/usr/bin/env python3
"""
Doctor agent for Treatment protocol.

Behavior:
- On complaint(id, symptom): either sends reassurance to Patient or a prescription to Pharmacist (exclusive choice).
- Choice is randomized to expose both maximal enactment paths.
"""

import random, uuid
from bspl.adapter import Adapter
from configuration import systems, agents
from Treatment import complaint, reassurance, prescription
from simple_logging import setup_logger

log = setup_logger("doctor")
adapter = Adapter("Doctor", systems, agents)


async def send_reassurance(message: reassurance):
    await adapter.send(message)
    try:
        sid = message["id"]
        done = message["done"]
        log.info(f"SENT reassurance: id={sid}, done={done}")
    except Exception:
        log.info("SENT reassurance")


async def send_prescription(message: prescription):
    await adapter.send(message)
    try:
        sid = message["id"]
        log.info(f"SENT prescription: id={sid}")
    except Exception:
        log.info("SENT prescription")


# Track per-complaint choice to avoid duplicate sends
decisions: dict[str, str] = {}


@adapter.reaction(complaint)
async def on_complaint(msg):
    sid = msg["id"]
    symptom = msg["symptom"]

    # Decide once per id
    choice = decisions.get(sid)
    if choice is None:
        choice = "reassure" if random.random() < 0.5 else "prescribe"
        decisions[sid] = choice

    if choice == "reassure":
        r = reassurance(id=sid, symptom=symptom, done="OK")
        await send_reassurance(r)
    else:
        # Produce a simple rx token
        rx_token = f"RX_{uuid.uuid4().hex[:6]}"
        p = prescription(id=sid, symptom=symptom, rx=rx_token)
        await send_prescription(p)

    return msg


if __name__ == "__main__":
    log.info("Doctor STARTING...")
    try:
        adapter.start()
    except KeyboardInterrupt:
        log.info("Doctor INTERRUPTED")
    except Exception as e:
        log.error(f"Doctor CRASHED: {e}")
        import traceback; traceback.print_exc()
    finally:
        log.info("Doctor ENDING...")

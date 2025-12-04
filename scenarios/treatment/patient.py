#!/usr/bin/env python3
"""
Patient agent for Treatment protocol.

Behavior:
- Initiates complaints with a fresh id and a symptom string.
- On reassurance or filledRx: records 'done' and logs, no further actions.
"""

import uuid, random
from bspl.adapter import Adapter
from configuration import systems, agents
from Treatment import complaint, reassurance, filledRx
from simple_logging import setup_logger

log = setup_logger("patient")
adapter = Adapter("Patient", systems, agents)

# Deferred send wrapper
async def send_complaint(message: complaint):
    await adapter.send(message)
    try:
        sid = message["id"]
        sym = message["symptom"]
        log.info(f"SENT complaint: id={sid}, symptom={sym}")
    except Exception:
        log.info("SENT complaint")


# Minimal local state per id
state: dict[str, dict] = {}

def _st(sid: str) -> dict:
    return state.setdefault(sid, {"symptom": None, "done": None})


@adapter.reaction(reassurance)
async def on_reassurance(msg):
    sid = msg["id"]
    done = msg["done"]
    s = _st(sid)
    s["done"] = done
    log.info(f"RECEIVED reassurance: id={sid}, done={done}")
    return msg


@adapter.reaction(filledRx)
async def on_filled_rx(msg):
    sid = msg["id"]
    done = msg["done"]
    s = _st(sid)
    s["done"] = done
    log.info(f"RECEIVED filledRx: id={sid}, done={done}")
    return msg


# Simple initiator to seed complaints
SYMPTOMS = [
    "headache",
    "cough",
    "fever",
    "back pain",
]

async def initiator():
    sid = f"S{uuid.uuid4().hex[:8]}"
    symptom = random.choice(SYMPTOMS)
    s = _st(sid)
    s["symptom"] = symptom
    c = complaint(id=sid, symptom=symptom)
    await send_complaint(c)


if __name__ == "__main__":
    log.info("Patient STARTING...")
    try:
        adapter.start()
    except KeyboardInterrupt:
        log.info("Patient INTERRUPTED")
    except Exception as e:
        log.error(f"Patient CRASHED: {e}")
        import traceback; traceback.print_exc()
    finally:
        log.info("Patient ENDING...")

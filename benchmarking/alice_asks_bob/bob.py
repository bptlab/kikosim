#!/usr/bin/env python3
"""
Bob Agent - Receives Ask and sends Reply

Minimal synthetic protocol for resource evaluation:
1. On Ask(id, question) from Alice, reply once with Reply(id, answer)

No production mode, no monitoring wrapper. Logs use the SENT pattern.
"""
import random
from bspl.adapter import Adapter
from configuration import systems, agents
from AliceAsksBob import Ask, Reply
from simple_logging import setup_logger

log = setup_logger('bob')
adapter = Adapter('Bob', systems, agents)


# ──────────────────────────────────────────────────────────────────────────────
# MESSAGE HANDLERS
# ──────────────────────────────────────────────────────────────────────────────

@adapter.reaction(Ask)
async def receive_ask(msg):
    """On Ask, send a single Reply.

    This reaction will be deferred by the resource transformation in simulation
    setups, allowing a clean measurement of resource effects with fixed durations.
    """
    _id = msg["id"]
    _question = msg["question"]

    # Simple deterministic answer text; randomness optional but not required
    answer = random.choice(["OK", "42", "ACK"])

    reply = Reply(id=_id, question=_question, answer=answer)
    await adapter.send(reply)
    props = f"id={_id}, answer={answer}"
    log.info(f"SENT Reply: {props}")
    return msg


if __name__ == '__main__':
    log.info('Bob STARTING...')
    try:
        adapter.start()
    except KeyboardInterrupt:
        log.info('Bob INTERRUPTED BY USER')
    except Exception as e:
        log.error(f'Bob CRASHED: {e}')
        import traceback
        traceback.print_exc()
    finally:
        log.info('Bob ENDING...')


#!/usr/bin/env python3
"""
Alice Agent - Sends Ask and receives Reply

Minimal synthetic protocol for resource evaluation:
1. Alice sends Ask(id, question) to Bob
2. Bob replies with Reply(id, answer)

No production mode, no monitoring wrapper. Logs use the SENT pattern.
"""
import uuid, random
from bspl.adapter import Adapter
from configuration import systems, agents
from AliceAsksBob import Ask, Reply
from simple_logging import setup_logger

log = setup_logger('alice')
adapter = Adapter('Alice', systems, agents)

# ──────────────────────────────────────────────────────────────────────────────
# MESSAGE HANDLERS
# ──────────────────────────────────────────────────────────────────────────────

@adapter.reaction(Reply)
async def receive_reply(msg):
    """Handle Reply from Bob."""
    # Access fields if needed
    _id = msg["id"]
    _answer = msg["answer"]
    # Business logic could process the answer here
    return msg


# ──────────────────────────────────────────────────────────────────────────────
# INITIATOR PATTERN (simulation)
# ──────────────────────────────────────────────────────────────────────────────

QUESTIONS = [
    "What is the answer?",
    "How are you?",
    "Ping?",
    "Status?",
]

async def initiator():
    """Create an Ask with a fresh id and a simple question."""
    ask_id = f"ASK_{str(uuid.uuid4())[:8]}"
    question = random.choice(QUESTIONS)
    msg = Ask(id=ask_id, question=question)
    await adapter.send(msg)
    props = f"id={ask_id}, question={question}"
    log.info(f"SENT Ask: {props}")


if __name__ == '__main__':
    log.info('Alice STARTING...')
    try:
        adapter.start()
    except KeyboardInterrupt:
        log.info('Alice INTERRUPTED BY USER')
    except Exception as e:
        log.error(f'Alice CRASHED: {e}')
        import traceback
        traceback.print_exc()
    finally:
        log.info('Alice ENDING...')


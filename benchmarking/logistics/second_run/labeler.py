"""
This agent generates unique labels for orders upon request.
"""

import logging
import uuid
from bspl.adapter import Adapter
from configuration import systems, agents
from Logistics import Labeled, RequestLabel

adapter = Adapter("Labeler", systems, agents)

log = logging.getLogger("labeler")
log.setLevel(logging.INFO)

@adapter.reaction(RequestLabel)
async def label(msg):
    """Handles label requests by generating a unique UUID-based label."""
    label = str(uuid.uuid4())
    log.info(f"Generated label {label} for order {msg['id']}")
    response_msg = Labeled(label=label, **msg.payload)
    log.info(f"SENT Labeled: id={msg['id']}, label={label}")
    await adapter.send(response_msg)
    return msg

if __name__ == "__main__":
    log.info("Starting Labeler...")
    adapter.start()

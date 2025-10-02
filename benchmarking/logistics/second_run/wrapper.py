"""
This agent handles wrapping requests by choosing appropriate wrapping material based on item type.
"""

import logging
from bspl.adapter import Adapter
from configuration import systems, agents
from Logistics import Wrapped, RequestWrapping

adapter = Adapter("Wrapper", systems, agents)

log = logging.getLogger("wrapper")
log.setLevel(logging.INFO)

@adapter.reaction(RequestWrapping)
async def wrap(msg):
    """Handles wrapping requests by selecting appropriate material (bubblewrap for fragile items)."""
    wrapping = "bubblewrap" if msg["item"] in ["plate", "glass"] else "paper"
    log.info(f"Order {msg['id']} item {msg['itemID']} ({msg['item']}) wrapped with {wrapping}")
    response_msg = Wrapped(
        wrapping=wrapping,
        **msg.payload
    )
    log.info(f"SENT Wrapped: id={msg['id']}, itemID={msg['itemID']}, wrapping={wrapping}")
    await adapter.send(response_msg)
    return msg

if __name__ == "__main__":
    log.info("Starting Wrapper...")
    adapter.start()

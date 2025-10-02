"""
This agent combines wrapped items with their labels to create the final package.
"""

import logging
from bspl.adapter import Adapter
from configuration import systems, agents
from Logistics import Packed

adapter = Adapter("Packer", systems, agents)

log = logging.getLogger("packer")
log.setLevel(logging.INFO)

@adapter.enabled(Packed)
async def pack(msg):
    """Handles enabled Packed messages by setting their status."""
    msg["status"] = "packed"
    log.info(f"SENT Packed: id={msg['id']}, itemID={msg['itemID']}, status=packed")
    return msg

if __name__ == "__main__":
    logger.info("Starting Packer...")
    adapter.start()

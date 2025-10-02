"""
This agent combines wrapped items with their labels to create the final package.
"""

import logging
from bspl.adapter import Adapter
from configuration import systems, agents
from Logistics import Packed, PackCommand

adapter = Adapter("Packer", systems, agents)

log = logging.getLogger("packer")
log.setLevel(logging.INFO)

@adapter.enabled(PackCommand)
async def pack_command(msg):
    """Handles enabled PackCommand messages by setting their status."""
    msg["packingDone"] = "packed"
    log.info(f"Order {msg['id']} item {msg['itemID']} packed with wrapping {msg['wrapping']} and label {msg['label']}")
    log.info(f"SENT PackCommand: id={msg['id']}, itemID={msg['itemID']}, packingDone=packed")
    return msg

@adapter.reaction(PackCommand)
async def pack(msg):
    """Reacts to PackCommand messages by setting their status."""
    log.info(f"Order {msg['id']} item {msg['itemID']} packed with wrapping {msg['wrapping']} and label {msg['label']}")
    packed_msg = Packed(
        id=msg["id"],
        itemID=msg["itemID"],
        item=msg["item"],
        wrapping=msg["wrapping"],
        label=msg["label"],
        packingDone=msg["packingDone"],
        status="packed",
    )
    log.info(f"SENT Packed: id={msg['id']}, itemID={msg['itemID']}, status=packed")
    return packed_msg

if __name__ == "__main__":
    log.info("Starting Packer...")
    adapter.start()

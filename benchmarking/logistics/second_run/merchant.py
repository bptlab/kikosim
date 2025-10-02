"""
This agent initiates the logistics protocol by generating orders and handling packed responses.
"""

import logging
import random
import asyncio
from bspl.adapter import Adapter
from configuration import systems, agents
from Logistics import RequestLabel, RequestWrapping, Packed

adapter = Adapter("Merchant", systems, agents)

log = logging.getLogger("merchant")
# log.setLevel(logging.DEBUG)

# Global counters to ensure unique IDs across multiple initiator() calls
global_item_id = 0
global_order_id = 0

# NEW VERSION: Initiator pattern for simulation framework compatibility
# The simulation framework expects an 'initiator' function that can be called
# by TimeUpdate handlers for coordinated execution with virtual time
async def initiator():
    """Generates a single order with random items and address."""
    global global_item_id, global_order_id
    
    id = global_order_id
    global_order_id += 1
    
    msg = RequestLabel(
        id=id,
        address=random.choice(["Lancaster University", "NCSU"]),
    )
    log.info(f"SENT RequestLabel: id={id}, address={msg['address']}")
    await adapter.send(msg)
    
    for i in range(2):
        msg = RequestWrapping(
            id=id,
            itemID=global_item_id,
            item=random.choice(["ball", "bat", "plate", "glass"]),
        )
        log.info(f"SENT RequestWrapping: id={id}, itemID={global_item_id}, item={msg['item']}")
        await adapter.send(msg)
        global_item_id += 1

@adapter.reaction(Packed)
async def packed(msg):
    """Handles packed items by logging their status."""
    log.info(f"Order {msg['id']} item {msg['itemID']} packed with status: {msg['status']}")
    return msg

if __name__ == "__main__":
    log.info("Starting Merchant...")
    # OLD: adapter.start(order_generator()) - direct execution
    # NEW: adapter.start() - business logic triggered by TimeUpdate handlers
    adapter.start()

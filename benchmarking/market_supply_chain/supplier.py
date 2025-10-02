#!/usr/bin/env python3
"""
Supplier Agent - Processes orders from retailer

Standard supplier logic:
1. Receives orders from retailer
2. Randomly accepts or rejects based on business rules
3. For accepted orders, sends packages after processing delay
"""

import asyncio, random
from bspl.adapter import Adapter
from configuration import systems, agents
from MarketSupplyChain import Order, Reject, Accept, ShipPackage
from simple_logging import setup_logger
from datetime import datetime, timedelta

# ═══════════════════════════════════════════════════════════════════
# SETUP - Standard agent initialization
# ═══════════════════════════════════════════════════════════════════
adapter = Adapter("Supplier", systems, agents)
log = setup_logger("supplier")

# ═══════════════════════════════════════════════════════════════════
# BUSINESS LOGIC - Pure business functions
# ═══════════════════════════════════════════════════════════════════

def evaluate_order(product: str) -> tuple[bool, str]:
    """Evaluate order and determine acceptance/rejection."""
    # Business rules for acceptance
    rejection_reasons = ["Out of stock", "Too busy", "Product unavailable"]
    
    # 70% acceptance rate
    if random.random() < 0.7:
        # Accept the order
        return True, "ACCEPTED"
    else:
        # Reject the order
        reason = random.choice(rejection_reasons)
        return False, reason

def process_shipment(order_id: str, product: str) -> str:
    """Process shipment and generate package info."""
    package_info = f"PKG_{order_id}_{product}_{datetime.now().strftime('%Y%m%d')}"
    return package_info

# ═══════════════════════════════════════════════════════════════════
# MESSAGE HANDLERS - Reactions to orders
# ═══════════════════════════════════════════════════════════════════

@adapter.reaction(Order)
async def receive_order(msg):
    """Handle incoming orders from retailer."""
    order_id = msg["orderID"]
    market_id = msg["id"]
    product = msg["product"]
    
    # Properties for logging
    props = f"orderID={order_id}, id={market_id}, product={product}"
    
    # Business logic evaluation
    accepted, response_reason = evaluate_order(product)
    deliveryTime = "3-5 business days"
    
    if accepted:
        # Send acceptance
        accept_msg = Accept(
            orderID=order_id,
            id=market_id,
            product=product,
            orderResponse="ACCEPTED",
            deliveryTime=deliveryTime
        )
        await adapter.send(accept_msg)
        # Log with business message emoji and all properties
        props = f"orderID={order_id}, id={market_id}, product={product}, orderResponse=ACCEPTED"
        log.info(f"SENT Accept: {props}")
        
    else:
        # Send rejection
        reject_msg = Reject(
            orderID=order_id,
            id=market_id,
            product=product,
            orderResponse=response_reason
        )
        await adapter.send(reject_msg)
        # Log with business message emoji and all properties
        props = f"orderID={order_id}, id={market_id}, product={product}, orderResponse={response_reason}"
        log.info(f"SENT Reject: {props}")
    
    return msg

@adapter.reaction(Accept)
async def ship_package(msg):
    """Self-reaction to Accept message to trigger ShipPackage."""
    order_id = msg["orderID"]
    market_id = msg["id"]
    product = msg["product"]
    order_response = msg["orderResponse"]
    delivery_time = msg["deliveryTime"]
    
    # Only react to our own Accept messages
    if order_response == "ACCEPTED":
        package_info = process_shipment(order_id, product)
        package_msg = ShipPackage(
            orderID=order_id,
            id=market_id,
            product=product,
            orderResponse=order_response,
            package=package_info,
            deliveryTime=delivery_time
        )
        await adapter.send(package_msg)
        # Log with business message emoji and all properties
        props = f"orderID={order_id}, id={market_id}, product={product}, package={package_info}, deliveryTime={delivery_time}"
        log.info(f"SENT ShipPackage: {props}")
    
    return msg

# ═══════════════════════════════════════════════════════════════════
# STARTUP
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    log.info("🏁 SUPPLIER STARTING...")
    try:
        adapter.start()
    except KeyboardInterrupt:
        log.info("🛑 SUPPLIER INTERRUPTED BY USER")
    except Exception as e:
        log.error(f"💥 SUPPLIER CRASHED: {e}")
        import traceback
        traceback.print_exc()
    finally:
        log.info("🏁 SUPPLIER ENDING...")
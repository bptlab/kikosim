#!/usr/bin/env python3
"""
Retailer Agent - Processes market orders and manages supplier interactions

Complex state management:
1. Receives product lists from market
2. Breaks down into individual orders to supplier
3. Tracks state of each individual order
4. Retries rejected orders until completion
5. Sends completion notification back to market when all products fulfilled
"""

import uuid, asyncio
from bspl.adapter import Adapter
from configuration import systems, agents
from MarketSupplyChain import MarketOrder, MarketOrderComplete, Order, Reject, Accept, ShipPackage
from simple_logging import setup_logger

# ═══════════════════════════════════════════════════════════════════
# SETUP - Standard agent initialization
# ═══════════════════════════════════════════════════════════════════
adapter = Adapter("Retailer", systems, agents)
log = setup_logger("retailer")

# State tracking for market orders
market_orders = {}  # market_order_id -> {products: [list], completed: [list], pending: [list]}
order_to_market = {}  # order_id -> market_order_id

# ═══════════════════════════════════════════════════════════════════
# BUSINESS LOGIC - Pure business functions
# ═══════════════════════════════════════════════════════════════════

def process_market_order(market_order_id: str, product_list: list) -> None:
    """Initialize tracking for a new market order."""
    market_orders[market_order_id] = {
        'products': product_list,
        'completed': [],
        'pending': product_list.copy(),
    }
    # Market order processing starts (will be logged by deferred decorator)
    log.info(f"🔍 DEBUG: Added {market_order_id} to market_orders. Total market orders: {len(market_orders)}")

def check_market_order_completion(market_order_id: str) -> bool:
    """Check if all products in a market order are completed."""
    if market_order_id not in market_orders:
        log.error(f"❌ Market order {market_order_id} not found in check_market_order_completion")
        return False
    order_state = market_orders[market_order_id]
    return not order_state['pending']

def mark_product_completed(market_order_id: str, product: str) -> None:
    """Mark a product as completed in the market order."""
    if market_order_id not in market_orders:
        log.error(f"❌ Market order {market_order_id} not found in mark_product_completed")
        return
    order_state = market_orders[market_order_id]
    if product in order_state['pending']:
        order_state['pending'].remove(product)
        order_state['completed'].append(product)

def mark_product_rejected(market_order_id: str, product: str) -> None:
    """Handle rejected product - it stays in pending for retry."""
    # Product rejection will be retried (business logic timing)

# ═══════════════════════════════════════════════════════════════════
# MESSAGE HANDLERS - Reactions to various message types
# ═══════════════════════════════════════════════════════════════════

@adapter.reaction(MarketOrder)
async def receive_market_order(msg):
    """Handle new market order with product list."""
    market_order_id = msg["id"]
    product_list_str = msg["productList"]
    product_list = [p.strip() for p in product_list_str.split(",")]
    
    # Properties for logging
    props = f"id={market_order_id}, productList={product_list_str}"
    
    # Business logic
    process_market_order(market_order_id, product_list)
    
    # Send individual orders to supplier for each product
    for product in product_list:
        await send_order_to_supplier(market_order_id, product)
    
    return msg

@adapter.reaction(Accept)
async def receive_accept(msg):
    """Handle supplier acceptance."""
    order_id = msg["orderID"]
    product = msg["product"]
    order_response = msg["orderResponse"]
    
    # Properties for logging
    props = f"orderID={order_id}, product={product}, orderResponse={order_response}"
    
    return msg

@adapter.reaction(Reject)
async def receive_reject_order_again(msg):
    """Handle supplier rejection and retry."""
    order_id = msg["orderID"]
    product = msg["product"]
    order_response = msg["orderResponse"]
    
    # Properties for logging
    props = f"orderID={order_id}, product={product}, orderResponse={order_response}"
    
    # Find the market order and retry
    if order_id in order_to_market:
        market_order_id = order_to_market[order_id]
        
        # Check if market order still exists (defensive programming)
        if market_order_id not in market_orders:
            log.error(f"❌ Market order {market_order_id} not found in market_orders for rejected order {order_id}")
            return msg
            
        mark_product_rejected(market_order_id, product)
        
        # Retry after a short delay
        await send_order_to_supplier(market_order_id, product)
    else:
        log.error(f"❌ Order {order_id} not found in order_to_market mapping for rejection")
    
    return msg

@adapter.reaction(ShipPackage)
async def receive_package(msg):
    """Handle package delivery - product is now completed."""
    order_id = msg["orderID"]
    product = msg["product"]
    package = msg["package"]
    
    # Properties for logging
    props = f"orderID={order_id}, product={product}, package={package}"
    
    # Mark product as completed in market order
    if order_id in order_to_market:
        market_order_id = order_to_market[order_id]
        
        # Check if market order still exists (defensive programming)
        if market_order_id not in market_orders:
            log.error(f"❌ Market order {market_order_id} not found in market_orders for order {order_id}")
            log.error(f"🔍 DEBUG: Current market_orders keys: {list(market_orders.keys())}")
            log.error(f"🔍 DEBUG: Current order_to_market mappings: {len(order_to_market)}")
            return msg
            
        mark_product_completed(market_order_id, product)
        
        # Check if market order is now complete
        if check_market_order_completion(market_order_id):
            await send_market_completion(market_order_id)
    else:
        log.error(f"❌ Order {order_id} not found in order_to_market mapping")
    
    return msg

# ═══════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════

async def send_order(message: Order):
    """Wrapper around sending Order messages."""
    await adapter.send(message)

async def send_market_order_complete(message: MarketOrderComplete):
    """Wrapper around sending MarketOrderComplete messages."""
    await adapter.send(message)

async def send_order_to_supplier(market_order_id: str, product: str):
    """Send individual order to supplier for a product."""
    order_id = str(uuid.uuid4())[:8]
    
    # Track which market order this belongs to
    order_to_market[order_id] = market_order_id
    
    order = Order(orderID=order_id, id=market_order_id, product=product)
    # Use wrapper for sending
    await send_order(order)
    # Log with business message emoji and all properties
    props = f"id={market_order_id}, orderID={order_id}, product={product}"
    log.info(f"SENT Order: {props}")

async def send_market_completion(market_order_id: str):
    """Send completion notification back to market."""
    if market_order_id not in market_orders:
        log.error(f"❌ Market order {market_order_id} not found in send_market_completion")
        return
    order_state = market_orders[market_order_id]
    completed_products = ",".join(order_state['completed'])
    
    completion = MarketOrderComplete(
        id=market_order_id,
        marketResponse=f"COMPLETED: {completed_products}"
    )
    # Use wrapper for sending
    await send_market_order_complete(completion)
    # Log with business message emoji and all properties
    props = f"id={market_order_id}, marketResponse=COMPLETED: {completed_products}"
    log.info(f"SENT MarketOrderComplete: {props}")

# ═══════════════════════════════════════════════════════════════════
# STARTUP
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    log.info("🏁 RETAILER STARTING...")
    try:
        adapter.start()
    except KeyboardInterrupt:
        log.info("🛑 RETAILER INTERRUPTED BY USER")
    except Exception as e:
        log.error(f"💥 RETAILER CRASHED: {e}")
        import traceback
        traceback.print_exc()
    finally:
        log.info("🏁 RETAILER ENDING...")

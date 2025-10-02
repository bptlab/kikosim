#!/usr/bin/env python3
"""
Market Agent - Sends product lists to retailer

Demonstrates multi-agent business protocol:
1. Market sends product lists to retailer
2. Retailer processes list and manages individual orders with supplier
3. Market receives completion notification when all products fulfilled

Production evaluation mode: Can run at specified rates with monitoring
"""
import asyncio, random, uuid
from bspl.adapter import Adapter
from configuration import systems, agents
from MarketSupplyChain import MarketOrder, MarketOrderComplete
from simple_logging import setup_logger

# Setup logging
log = setup_logger('customer')
adapter = Adapter('Customer', systems, agents)

# ═══════════════════════════════════════════════════════════════════
# BUSINESS LOGIC - Pure business functions
# ═══════════════════════════════════════════════════════════════════

def process_market_completion(market_order_id: str, response: str) -> None:
    """Process completed market order - pure business logic."""
    # Market order completion processing (business logic timing)

# ═══════════════════════════════════════════════════════════════════
# MESSAGE HANDLERS - Reaction to market order completions
# ═══════════════════════════════════════════════════════════════════

@adapter.reaction(MarketOrderComplete)
async def receive_complete_market_order(msg):
    """Handle completion notification from retailer."""
    global finished_enactments
    
    market_order_id = msg["id"]
    market_response = msg["marketResponse"]
    
    # Properties for logging
    props = f"id={market_order_id}, marketResponse={market_response}"
    
    # Business logic
    process_market_completion(market_order_id, market_response)
    
    return msg

# ═══════════════════════════════════════════════════════════════════
# INITIATOR PATTERN - Called randomly on TimeUpdate broadcasts
# ═══════════════════════════════════════════════════════════════════

# Market state for random order generation
product_catalog = ['laptop', 'mouse', 'keyboard', 'monitor']

async def initiator():
    """
    Initiator function - called randomly when TimeUpdate is received.
    
    This function will be automatically detected by the transformation system
    and called with 30% probability on each virtual time round.
    """
    
    log.info('🎯Order initiator called - generating single-product order!')
    market_order_id = f'MKT_{str(uuid.uuid4())[:8]}'
    product = random.choice(product_catalog)
    product_list_str = product  # single product as string
    market_order = MarketOrder(id=market_order_id, productList=product_list_str)
    
    await adapter.send(market_order)
    props = f'id={market_order_id}, productList={product_list_str}'
    log.info(f'SENT MarketOrder: {props}')

if __name__ == '__main__':
    log.info('🏁 Customer STARTING...')
    try:
        adapter.start()
    except KeyboardInterrupt:
        log.info('🛑 Customer INTERRUPTED BY USER')
    except Exception as e:
        log.error(f'💥 Customer CRASHED: {e}')
        import traceback
        traceback.print_exc()
    finally:
        log.info('🏁 Customer ENDING...')
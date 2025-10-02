#!/usr/bin/env python3
"""
Virtual TimeService Agent - Self-messaging coordination

Implements simplified self-messaging time coordination:
1. Agents send Reminder messages when they want to act at specific times
2. TimeService tracks all agent timing requests
3. TimeService advances virtual time to the earliest requested time
4. TimeService sends individual TimeUpdate messages to all agents
5. Agents execute due tasks and send new reminders as needed
"""

import asyncio
import signal
import sys
from typing import Dict, Optional, Set
from bspl.adapter import Adapter
from configuration import systems, agents, timeservice_spec
from simple_logging import setup_logger, set_virtual_time

# Import TimeService classes from the generated module
Hold = timeservice_spec.module.Hold
Passivate = timeservice_spec.module.Passivate
TimeUpdate = timeservice_spec.module.TimeUpdate

# ═══════════════════════════════════════════════════════════════════
# SETUP - Standard agent initialization
# ═══════════════════════════════════════════════════════════════════
adapter = Adapter("TimeService", systems, agents)
import os
log = setup_logger(
    "timeservice",
    simulation_id=os.getenv("KIKOSIM_SIMULATION_ID"),
    run_id=os.getenv("KIKOSIM_RUN_ID")
)

# Round-based virtual time coordination state
virtual_time = 0.0
round_number = 0
participating_agents: Set[str] = set()

# State for each round: agent_name -> next_time
round_agent_next_times: Dict[str, float] = {}
# Responses received for each round: round_id -> set of agent_names
round_responses: Dict[int, Set[str]] = {}
# Agent watchdog: agent_name -> last_response_round
agent_last_response: Dict[str, int] = {}

# ═══════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS - Reminder-based virtual time coordination
# ═══════════════════════════════════════════════════════════════════

def get_participating_agents():
    """Get all agents participating in time coordination from the configuration."""
    global participating_agents
    log.info("DEBUG: Starting get_participating_agents...")
    for system_id, system in systems.items():
        protocol_name = system["protocol"].name
        log.info(f"DEBUG: Checking system {system_id}. Protocol name: {protocol_name}")
        if system["protocol"].name == timeservice_spec.name:
            log.info(f"DEBUG: Protocol matches timeservice_spec.name: {timeservice_spec.name}")
            for role, agent_names in system["roles"].items():
                log.info(f"DEBUG:   Checking role: {role.name}. Agent names: {agent_names}")
                if role.name == "Agent":
                    log.info(f"DEBUG:     Role name matches 'Agent'. Adding agents.")
                    if isinstance(agent_names, list):
                        participating_agents.update(agent_names)
                    else:
                        participating_agents.add(agent_names)
                else:
                    log.info(f"DEBUG:     Role name '{role.name}' does not match 'Agent'.")
    log.info(f"👥 Identified {len(participating_agents)} participating agents.")

def check_agent_responsiveness():
    """Check for agents that haven't responded recently (watchdog system)."""
    global agent_last_response, round_number, participating_agents
    
    # Look for agents that haven't responded in the last 5 rounds
    UNRESPONSIVE_THRESHOLD = 5
    unresponsive_agents = []
    
    for agent_name in participating_agents:
        last_round = agent_last_response.get(agent_name, 0)
        rounds_since_response = round_number - last_round
        
        if rounds_since_response > UNRESPONSIVE_THRESHOLD:
            unresponsive_agents.append((agent_name, rounds_since_response))
    
    if unresponsive_agents:
        log.warning(f"🚨 WATCHDOG: {len(unresponsive_agents)} agents appear unresponsive:")
        for agent_name, rounds_silent in unresponsive_agents:
            log.warning(f"   💀 {agent_name}: no response for {rounds_silent} rounds (last: round {agent_last_response.get(agent_name, 0)})")

async def advance_virtual_time():
    """Advance time to the earliest requested time for the completed round and start a new one."""
    global virtual_time, round_number, round_agent_next_times

    # Check if we've reached the maximum number of rounds
    max_rounds = getattr(sys.modules[__name__], 'max_rounds', 200)
    if round_number >= max_rounds:
        log.info(f"🏁 Reached maximum rounds ({round_number}/{max_rounds}), shutting down simulation")
        log_final_state()
        # Send shutdown signal to all processes
        import os
        os.kill(os.getpid(), signal.SIGTERM)
        return

    # Determine next virtual time from the collected responses for the completed round
    if round_agent_next_times:
        requested_time = min(round_agent_next_times.values())
        # CRITICAL FIX: Virtual time must NEVER go backwards!
        next_virtual_time = max(virtual_time, requested_time)
        if requested_time < virtual_time:
            log.warning(f"⚠️ Agent requested past time {requested_time}, clamping to current time {virtual_time}")
    else:
        # No agent requested a specific time, so advance by a default step (e.g., 1 day)
        next_virtual_time = virtual_time
        log.info(f"😴 No specific time requested, advancing by 0 days.")

    old_time = virtual_time
    virtual_time = next_virtual_time
    set_virtual_time(virtual_time)
    # Log every time advance for debugging
    log.info(f"⏰ Virtual time advanced: {old_time} → {virtual_time}")

    # Reset for the next round
    round_number += 1
    round_agent_next_times = {}
    round_responses[round_number] = set()
    
    # Log every round for debugging
    log.info(f"🔄 Starting round {round_number}")
    await send_time_updates(virtual_time, round_number)
    
    # Start timeout monitoring for this round
    asyncio.create_task(monitor_round_timeout(round_number))

async def send_time_updates(new_time: float, round_id: int):
    """Send individual TimeUpdate messages to all agents with round-based ids, business agents first."""
    from configuration import agents as agent_config
    import random
    
    agents_notified = 0
    agent_list = list(participating_agents)
    
    # CRITICAL FIX: Separate business agents from resource agents
    business_agents = [agent for agent in agent_list if not agent.startswith('RA_')]
    resource_agents = [agent for agent in agent_list if agent.startswith('RA_')]
    
    phase_delay = 0.05  # 50ms delay between phases
    
    # Shuffle within each group to avoid always sending in same order
    random.shuffle(business_agents)
    random.shuffle(resource_agents)
    
    # PHASE 1: Send TimeUpdates to business agents first
    log.info(f"📡 Phase 1: Sending TimeUpdates to {len(business_agents)} business agents")
    for i, agent_name in enumerate(business_agents):
        unique_round_id = f"round_{round_id}_{agent_name}"
        time_update = TimeUpdate(roundId=unique_round_id, now=new_time)

        if agent_name in agent_config:
            agent_endpoints = agent_config[agent_name]
            if isinstance(agent_endpoints, list):
                time_update.dest = agent_endpoints[0]
            else:
                time_update.dest = agent_endpoints
            
            await adapter.send(time_update)
            agents_notified += 1
        else:
            log.error(f"❌ Cannot find endpoint for business agent {agent_name} in configuration.")
    
    # Wait between phases to ensure business agents process first
    await asyncio.sleep(phase_delay)
    
    # PHASE 2: Send TimeUpdates to resource agents
    log.info(f"📡 Phase 2: Sending TimeUpdates to {len(resource_agents)} resource agents")
    for i, agent_name in enumerate(resource_agents):
        unique_round_id = f"round_{round_id}_{agent_name}"
        time_update = TimeUpdate(roundId=unique_round_id, now=new_time)

        if agent_name in agent_config:
            agent_endpoints = agent_config[agent_name]
            if isinstance(agent_endpoints, list):
                time_update.dest = agent_endpoints[0]
            else:
                time_update.dest = agent_endpoints
            
            await adapter.send(time_update)
            agents_notified += 1
        else:
            log.error(f"❌ Cannot find endpoint for resource agent {agent_name} in configuration.")

    log.info(f"📡 Sent TimeUpdates to {agents_notified} agents in 2 phases: time={new_time}, round={round_id}")

async def monitor_round_timeout(expected_round_id: int):
    """Monitor for round timeout and detect dead agents."""
    global participating_agents
    
    ROUND_TIMEOUT = 30.0  # 30 seconds per round should be plenty
    await asyncio.sleep(ROUND_TIMEOUT)
    
    # Check if we're still waiting for this round (round hasn't advanced)
    if round_number == expected_round_id:
        # Timeout occurred - identify which agents didn't respond
        responding_agents = round_responses.get(expected_round_id, set())
        missing_agents = participating_agents - responding_agents
        
        log.error(f"🚨 ROUND TIMEOUT after {ROUND_TIMEOUT}s in round {expected_round_id}")
        log.error(f"💀 Missing responses from: {sorted(missing_agents)}")
        log.error(f"✅ Received responses from: {sorted(responding_agents)}")
        
        # Continue simulation without the dead agents
        log.warning(f"⚠️ Continuing simulation without {len(missing_agents)} dead agents")
        # Remove dead agents from participating set
        participating_agents = responding_agents.copy()
        
        if participating_agents:
            # Force advance to next round
            await advance_virtual_time()
        else:
            log.error(f"💥 ALL AGENTS DEAD - terminating simulation")
            import os
            os.kill(os.getpid(), signal.SIGTERM)

def log_final_state():
    """Log the final state of the TimeService for debugging."""
    log.info("🏁 TIMESERVICE ENDING...")
    log.info(f"📊 Final state: round={round_number}, virtual_time={virtual_time}")
    log.info(f"📊 Participating agents: {participating_agents}")

def signal_handler(signum, frame):
    """Handle SIGTERM and other signals gracefully."""
    log.info(f"🛑 TIMESERVICE RECEIVED SIGNAL {signum} (SIGTERM={signal.SIGTERM})")
    log_final_state()
    sys.exit(0)


async def start_coordination():
    """Initialize coordination by sending first TimeUpdate."""
    log.info("🚀 Starting virtual time coordination with self-messaging pattern")
    get_participating_agents()
    set_virtual_time(virtual_time)
    await advance_virtual_time()

# ═══════════════════════════════════════════════════════════════════
# MESSAGE HANDLERS - BSPL message reactions
# ═══════════════════════════════════════════════════════════════════

@adapter.reaction(Hold)
async def handle_hold(msg):
    """Handle Hold from an agent, record their requested time, and check if the round is complete."""
    agent_name = msg["agentName"]
    next_time = msg["nextTime"]
    round_id_str = msg["roundId"]

    try:
        round_id = int(round_id_str.split('_')[1])
    except (IndexError, ValueError):
        log.warning(f"Invalid round ID format from {agent_name}: {round_id_str}")
        return msg

    if round_id == round_number:
        if agent_name not in round_responses.get(round_id, set()):
            round_responses.setdefault(round_id, set()).add(agent_name)
            round_agent_next_times[agent_name] = next_time
            # Update watchdog tracking
            agent_last_response[agent_name] = round_id
            # Log Hold messages for debugging
            log.info(f"📨 Received Hold from {agent_name} for time {next_time} ({len(round_responses[round_id])}/{len(participating_agents)})")

            if len(round_responses[round_id]) == len(participating_agents):
                await advance_virtual_time()
        else:
            log.warning(f"Received duplicate Hold from {agent_name} in round {round_id}")
    else:
        log.warning(f"Stale Hold from {agent_name} for round {round_id}, current round is {round_number}")

    return msg

@adapter.reaction(Passivate)
async def handle_passivate(msg):
    """Handle Passivate from an agent and check if the round is complete."""
    agent_name = msg["agentName"]
    round_id_str = msg["roundId"]

    try:
        round_id = int(round_id_str.split('_')[1])
    except (IndexError, ValueError):
        log.warning(f"Invalid round ID format from {agent_name}: {round_id_str}")
        return msg

    if round_id == round_number:
        if agent_name not in round_responses.get(round_id, set()):
            round_responses.setdefault(round_id, set()).add(agent_name)
            # Update watchdog tracking
            agent_last_response[agent_name] = round_id
            # Log Passivate messages for debugging
            log.info(f"😴 Received Passivate from {agent_name} ({len(round_responses[round_id])}/{len(participating_agents)})")

            if len(round_responses[round_id]) == len(participating_agents):
                await advance_virtual_time()
        else:
            log.warning(f"Received duplicate Passivate from {agent_name} in round {round_id}")
    else:
        log.warning(f"Stale Passivate from {agent_name} for round {round_id}, current round is {round_number}")

    return msg

# ═══════════════════════════════════════════════════════════════════
# STARTUP
# ═══════════════════════════════════════════════════════════════════

async def main():
    """Main TimeService function - starts coordination and returns to let adapter handle messages."""
    log.info("⏰ TimeService starting with simplified self-messaging coordination...")
    
    # Start the coordination process
    await start_coordination()
    
    # Start periodic heartbeat task in the background
    asyncio.create_task(heartbeat_task())
    
    # Return immediately to let the adapter start its message processing loop
    log.info("✅ TimeService initialization complete, adapter will handle messages")

async def heartbeat_task():
    """Background heartbeat task to show TimeService is alive."""
    try:
        while True:
            await asyncio.sleep(30)  # Log every 30 seconds
            log.info("❤️ Heartbeat: TimeService is alive")
    except Exception as e:
        log.error(f"💥 HEARTBEAT CRASHED: {e}")
        raise

if __name__ == "__main__":
    # Parse command line arguments for max_rounds
    max_rounds = 200  # default
    if len(sys.argv) >= 3 and sys.argv[1] == "--max-rounds":
        max_rounds = int(sys.argv[2])
    elif len(sys.argv) >= 2 and sys.argv[1].isdigit():
        max_rounds = int(sys.argv[1])
    
    # Set max_rounds as module attribute so advance_virtual_time can access it
    sys.modules[__name__].max_rounds = max_rounds
    
    log.info(f"🏁 TIMESERVICE STARTING (max_rounds={max_rounds})...")
    
    # Register signal handler for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    
    try:
        adapter.start(main())
    except KeyboardInterrupt:
        log.info("🛑 TIMESERVICE INTERRUPTED BY USER")
        log_final_state()
    except Exception as e:
        log.error(f"💥 TIMESERVICE CRASHED: {e}")
        import traceback
        traceback.print_exc()
        log_final_state()
    finally:
        log_final_state()
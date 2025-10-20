#!/usr/bin/env python3
"""
Virtual Time ResourceAgent -

"""
import sys 
import asyncio
from bspl.adapter import Adapter
from configuration import systems, agents, timeservice_spec
from ResourceAgent import GiveTask, CompleteTask
from simple_logging import setup_logger, set_virtual_time
from ra_helpers import sample_duration

# Import TimeService classes from the generated module
Reminder = timeservice_spec.module.Reminder
Hold = timeservice_spec.module.Hold
Passivate = timeservice_spec.module.Passivate
TimeUpdate = timeservice_spec.module.TimeUpdate

name = sys.argv[1] # e.g. "RA_SupplierShipper_Supplier_1"
adapter = Adapter(name, systems, agents)

# Extract business agent name, agent type, and unique ID for distinct logging
# From "RA_SupplierShipper_Supplier_1" extract "Supplier", "SupplierShipper", and "1" to create "supplier_suppliershipper_1"
business_agent_name = "unknown"
agent_type = "unknown"
# Keep originals for strategy lookup in configuration
principal_for_strategy = "Unknown"
agent_type_for_strategy = "Unknown"
unique_id = ""
if "_" in name:
    parts = name.split("_")
    if len(parts) >= 2:
        agent_type_for_strategy = parts[1]
        agent_type = parts[1].lower()  # Extract "SupplierShipper" -> "suppliershipper"
    if len(parts) >= 3:
        principal_for_strategy = parts[2]
        business_agent_name = parts[2].lower()  # Extract "Supplier" -> "supplier"
    if len(parts) >= 4:
        unique_id = f"_{parts[3]}"  # Extract "1" -> "_1"

logger_name = f"{business_agent_name}_{agent_type}{unique_id}"

import os
log = setup_logger(
    logger_name,
    simulation_id=os.getenv("KIKOSIM_SIMULATION_ID"),
    run_id=os.getenv("KIKOSIM_RUN_ID")
)

# Determine assignment strategy tag for clearer task logs
try:
    from configuration import agent_strategies as _agent_strategies
    _strategy = _agent_strategies.get((principal_for_strategy, agent_type_for_strategy), "round_robin")
except Exception:
    _strategy = "round_robin"
# for debugging purposes, you can see the selected strategy for each task in disco by uncommenting the next line
# strategy_tag = "strat_rand" if _strategy == "random" else "strat_round" 
strategy_tag = ""

# =================================================================
# STATE MANAGEMENT
# =================================================================

# Current state
current_virtual_time = 0.0
current_task = None      # {'task_id': str, 'completion_time': float, 'msg': dict, 'id': str, 'task_type': str}
task_queue = []          # List of tasks waiting to start

@adapter.reaction(GiveTask)
async def handle_task(msg):
    """Queue task for execution - never start immediately."""
    try:
        task_id = msg["taskID"]
        id_value = msg["id"]  # Must be present - fail clearly if missing
        task_type = msg["taskType"]
        
        # Parse duration - always positive
        try:
            duration = sample_duration(msg["duration"])
        except (ValueError, TypeError) as e:
            log.error(f"💥 Error parsing duration '{msg['duration']}': {e}")
            try:
                duration = float(msg["duration"])
                log.warning(f"⚠️ Used fallback float parsing for duration: {duration}")
            except (ValueError, TypeError):
                log.error(f"💥 Could not parse duration '{msg['duration']}'")
                return msg
        
        if duration <= 0:
            log.error(f"💥 Invalid duration value: {duration} (must be positive)")
            return msg

        # Always queue the task
        task_info = {
            'task_id': task_id,
            'duration': duration,
            'msg': msg,
            'id': id_value,
            'task_type': task_type
        }
        task_queue.append(task_info)
        
        log.info(f"TASK_QUEUED {id_value}: [taskID={task_id}, taskType={task_type}|{strategy_tag}, duration={duration:.1f}d, queue_pos={len(task_queue)}]")
        
        return msg
    except Exception as e:
        log.error(f"💥 Error queuing task: {e}")
        return msg

async def complete_task(task_info):
    """Complete a task and send CompleteTask message to business agent."""
    try:
        # Find the business agent (Principal) from current agent name
        current_agent_name = adapter.name
        parts = current_agent_name.split('_')
        if len(parts) >= 3:
            principal_name = parts[2]
        else:
            principal_name = "Unknown"
        
        # Create CompleteTask message
        complete_msg = CompleteTask(
            taskID=task_info['task_id'], 
            id=task_info['id'], 
            taskType=task_info['task_type']
        )
        
        # Set destination
        from configuration import agents
        if principal_name in agents:
            business_agent_endpoints = agents[principal_name]
            if isinstance(business_agent_endpoints, list):
                complete_msg.dest = business_agent_endpoints[0]
            else:
                complete_msg.dest = business_agent_endpoints
        else:
            log.error(f"❌ Cannot find business agent '{principal_name}' in agents config")
            raise RuntimeError(f"Principal '{principal_name}' not found")

        log.info(f"TASK_COMPLETED {task_info['id']}: [taskID={task_info['task_id']}, taskType={task_info['task_type']}|{strategy_tag}]")
        await adapter.send(complete_msg)
        
    except Exception as e:
        log.error(f"💥 Error completing task {task_info['task_id']}: {e}")

async def send_self_reminder(round_id: str):
    """Send self a reminder for timing coordination."""
    try:
        reminder = Reminder(roundId=round_id)
        
        from configuration import agents
        if adapter.name in agents:
            agent_endpoints = agents[adapter.name]
            if isinstance(agent_endpoints, list):
                reminder.dest = agent_endpoints[0]
            else:
                reminder.dest = agent_endpoints
            
            await adapter.send(reminder)
        else:
            log.error(f"❌ Cannot find own endpoint for {adapter.name}")
            
    except Exception as e:
        log.error(f"💥 Error sending self reminder: {e}")

async def send_hold(round_id: str, next_time: float):
    """Send Hold message to TimeService."""
    try:
        from configuration import agents
        if "TimeService" in agents:
            agent_endpoints = agents["TimeService"]
            if isinstance(agent_endpoints, list):
                timeservice_endpoint = agent_endpoints[0]
            else:
                timeservice_endpoint = agent_endpoints
            
            hold_msg = Hold(roundId=round_id, agentName=adapter.name, nextTime=next_time)
            hold_msg.dest = timeservice_endpoint
            await adapter.send(hold_msg)
            log.info(f"📤 Sent Hold to TimeService: round {round_id}, next action at day {next_time}")
        else:
            log.error(f"❌ Cannot find TimeService in agents config")
    except Exception as e:
        log.error(f"💥 Error sending Hold message: {e}")

async def send_passivate(round_id: str):
    """Send Passivate message to TimeService."""
    try:
        from configuration import agents
        if "TimeService" in agents:
            agent_endpoints = agents["TimeService"]
            if isinstance(agent_endpoints, list):
                timeservice_endpoint = agent_endpoints[0]
            else:
                timeservice_endpoint = agent_endpoints
            
            passivate_msg = Passivate(roundId=round_id, agentName=adapter.name)
            passivate_msg.dest = timeservice_endpoint
            await adapter.send(passivate_msg)
            log.info(f"📤 Sent Passivate to TimeService: round {round_id}")
        else:
            log.error(f"❌ Cannot find TimeService in agents config")
    except Exception as e:
        log.error(f"💥 Error sending Passivate message: {e}")

# =================================================================
# TIME COORDINATION
# =================================================================

@adapter.reaction(TimeUpdate)
async def handle_time_update(msg):
    """Handle TimeUpdate - execute tasks and manage state transitions."""
    global current_virtual_time, current_task
    
    round_id = msg["roundId"]
    old_time = current_virtual_time
    current_virtual_time = msg["now"]
    
    # Update global virtual time for logging
    set_virtual_time(current_virtual_time)
    
    # Log time updates occasionally
    if int(current_virtual_time) % 10 == 0 or current_virtual_time < 5:
        log.info(f"🕐 Time updated from {old_time} to {current_virtual_time} (round {round_id})")
    
    # 1. Complete current task if ready
    if current_task and current_virtual_time >= current_task['completion_time']:
        await complete_task(current_task)
        current_task = None
        log.info(f"🎯 Task completed, now IDLE")
    
    # 2. Start next task if idle and queue not empty
    if current_task is None and task_queue:
        next_task = task_queue.pop(0)
        
        # Calculate completion time - ALWAYS in the future
        completion_time = current_virtual_time + next_task['duration']
        
        current_task = {
            'task_id': next_task['task_id'],
            'completion_time': completion_time,
            'msg': next_task['msg'],
            'id': next_task['id'],
            'task_type': next_task['task_type']
        }
        
        log.info(f"TASK_STARTED {current_task['id']}: [taskID={current_task['task_id']}, taskType={current_task['task_type']}|{strategy_tag}, time=day {current_virtual_time}, completion=day {completion_time}]")
        
        # Check if task completes immediately (shouldn't happen with positive durations)
        if completion_time <= current_virtual_time:
            log.warning(f"⚠️ Task completes immediately - duration was too small")
            await complete_task(current_task)
            current_task = None
    
    # 3. Send timing coordination
    await send_self_reminder(round_id)
    
    return msg

@adapter.reaction(Reminder)
async def handle_reminder(msg):
    """Handle self-sent reminder - coordinate with TimeService."""
    global current_task
    
    round_id = msg["roundId"]
    
    if current_task:
        # We have a task in progress - hold until completion
        next_time = current_task['completion_time']
        
        # CRITICAL: Ensure we never request a past time
        if next_time <= current_virtual_time:
            log.error(f"💥 CRITICAL BUG: Trying to hold until past time {next_time} (current: {current_virtual_time})")
            log.error(f"Task info: {current_task}")
            # Emergency fallback: hold until current_time + small delta
            next_time = current_virtual_time + 0.1
        
        await send_hold(round_id, next_time)
    else:
        # We're idle - passivate
        await send_passivate(round_id)
    
    return msg

# =================================================================
# STARTUP
# =================================================================

async def startup_actions():
    """Startup actions for the resource agent."""
    log.info(f"🔗 {name} ready for virtual time coordination (SIMPLIFIED)")

if __name__ == "__main__":
    log.info("🏁 RESOURCE AGENT STARTING (FIXED VERSION)...")
    try:
        adapter.start(startup_actions())
    except KeyboardInterrupt:
        log.info("🛑 RESOURCE AGENT INTERRUPTED BY USER")
    except Exception as e:
        log.error(f"💥 RESOURCE AGENT CRASHED: {e}")
        import traceback
        traceback.print_exc()
    finally:
        log.info("🏁 RESOURCE AGENT ENDING...")

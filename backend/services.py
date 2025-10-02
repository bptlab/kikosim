"""
This module provides the core business logic and services for the KikoSim backend.

It is responsible for managing the in-memory data stores for simulations and runs,
handling the lifecycle of simulation processes, and providing helper functions for
tasks such as port allocation, ID generation, and log processing. The services in
this module are called by the API endpoints defined in `main.py`.

Key responsibilities include:
- **Data Storage**: Manages the `simulations_store` and `runs_store` dictionaries,
  which act as a simple in-memory database.
- **Simulation Execution**: The `run_simulation_background` function orchestrates
  the entire process of running a simulation, from transformation to execution
  and result handling.
- **Port Management**: Dynamically allocates and releases network ports for agent
  communication to prevent conflicts between concurrent simulation runs.
- **Real-time Updates**: Contains the logic for broadcasting real-time updates to
  clients via WebSockets, including virtual time progress.
- **Log Handling**: Provides functions for retrieving, parsing, and exporting
  simulation logs.
"""

import asyncio
import json
import re
import socket
import subprocess
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List, Set
from fastapi import HTTPException, WebSocket
from haikunator import Haikunator

from models import SimulationStatus, VirtualTimeStatus
from constants import (
    DEFAULT_BUSINESS_PORT_START, DEFAULT_RESOURCE_PORT_START, PORT_SAFETY_BUFFER,
    MAX_PORT_NUMBER, REDIS_PORT, REDIS_HOST, REDIS_DB, REDIS_STARTUP_DELAY_SECONDS,
    VIRTUAL_TIME_UPDATE_INTERVAL_SECONDS, ERROR_RETRY_DELAY_SECONDS
)
from ra_transformer_lib import (
    transform_agents_from_content, 
    run_simulation_async, 
    cleanup_simulation,
    SimulationConfig,
    create_default_config
)


# In-memory storage
simulations_store: Dict[str, Dict] = {}
runs_store: Dict[str, Dict] = {}
running_tasks: Dict[str, asyncio.Task] = {}
active_connections: List[WebSocket] = []

# Port allocation management
allocated_ports: Set[int] = set()  # Track allocated ports globally
run_port_ranges: Dict[str, Dict[str, int]] = {}  # run_id -> {"business_base": 8000, "resource_base": 9000}

# ID generators
haikunator = Haikunator()


def create_run_id() -> str:
    """Generates a unique, memorable run ID like 'adjective-noun-noun'."""
    while True:
        adj_noun = haikunator.haikunate(token_length=0)
        noun2 = haikunator.haikunate(token_length=0).split('-')[1]
        name = f"{adj_noun}-{noun2}"
        
        if name not in runs_store:
            return name


def create_simulation_id() -> str:
    return str(uuid.uuid4())[:8]


def is_port_available(port: int) -> bool:
    """Check if a specific port is available for use."""
    try:
        # Check UDP (BSPL uses UDP)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.bind(('127.0.0.1', port))
        return True
    except OSError:
        return False


def find_available_port_range(start_port: int, count: int) -> Optional[int]:
    """Find a contiguous range of available ports starting from start_port."""
    for base_port in range(start_port, MAX_PORT_NUMBER - count):
        # Skip if any port in this range is already allocated
        if any(port in allocated_ports for port in range(base_port, base_port + count)):
            continue
            
        # Check if all ports in range are actually available
        if all(is_port_available(port) for port in range(base_port, base_port + count)):
            return base_port
    
    return None


def allocate_ports_for_run(run_id: str, business_agent_count: int, resource_agent_count: int) -> Dict[str, int]:
    """
    Allocate port ranges for a simulation run.
    
    Returns:
        Dict with 'business_base' and 'resource_base' port numbers
    """
    # Calculate total ports needed
    total_business_ports = business_agent_count + 1  # +1 for TimeService
    total_resource_ports = resource_agent_count
    
    # Find available business agent ports (starting from 8000)
    business_base = find_available_port_range(DEFAULT_BUSINESS_PORT_START, total_business_ports)
    if business_base is None:
        raise RuntimeError(f"Cannot find {total_business_ports} contiguous ports for business agents")
    
    # Find available resource agent ports (starting from 9000, or after business ports)
    resource_start = max(DEFAULT_RESOURCE_PORT_START, business_base + total_business_ports + PORT_SAFETY_BUFFER)
    resource_base = find_available_port_range(resource_start, total_resource_ports)
    if resource_base is None:
        raise RuntimeError(f"Cannot find {total_resource_ports} contiguous ports for resource agents")
    
    # Mark all ports as allocated
    for port in range(business_base, business_base + total_business_ports):
        allocated_ports.add(port)
    for port in range(resource_base, resource_base + total_resource_ports):
        allocated_ports.add(port)
    
    # Store the allocation
    port_allocation = {
        "business_base": business_base,
        "resource_base": resource_base,
        "business_count": total_business_ports,
        "resource_count": total_resource_ports
    }
    run_port_ranges[run_id] = port_allocation
    
    print(f"🔌 Allocated ports for run {run_id}:")
    print(f"   Business agents: {business_base}-{business_base + total_business_ports - 1}")
    print(f"   Resource agents: {resource_base}-{resource_base + total_resource_ports - 1}")
    
    return port_allocation


def release_ports_for_run(run_id: str):
    """Release all ports allocated for a specific run."""
    if run_id not in run_port_ranges:
        return
    
    allocation = run_port_ranges[run_id]
    
    # Release business agent ports
    for port in range(allocation["business_base"], allocation["business_base"] + allocation["business_count"]):
        allocated_ports.discard(port)
    
    # Release resource agent ports  
    for port in range(allocation["resource_base"], allocation["resource_base"] + allocation["resource_count"]):
        allocated_ports.discard(port)
    
    del run_port_ranges[run_id]
    print(f"🔌 Released ports for run {run_id}")


async def start_redis_server():
    """Start Redis server for simulation logging."""
    print("🔴 Starting Redis server for simulation logging...")
    try:
        # Check if Redis is already running
        import redis
        redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
        redis_client.ping()
        print("✅ Redis server is already running")
        return True
    except:
        # Redis not running, try to start it
        try:
            subprocess.Popen([
                "redis-server", "--port", str(REDIS_PORT), "--daemonize", "yes"
            ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            await asyncio.sleep(REDIS_STARTUP_DELAY_SECONDS)  # Give Redis time to start
            
            # Test connection
            redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
            redis_client.ping()
            print("✅ Redis server started successfully")
            return True
        except Exception as e:
            print(f"⚠️ Failed to start Redis: {e}")
            print("   Make sure Redis is installed: brew install redis")
            return False


def get_simulation(simulation_id: str) -> Dict:
    if simulation_id not in simulations_store:
        raise HTTPException(status_code=404, detail=f"Simulation {simulation_id} not found")
    return simulations_store[simulation_id]


def get_run(run_id: str) -> Dict:
    if run_id not in runs_store:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return runs_store[run_id]


def get_runs_for_simulation(simulation_id: str) -> List[Dict]:
    return [run for run in runs_store.values() if run["simulation_id"] == simulation_id]


async def notify_clients():
    """Notify all connected clients about an update."""
    for connection in active_connections:
        await connection.send_json({"event": "update"})


async def update_run_status(run_id: str, status: SimulationStatus, **kwargs):
    run = runs_store[run_id]
    run["status"] = status
    run["updated_at"] = datetime.now()
    for key, value in kwargs.items():
        run[key] = value
    await notify_clients()


def get_virtual_time_status(run_id: str) -> Optional[VirtualTimeStatus]:
    """Get current virtual time status from Redis logs."""
    try:
        import redis
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
        
        # Test Redis connection
        r.ping()
        
        # Get the run to find simulation_id
        run = runs_store.get(run_id)
        if not run:
            return None
        
        simulation_id = run["simulation_id"]
        
        # Get timeservice logs for round info using hierarchical key
        timeservice_key = f"logs:{simulation_id}:{run_id}:timeservice"
        
        # Check if key exists
        if not r.exists(timeservice_key):
            return None
        
        timeservice_logs = r.lrange(timeservice_key, 0, 20)  # Get more recent logs
        current_round = 0
        current_virtual_time = 0.0
        
        
        for log_entry in timeservice_logs:
            try:
                log_data = json.loads(log_entry)
                message = log_data.get('message', '')
                entry_virtual_time = log_data.get('virtual_time', 0.0)
                
                # Extract round number from messages
                round_match = re.search(r'Starting round (\d+)', message)
                if round_match:
                    round_num = int(round_match.group(1))
                    current_round = max(current_round, round_num)
                
                # Extract round from "round=X" pattern 
                round_match2 = re.search(r'round=(\d+)', message)
                if round_match2:
                    round_num = int(round_match2.group(1))
                    current_round = max(current_round, round_num)
                
                # Use virtual_time metadata from log entry
                if entry_virtual_time > current_virtual_time:
                    current_virtual_time = entry_virtual_time
                    
            except Exception as e:
                print(f"⚠️ Error parsing log entry: {e}")
                continue
        
        
        # Get run's max_rounds setting
        run = runs_store.get(run_id, {})
        max_rounds = run.get('max_rounds', 200)
        
        # Calculate progress
        progress_percentage = min((current_round / max_rounds) * 100, 100.0)
        
        # Get log counts for each agent in this specific run
        log_pattern = f"logs:{simulation_id}:{run_id}:*"
        log_keys = r.keys(log_pattern)
        agent_activity = {}
        
        for key in log_keys:
            # Extract logger name from hierarchical key (last part)
            key_parts = key.split(":")
            logger_name = key_parts[-1] if key_parts else key
            count = r.llen(key)
            agent_activity[logger_name] = count
        
        # Get recent activity and extract virtual time from it as backup
        recent_activity = []
        for log_entry in timeservice_logs[:3]:
            try:
                log_data = json.loads(log_entry)
                message = log_data.get('message', '')
                timestamp = log_data.get('timestamp', '')
                recent_activity.append(f"{timestamp}: {message}")
                
                        
            except Exception as e:
                print(f"⚠️ Error parsing recent activity: {e}")
                continue
        
        
        return VirtualTimeStatus(
            current_round=current_round,
            max_rounds=max_rounds,
            current_virtual_time=current_virtual_time,
            progress_percentage=progress_percentage,
            agent_activity=agent_activity,
            recent_activity=recent_activity
        )
        
    except Exception as e:
        print(f"⚠️ Redis monitoring failed: {e}")
        return None


async def broadcast_virtual_time_updates():
    """Background task to broadcast virtual time updates for running simulations."""
    while True:
        try:
            # Get all running simulations
            running_runs = [run_id for run_id, run in runs_store.items() 
                          if run["status"] == SimulationStatus.RUNNING]
            
            # Broadcast virtual time status for each running simulation
            for run_id in running_runs:
                virtual_time_status = get_virtual_time_status(run_id)
                if virtual_time_status and active_connections:
                    message = {
                        "event": "virtual_time_update",
                        "run_id": run_id,
                        "data": virtual_time_status.dict()
                    }
                    
                    # Send to all connected clients
                    disconnected = []
                    for connection in active_connections:
                        try:
                            await connection.send_json(message)
                        except:
                            disconnected.append(connection)
                    
                    # Remove disconnected clients
                    for conn in disconnected:
                        if conn in active_connections:
                            active_connections.remove(conn)
            
            await asyncio.sleep(VIRTUAL_TIME_UPDATE_INTERVAL_SECONDS)  # Update every 2 seconds
            
        except Exception as e:
            print(f"⚠️ Virtual time broadcast error: {e}")
            await asyncio.sleep(ERROR_RETRY_DELAY_SECONDS)  # Wait longer on error


async def run_simulation_background(run_id: str, max_rounds: int = 200):
    """Background task to run a specific run."""
    simulation_result = None
    try:
        run = runs_store[run_id]
        simulation = simulations_store[run["simulation_id"]]
        
        await update_run_status(run_id, SimulationStatus.RUNNING)
        print(f"🚀 Starting run {run_id}")
        
        # Always regenerate transformation for fresh config
        print(f"🔄 Regenerating transformation with latest config")
        
        # Add max_rounds to config overrides for transformation
        config_with_rounds = run["config"].copy() if run["config"] else {}
        config_with_rounds["max_rounds"] = max_rounds
        
        sim_config = SimulationConfig(max_rounds=max_rounds)
        start_time = time.time()
        
        # Allocate ports for this simulation run
        sim = simulations_store[run["simulation_id"]]
        business_agent_count = len(sim["agent_files"])
        
        # Calculate resource agent count from config
        resource_agent_count = 0
        if run["config"] and "AGENT_POOLS" in run["config"]:
            for principal, pools_list in run["config"]["AGENT_POOLS"].items():
                for pool_dict in pools_list:
                    for agent_type, count in pool_dict.items():
                        resource_agent_count += count
        else:
            # Default: 1 resource agent per business agent
            resource_agent_count = business_agent_count
        
        port_allocation = allocate_ports_for_run(run_id, business_agent_count, resource_agent_count)
        
        # Regenerate transformation with allocated ports
        transformation_result = transform_agents_from_content(
            agent_contents=simulation["agent_files"],
            bspl_content=simulation["bspl_content"],
            bspl_filename=simulation["bspl_filename"],
            config_overrides=config_with_rounds,
            business_base_port=port_allocation["business_base"],
            resource_base_port=port_allocation["resource_base"]
        )
        
        if not transformation_result.success:
            error_msg = f"Transformation failed: {'; '.join(transformation_result.errors)}"
            await update_run_status(run_id, SimulationStatus.FAILED, error_message=error_msg)
            print(f"❌ {error_msg}")
            release_ports_for_run(run_id)  # Clean up allocated ports
            return

        # Use the web app run_id for the simulation directory name
        working_dir = Path("simulation_runs") / f"run_{run_id}"
        print(f"📁 Simulation directory: {working_dir}")
        
        simulation_result = await run_simulation_async(
            transformation_result, 
            config=sim_config, 
            working_dir=working_dir,
            simulation_id=run["simulation_id"],
            run_id=run_id
        )
        execution_time = time.time() - start_time
        
        if simulation_result.timed_out:
            await update_run_status(
                run_id,
                SimulationStatus.TIMED_OUT,
                execution_time=execution_time,
                message_count=len(simulation_result.logs),
                simulation_result=simulation_result,
                error_message=f"Simulation timed out after {execution_time:.1f}s."
            )
            print(f"⌛️ Run {run_id} timed out after {execution_time:.2f}s")
            release_ports_for_run(run_id)
        elif simulation_result.success:
            await update_run_status(
                run_id, 
                SimulationStatus.COMPLETE,
                execution_time=execution_time,
                message_count=len(simulation_result.logs),
                simulation_result=simulation_result
            )
            print(f"✅ Run {run_id} completed in {execution_time:.2f}s")
            release_ports_for_run(run_id)
        else:
            error_message = "; ".join(simulation_result.errors) if simulation_result.errors else f"Simulation failed with exit code {simulation_result.exit_code}"
            await update_run_status(
                run_id,
                SimulationStatus.FAILED,
                execution_time=execution_time,
                error_message=error_message,
                simulation_result=simulation_result
            )
            print(f"❌ Run {run_id} failed: {error_message}")
            release_ports_for_run(run_id)
            
    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Exception: {str(e)}\nTraceback: {tb}"
        await update_run_status(
            run_id,
            SimulationStatus.FAILED,
            error_message=error_message
        )
        print(f"💥 Run {run_id} crashed: {e}")
        release_ports_for_run(run_id)  # Clean up ports on exception
    finally:
        if simulation_result:
            cleanup_simulation(simulation_result)
        if run_id in running_tasks:
            del running_tasks[run_id]
        await notify_clients()


def parse_bspl_protocols(bspl_file_path: Path) -> dict:
    """
    Parse BSPL file to extract key parameters and message types.
    
    Args:
        bspl_file_path: Path to the BSPL file
        
    Returns:
        Dict with 'key_params' and 'message_types'
    """
    try:
        with open(bspl_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find parameters section and extract key parameters
        key_params = []
        import re
        params_match = re.search(r'parameters\s+([^}]+)', content, re.DOTALL)
        if params_match:
            params_text = params_match.group(1)
            # Find all "out <name> key" patterns - these are the case identifiers
            key_params = re.findall(r'out\s+(\w+)\s+key', params_text, re.IGNORECASE)
            print(f"📋 BSPL Analysis: Found {len(key_params)} key parameters: {key_params}")
        
        # Extract message types from protocol interactions
        message_types = re.findall(r'\w+\s*→\s*\w+:\s*(\w+)\[', content)
        message_types = list(set(message_types))  # Remove duplicates
        print(f"📋 BSPL Analysis: Found {len(message_types)} message types: {message_types}")
        
        return {'key_params': list(set(key_params)), 'message_types': message_types}
    except Exception as e:
        print(f"Warning: Could not parse BSPL file {bspl_file_path}: {e}")
        return {'key_params': [], 'message_types': []}

def export_run_logs_to_csv(run_id: str) -> str:
    """
    Export run logs to a CSV file for process mining.
    Args:
        run_id: The ID of the run to export.
    Returns:
        A string containing the CSV data.
    """
    run = get_run(run_id)
    simulation_id = run["simulation_id"]

    working_dir = Path("simulation_runs") / f"run_{run_id}"
    agent_logs_dir = working_dir / "agent_logs" / simulation_id / run_id

    if not agent_logs_dir.exists():
        raise HTTPException(status_code=404, detail="Exported logs not found")

    # Parse BSPL files to discover key parameters and message types dynamically
    key_parameters = []
    message_types = []
    for bspl_file in working_dir.glob("*.bspl"):
        if "timeservice" not in bspl_file.name.lower():  # Skip technical protocols
            bspl_data = parse_bspl_protocols(bspl_file)
            key_parameters.extend(bspl_data['key_params'])
            message_types.extend(bspl_data['message_types'])
    
    # Remove duplicates and ensure we have some fallback
    key_parameters = list(set(key_parameters))
    message_types = list(set(message_types))
    if not key_parameters:
        # Fallback to common patterns if no BSPL found
        key_parameters = ['id', 'ID', 'orderID']

    log_entries = []
    ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]|\[\d+m')

    # Keywords to identify and exclude non-business-protocol logs
    FILTER_KEYWORDS = [
        # Time management
        "timeupdate", "passivate", "hold", "timeservice", "virtual time",
        "self reminder", "next action", "starting round",
        # Resource/task management - keep "givetask" in business logs, filter out internal scheduling
        "completetask", "scheduled task",
    ]

    for log_file in agent_logs_dir.glob("*.log"):
        agent_name = log_file.stem
        with open(log_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                # Extract timestamp and agent info from log line format: "2020-01-01 09:00:00.123 category:agent_name: message"
                timestamp_match = re.match(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d{3})?)\s+([^:]+):([^:]+(?:::[^:]+)?):?\s*(.*)$', line)
                if timestamp_match:
                    timestamp = timestamp_match.group(1)
                    log_category = timestamp_match.group(2)  # "resource", "business", etc.
                    extracted_agent_name = timestamp_match.group(3)  # "retailer_resource_1", "supplier::resource", "Retailer", etc.
                    message = timestamp_match.group(4)
                    
                    # Use extracted agent name if it's a resource agent, otherwise use filename
                    if "_resource" in extracted_agent_name or "::" in extracted_agent_name:
                        agent_name = extracted_agent_name
                else:
                    # Skip malformed lines
                    continue
                
                # No need for deduplication - fixed at source in simple_logging.py
                
                clean_message = ansi_escape.sub('', message).lower()
                clean_message = re.sub(r'\[\d+m', '', clean_message)

                # Filter out logs containing any of the keywords
                if any(keyword in clean_message for keyword in FILTER_KEYWORDS):
                    continue

                case_id = None
                activity_name = ""

                # SIMPLIFIED: Two keyword-based patterns for business log extraction
                
                # Pattern 1: Business Protocol Messages - "SENT MessageType: id=X, ..."
                sent_match = re.search(r'SENT\s+(\w+):\s*(.+)', message)
                if sent_match:
                    message_type = sent_match.group(1)
                    properties_text = sent_match.group(2)
                    # Extract case_id from properties (look for id=...)
                    case_id_match = re.search(r'id=([^,\s]+)', properties_text)
                    case_id = case_id_match.group(1) if case_id_match else "unknown"
                    activity_name = f"{agent_name}: Send {message_type}"
                
                # Pattern 2: Resource Task Events - "TASK_QUEUED case_id: [taskID=X, taskType=Y, ...]"
                task_match = re.search(r'TASK_(QUEUED|STARTED|COMPLETED)\s+([^:]+):\s*\[(.+)\]', message)
                if task_match:
                    task_action = task_match.group(1).lower().capitalize()  # Queued, Started, Completed
                    case_id = task_match.group(2).strip()
                    properties_text = task_match.group(3)
                    # Extract taskType from properties
                    task_type_match = re.search(r'taskType=([^,\]]+)', properties_text)
                    task_type = task_type_match.group(1) if task_type_match else ""
                    activity_name = f"{agent_name}: {task_action} Task ({task_type})" if task_type else f"{agent_name}: {task_action} Task"

                if case_id and activity_name:
                    # Clean ANSI escape codes from activity name
                    clean_activity_name = ansi_escape.sub('', activity_name)
                    clean_activity_name = re.sub(r'\[\d+m', '', clean_activity_name)
                    
                    log_entries.append({
                        "enactment_id": case_id,
                        "activity_name": clean_activity_name,
                        "timestamp": timestamp,
                        "agent_name": agent_name
                    })

    log_entries.sort(key=lambda x: x.get("timestamp", ""))

    import io
    import csv
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["enactment_id", "activity_name", "timestamp", "agent_name"])
    for entry in log_entries:
        writer.writerow([entry["enactment_id"], entry["activity_name"], entry["timestamp"], entry["agent_name"]])

    return output.getvalue()
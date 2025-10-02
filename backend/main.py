#!/usr/bin/env python3
"""
This module implements the main FastAPI application for the KikoSim backend.

The backend serves as a web-based interface to the `ra_transformer_lib`, providing
a RESTful API for creating, managing, and executing multi-agent simulations. It
handles the entire simulation lifecycle, from transforming agent code to running
the simulation and storing the results.

Key Features:
- **Simulation Management**: Create simulations by uploading agent and BSPL files.
- **Run Management**: Create multiple "runs" for each simulation, each with its
  own configuration. This allows for easy experimentation and comparison of
  different simulation parameters.
- **Configuration**: A flexible configuration system allows users to override
  default settings for resource agent pools and task durations.
- **Execution**: Asynchronously execute simulation runs in the background.
- **Real-time Updates**: A WebSocket endpoint provides real-time updates on the
  status of simulations and runs to connected clients.
- **Results and Logging**: Store and retrieve detailed logs and results for each
  simulation run.
- **Data Export**: Export simulation logs to CSV for analysis in process mining
  tools like Disco.
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
import uvicorn

# Add the ra_transformer_lib to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "ra_transformer_lib_src"))

from ra_transformer_lib import (
    transform_agents_from_content, 
    create_default_config,
    validate_agent_content,
    validate_bspl_content
)

# Import validation from dedicated module (avoids simulation dependencies)
from ra_transformer_lib.duration_validation import validate_task_settings

# Import our modules
from models import (
    SimulationStatus, CreateSimulationRequest, CreateRunRequest, 
    UpdateRunConfigRequest, ExecuteRunRequest, DuplicateRunRequest,
    VirtualTimeStatus, SimulationInfo, RunInfo
)
from constants import ALLOWED_ORIGINS, BACKEND_PORT, LARGE_LOG_QUERY_LIMIT
from services import (
    simulations_store, runs_store, running_tasks, active_connections,
    create_simulation_id, create_run_id, get_simulation, get_run,
    get_runs_for_simulation, notify_clients, update_run_status,
    get_virtual_time_status, broadcast_virtual_time_updates,
    run_simulation_background, start_redis_server, export_run_logs_to_csv
)


app = FastAPI(
    title="KikoSim Backend", 
    version="1.0.0",
    description="Multi-agent business process simulation API"
)

# Add request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = datetime.now()
    
    # Log the incoming request
    if request.method == "POST" and request.url.path == "/simulations":
        print(f"🌐 {request.method} {request.url.path} - Client: {request.client.host}")
        
        # Try to read and log the request body for debugging
        try:
            body = await request.body()
            print(f"   Request body size: {len(body)} bytes")
            if len(body) > 0:
                print(f"   Content-Type: {request.headers.get('content-type', 'unknown')}")
            else:
                print(f"   ⚠️ Empty request body received!")
        except Exception as e:
            print(f"   ⚠️ Could not read request body: {e}")
        
        # Recreate request with body for downstream processing
        async def receive():
            return {"type": "http.request", "body": body}
        request._receive = receive
    
    # Process the request
    response = await call_next(request)
    
    # Log the response
    if request.method == "POST" and request.url.path == "/simulations":
        duration = (datetime.now() - start_time).total_seconds()
        print(f"   → Response: {response.status_code} (took {duration:.3f}s)")
        
        if response.status_code >= 400:
            print(f"   ❌ Error response: {response.status_code}")
    
    return response

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add exception handlers for better error logging
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    print(f"❌ Request validation error on {request.method} {request.url.path}:")
    for error in exc.errors():
        print(f"   • {error['loc']}: {error['msg']} (type: {error['type']})")
        if 'input' in error:
            print(f"     Input: {error['input']}")
    
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": exc.body}
    )

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if request.url.path == "/simulations" and request.method == "POST":
        print(f"❌ HTTP exception on POST /simulations: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

# ============================================================================
# WEBSOCKET ENDPOINT
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Provides a WebSocket endpoint for real-time communication with clients.

    When a client connects, it is added to a list of active connections. The
    backend can then push updates (e.g., simulation status changes) to all
    connected clients.
    """
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_connections.remove(websocket)

# ============================================================================
# SIMULATION ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    """The root endpoint, providing basic status information."""
    return {"status": "KikoSim Backend", "version": "3.0.0"}

@app.post("/simulations", response_model=SimulationInfo)
async def create_simulation(request: CreateSimulationRequest):
    """
    Creates a new simulation from a set of agent files and a BSPL protocol.

    This endpoint receives the raw content of the agent and BSPL files,
    validates them, and stores them as a new simulation.
    """
    print(f"📨 POST /simulations - Creating new simulation")
    print(f"   Description: {request.description}")
    print(f"   Agent files: {list(request.agent_files.keys())}")
    print(f"   BSPL filename: {request.bspl_filename}")
    print(f"   BSPL content length: {len(request.bspl_content)} characters")
    
    try:
        validation_warnings = []
        for filename, content in request.agent_files.items():
            print(f"   Validating agent file: {filename} ({len(content)} characters)")
            is_valid, errors, warnings = validate_agent_content(content)
            if not is_valid:
                error_msg = f"Invalid agent file {filename}: {'; '.join(errors)}"
                print(f"❌ Validation failed: {error_msg}")
                raise HTTPException(
                    status_code=400, 
                    detail=error_msg
                )
            if warnings:
                for warning in warnings:
                    warning_msg = f"⚠️ File {filename}: {warning}"
                    print(warning_msg)
                    validation_warnings.append(warning_msg)
        
        print(f"   Validating BSPL content...")
        is_valid, errors = validate_bspl_content(request.bspl_content)
        if not is_valid:
            error_msg = f"Invalid BSPL content: {'; '.join(errors)}"
            print(f"❌ BSPL validation failed: {error_msg}")
            raise HTTPException(
                status_code=400,
                detail=error_msg
            )
    except HTTPException as e:
        print(f"❌ Simulation creation failed with 400 error: {e.detail}")
        raise
    except Exception as e:
        print(f"❌ Unexpected error during simulation creation: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )
    
    simulation_id = create_simulation_id()
    now = datetime.now()
    
    simulations_store[simulation_id] = {
        "simulation_id": simulation_id,
        "created_at": now,
        "updated_at": now,
        "description": request.description,
        "agent_files": request.agent_files,
        "bspl_content": request.bspl_content,
        "bspl_filename": request.bspl_filename,
        "agent_count": len(request.agent_files)
    }
    
    print(f"📝 Created simulation {simulation_id} with {len(request.agent_files)} agents")
    if validation_warnings:
        print(f"⚠️ Simulation created with {len(validation_warnings)} warnings")
    await notify_clients()
    
    return SimulationInfo(
        simulation_id=simulation_id,
        created_at=now,
        updated_at=now,
        description=request.description,
        agent_count=len(request.agent_files),
        bspl_filename=request.bspl_filename,
        run_count=0,
        warnings=validation_warnings if validation_warnings else None
    )

@app.get("/simulations")
async def list_simulations():
    """
    Lists all available simulations and their associated runs.
    """
    simulations_with_runs = []
    
    for sim_id, sim in simulations_store.items():
        runs = get_runs_for_simulation(sim_id)
        simulations_with_runs.append({
            "simulation_id": sim_id,
            "created_at": sim["created_at"],
            "updated_at": sim["updated_at"],
            "description": sim.get("description"),
            "agent_count": sim["agent_count"],
            "bspl_filename": sim["bspl_filename"],
            "run_count": len(runs),
            "runs": [
                {
                    "run_id": run["run_id"],
                    "status": run["status"],
                    "description": run.get("description"),
                    "created_at": run["created_at"],
                    "execution_time": run.get("execution_time"),
                    "message_count": run.get("message_count")
                }
                for run in sorted(runs, key=lambda r: r["created_at"], reverse=True)
            ]
        })
    
    return {
        "simulations": sorted(simulations_with_runs, key=lambda s: s["created_at"], reverse=True),
        "total_count": len(simulations_store),
        "total_runs": len(runs_store),
        "running_count": len(running_tasks)
    }

@app.get("/simulations/{simulation_id}", response_model=SimulationInfo)
async def get_simulation_info(simulation_id: str):
    """Gets information about a specific simulation."""
    sim = get_simulation(simulation_id)
    runs = get_runs_for_simulation(simulation_id)
    
    return SimulationInfo(
        simulation_id=simulation_id,
        created_at=sim["created_at"],
        updated_at=sim["updated_at"],
        description=sim.get("description"),
        agent_count=sim["agent_count"],
        bspl_filename=sim["bspl_filename"],
        run_count=len(runs)
    )

# ============================================================================
# RUN ENDPOINTS
# ============================================================================

@app.post("/simulations/{simulation_id}/runs", response_model=RunInfo)
async def create_run(simulation_id: str, request: CreateRunRequest):
    """
    Creates a new run for a given simulation.

    A run represents a specific execution of a simulation, with its own
    configuration. This allows for experimentation with different parameters.
    If no configuration is provided, a default one is generated.
    """
    simulation = get_simulation(simulation_id)
    run_id = create_run_id()
    now = datetime.now()

    # If config is provided, use it. Otherwise, create a default one.
    if request.config:
        config = request.config
        initial_status = SimulationStatus.CONFIGURED
    else:
        # Generate a default config based on the simulation files
        config = create_default_config(simulation["agent_files"])
        initial_status = SimulationStatus.CONFIGURED

    new_run = {
        "run_id": run_id,
        "simulation_id": simulation_id,
        "status": initial_status,
        "created_at": now,
        "updated_at": now,
        "description": request.description or f"Run at {now.isoformat()}",
        "config": config,
        "execution_time": None,
        "message_count": None,
        "error_message": None,
        "simulation_result": None,
    }
    runs_store[run_id] = new_run
    
    await notify_clients()
    return {**new_run, "has_config": bool(new_run.get("config"))}

@app.get("/runs/{run_id}", response_model=RunInfo)
async def get_run_info(run_id: str):
    """Get run details and current status."""
    run = get_run(run_id)
    
    return RunInfo(
        run_id=run_id,
        simulation_id=run["simulation_id"],
        status=run["status"],
        created_at=run["created_at"],
        updated_at=run["updated_at"],
        description=run.get("description"),
        has_config=run.get("config") is not None,
        execution_time=run.get("execution_time"),
        message_count=run.get("message_count"),
        error_message=run.get("error_message")
    )

@app.get("/runs/{run_id}/config")
async def get_run_config(run_id: str):
    """Get run configuration settings."""
    run = get_run(run_id)
    
    if run.get("config") is None:
        raise HTTPException(
            status_code=404,
            detail="Run has no configuration."
        )
    
    transformation_result = run.get("transformation_result")
    config_response = {"config": run["config"]}
    
    if transformation_result and transformation_result.task_to_agent_mapping:
        config_response["config"]["TASK_TO_AGENT"] = transformation_result.task_to_agent_mapping
    
    return config_response

@app.put("/runs/{run_id}/config")
async def update_run_config(run_id: str, request: UpdateRunConfigRequest):
    """
    Updates the configuration of a specific run.

    This endpoint allows for modifying the `AGENT_POOLS` and `TASK_SETTINGS`
    of a run. The new configuration is validated before being applied.
    """
    run = get_run(run_id)
    
    if run["status"] not in [SimulationStatus.CONFIGURED]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot update config for run in status {run['status']}"
        )
    
    try:
        current_config = run["config"].copy()
        
        if request.agent_pools is not None:
            current_config["AGENT_POOLS"] = request.agent_pools
        if request.task_settings is not None:
            # Validate task_settings before applying
            is_valid, errors = validate_task_settings(request.task_settings)
            if not is_valid:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid task_settings: {'; '.join(errors)}"
                )
            current_config["TASK_SETTINGS"] = request.task_settings
        
        sim = get_simulation(run["simulation_id"])
        transformation_result = transform_agents_from_content(
            agent_contents=sim["agent_files"],
            bspl_content=sim["bspl_content"],
            bspl_filename=sim["bspl_filename"],
            config_overrides=current_config
        )
        
        if not transformation_result.success:
            raise HTTPException(
                status_code=400,
                detail=f"Updated configuration is invalid: {'; '.join(transformation_result.errors)}"
            )
        
        await update_run_status(
            run_id,
            SimulationStatus.CONFIGURED,
            config=current_config,
            transformation_result=transformation_result
        )
        
        print(f"🔧 Updated config for run {run_id}")
        
        return {"message": "Configuration updated successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Config update failed: {str(e)}")

@app.post("/runs/{run_id}/duplicate", response_model=RunInfo)
async def duplicate_run(run_id: str, request: DuplicateRunRequest):
    """
    Creates a new run by duplicating the configuration of an existing run.

    This is a convenient way to create a new run with the same settings as a
    previous one, allowing for minor modifications before execution.
    """
    source_run = get_run(run_id)
    
    if source_run.get("config") is None:
        raise HTTPException(
            status_code=400,
            detail="Source run has no configuration to duplicate."
        )
    
    try:
        simulation_id = source_run["simulation_id"]
        
        # Copy the configuration from the source run
        config = source_run["config"].copy()
        
        new_run_id = create_run_id()
        now = datetime.now()
        
        # Create new run with same structure as regular runs
        runs_store[new_run_id] = {
            "run_id": new_run_id,
            "simulation_id": simulation_id,
            "status": SimulationStatus.CONFIGURED,
            "created_at": now,
            "updated_at": now,
            "description": request.description or f"Copy of {source_run.get('description', 'run')}", 
            "config": config,
            "execution_time": None,
            "message_count": None,
            "error_message": None,
            "simulation_result": None,
        }
        
        print(f"📋 Duplicated run {run_id} → {new_run_id}")
        await notify_clients()
        
        return RunInfo(
            run_id=new_run_id,
            simulation_id=simulation_id,
            status=SimulationStatus.CONFIGURED,
            created_at=now,
            updated_at=now,
            description=runs_store[new_run_id]["description"],
            has_config=True
        )
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Run duplication failed: {str(e)}")

@app.post("/runs/{run_id}/execute", response_model=RunInfo)
async def execute_run(run_id: str, request: ExecuteRunRequest, background_tasks: BackgroundTasks):
    """
    Executes a configured run.

    This endpoint triggers the simulation to run in the background. The run's
    status is updated to "RUNNING", and the simulation process is started.
    """
    run = get_run(run_id)
    
    if run["status"] != SimulationStatus.CONFIGURED:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot execute run in status {run['status']}. Must be CONFIGURED first."
        )
    
    if run_id in running_tasks:
        raise HTTPException(
            status_code=400,
            detail=f"Run {run_id} is already executing"
        )
    
    # Store max_rounds in the run
    await update_run_status(run_id, SimulationStatus.RUNNING, max_rounds=request.max_rounds)
    
    task = asyncio.create_task(run_simulation_background(run_id, request.max_rounds))
    running_tasks[run_id] = task
    
    print(f"🎯 Started execution of run {run_id} (max_rounds: {request.max_rounds})")
    
    return RunInfo(
        run_id=run_id,
        simulation_id=run["simulation_id"],
        status=SimulationStatus.RUNNING,
        created_at=run["created_at"],
        updated_at=run["updated_at"],
        description=run.get("description"),
        has_config=True
    )

@app.get("/runs/{run_id}/status")
async def get_run_status(run_id: str):
    """
    Retrieves the current status of a run, including virtual time information.

    For running simulations, this endpoint provides real-time progress, including
    the current virtual time and round. For completed runs, it extracts the
    final virtual time from the logs.
    """
    run = get_run(run_id)
    
    # Build response with basic run info
    response = {
        "run_id": run_id,
        "status": run["status"],
        "created_at": run["created_at"],
        "updated_at": run["updated_at"],
        "execution_time": run.get("execution_time"),
        "message_count": run.get("message_count"),
        "error_message": run.get("error_message"),
        "max_rounds": run.get("max_rounds", 200)
    }
    
    # Add virtual time status if running
    if run["status"] == SimulationStatus.RUNNING:
        virtual_time_status = get_virtual_time_status(run_id)
        if virtual_time_status:
            response["virtual_time_status"] = virtual_time_status.dict()
    elif run["status"] in [SimulationStatus.COMPLETE, SimulationStatus.FAILED, SimulationStatus.TIMED_OUT]:
        # For completed runs, extract final virtual time from exported logs
        try:
            from pathlib import Path
            import re
            
            working_dir = Path("simulation_runs") / f"run_{run_id}"
            timeservice_log = working_dir / "agent_logs" / run["simulation_id"] / run_id / "timeservice.log"
            
            if timeservice_log.exists():
                final_round = 0
                final_virtual_time = 0.0
                max_rounds = run.get("max_rounds", 200)
                
                with open(timeservice_log, 'r', encoding='utf-8') as f:
                    for line in f:
                        # Look for "Starting round X" or "Final state: round=X, virtual_time=Y"
                        round_match = re.search(r'Starting round (\d+)', line)
                        if round_match:
                            final_round = max(final_round, int(round_match.group(1)))
                        
                        final_state_match = re.search(r'Final state: round=(\d+), virtual_time=([0-9.]+)', line)
                        if final_state_match:
                            final_round = int(final_state_match.group(1))
                            final_virtual_time = float(final_state_match.group(2))
                        
                        # Look for "time=X.X" in TimeUpdate messages
                        time_match = re.search(r'time=([0-9.]+)', line)
                        if time_match:
                            virtual_time = float(time_match.group(1))
                            if virtual_time > final_virtual_time:
                                final_virtual_time = virtual_time
                
                # Calculate progress percentage
                progress_percentage = (final_round / max_rounds) * 100 if max_rounds > 0 else 0
                
                response["virtual_time_status"] = {
                    "current_round": final_round,
                    "max_rounds": max_rounds,
                    "current_virtual_time": final_virtual_time,
                    "progress_percentage": progress_percentage,
                    "agent_activity": {},
                    "recent_activity": []
                }
        except Exception as e:
            print(f"⚠️ Failed to extract virtual time from completed run {run_id}: {e}")
    
    return response

@app.get("/runs/{run_id}/logs")
async def get_run_logs(run_id: str):
    """
    Gets the logs for a specific run.

    For completed runs, this endpoint first attempts to retrieve logs from Redis.
    If that fails, it falls back to reading the log files from the simulation's
    working directory.
    """
    run = get_run(run_id)
    
    # For completed runs, try Redis first, then fall back to exported files
    if run["status"] in [SimulationStatus.COMPLETE, SimulationStatus.FAILED, SimulationStatus.TIMED_OUT]:
        simulation_id = run["simulation_id"]
        
        # First try to get logs from Redis
        try:
            import sys
            import os
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ra_transformer_lib_src'))
            from ra_transformer_lib.templates.simple_logging import query_redis_logs
            
            redis_logs = query_redis_logs(
                simulation_id=simulation_id,
                run_id=run_id,
                limit=LARGE_LOG_QUERY_LIMIT
            )
            
            if redis_logs:  # If Redis has logs, use them
                # Convert Redis logs to frontend format
                logs = []
                for log_entry in redis_logs:
                    message = log_entry.get('message', '')
                    enactment_id = None
                    
                    import re
                    id_match = re.search(r'id[:\s]*([a-zA-Z0-9_-]+)', message, re.IGNORECASE)
                    if id_match:
                        enactment_id = id_match.group(1)
                    
                    logs.append({
                        "timestamp": log_entry.get('timestamp', ''),
                        "agent": log_entry.get('logger', 'unknown'),
                        "message": message,
                        "type": "info",
                        "enactment_id": enactment_id
                    })
                
                logs.sort(key=lambda x: float(redis_logs[logs.index(x)].get('virtual_time', 0)))
                
                return {
                    "success": True,
                    "status": run["status"],
                    "error_message": run.get("error_message"),
                    "execution_time": run.get("execution_time"),
                    "logs": logs,
                    "agent_stats": {},
                    "raw_logs": []
                }
        except Exception as e:
            print(f"⚠️ Redis logs not available for run {run_id}: {e}")
        
        # Fall back to exported log files
        try:
            from pathlib import Path
            import json
            import re
            
            # Look for exported logs in the simulation directory
            working_dir = Path("simulation_runs") / f"run_{run_id}"
            agent_logs_dir = working_dir / "agent_logs" / simulation_id / run_id
            
            if not agent_logs_dir.exists():
                print(f"⚠️ Exported logs directory not found: {agent_logs_dir}")
                raise FileNotFoundError("Exported logs not found")
            
            logs = []
            
            # Read all log files in the directory
            for log_file in agent_logs_dir.glob("*.log"):
                agent_name = log_file.stem
                
                with open(log_file, 'r', encoding='utf-8') as f:
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        if not line:
                            continue
                        
                        # Parse log line format: "timestamp message"
                        parts = line.split(' ', 1)
                        if len(parts) >= 2:
                            timestamp = parts[0]
                            message = parts[1] if len(parts) > 1 else line
                        else:
                            timestamp = ""
                            message = line
                        
                        # Extract enactment_id from message (the id field)
                        enactment_id = None
                        
                        id_match = re.search(r'id[:\s]*([a-zA-Z0-9_-]+)', message, re.IGNORECASE)
                        if id_match:
                            enactment_id = id_match.group(1)
                        
                        logs.append({
                            "timestamp": timestamp,
                            "agent": agent_name,
                            "message": message,
                            "type": "info",
                            "enactment_id": enactment_id
                        })
            
            # Sort logs by timestamp
            logs.sort(key=lambda x: x.get("timestamp", ""))
            
            return {
                "success": True,
                "status": run["status"],
                "error_message": run.get("error_message"),
                "execution_time": run.get("execution_time"),
                "logs": logs,
                "agent_stats": {},
                "raw_logs": []
            }
            
        except Exception as e:
            print(f"⚠️ Failed to read exported logs for run {run_id}: {e}")
            # Continue to original fallback
    
    # Fallback: use simulation_result (old behavior)
    if "simulation_result" not in run or run["simulation_result"] is None:
        return {
            "success": False,
            "status": run["status"],
            "error_message": run.get("error_message", "No logs found."),
            "execution_time": run.get("execution_time"),
            "logs": [],
            "agent_stats": {},
            "raw_logs": [],
        }

    result = run["simulation_result"]
    return {
        "success": result.success,
        "status": run["status"],
        "error_message": run.get("error_message"),
        "execution_time": run.get("execution_time"),
        "exit_code": result.exit_code,
        "errors": result.errors,
        "logs": [
            {
                "timestamp": log.timestamp,
                "agent": log.agent_name,
                "message": log.message,
                "type": log.message_type,
                "enactment_id": getattr(log, 'enactment_id', None) or getattr(log, 'order_id', None)
            }
            for log in result.logs
        ],
        "agent_stats": result.agent_stats,
        "raw_logs": result.raw_logs
    }

@app.get("/runs/{run_id}/export/csv")
async def export_run_csv(run_id: str):
    """
    Exports the business protocol logs of a run to a CSV file.

    The exported CSV is formatted for use in process mining tools like Disco,
    with columns for case ID, activity name, timestamp, and resource.
    """
    try:
        csv_data = export_run_logs_to_csv(run_id)
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=run_{run_id}_business_protocol.csv"}
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# LEGACY/HELPER ENDPOINTS
# ============================================================================

@app.get("/status")
async def get_server_status():
    """Server status with simulation and run counts."""
    status_counts = {}
    for run in runs_store.values():
        status = run["status"]
        status_counts[status] = status_counts.get(status, 0) + 1
    
    return {
        "status": "running",
        "version": "3.0.0",
        "total_simulations": len(simulations_store),
        "total_runs": len(runs_store),
        "running_runs": len(running_tasks),
        "status_breakdown": status_counts,
        "data_model": "Simulations + Runs"
    }

@app.on_event("startup")
async def startup_event():
    """
    Performs startup tasks when the FastAPI application starts.

    This function starts the Redis server (if not already running) and a
    background task to broadcast virtual time updates to connected clients.
    """
    # Start Redis server for simulation logging
    await start_redis_server()
    
    # Start the virtual time broadcast task
    asyncio.create_task(broadcast_virtual_time_updates())
    print("🔄 Started virtual time broadcast task")

if __name__ == "__main__":
    print("Starting KikoSim Backend")
    print(f"Server will be available at: http://localhost:{BACKEND_PORT}")
    print()
    print("📋 API Endpoints:")
    print("POST /simulations                    - Create simulation")
    print("GET  /simulations                    - List simulations with runs")
    print("POST /simulations/{id}/runs          - Create new run")
    print("GET  /runs/{id}                      - Get run info")
    print("PUT  /runs/{id}/config              - Update run config")
    print("POST /runs/{id}/duplicate           - Duplicate run with same config")
    print("POST /runs/{id}/execute             - Execute run")
    print("GET  /runs/{id}/logs                - Get run results")
    print("GET  /ws                           - WebSocket for real-time updates")
    print()
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=BACKEND_PORT,
        log_level="info",
        access_log=True
    )

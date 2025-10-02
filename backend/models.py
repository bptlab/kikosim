"""
KikoSim Backend - Data Models

Pydantic models and enums for the KikoSim simulation backend.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, Optional, List
from pydantic import BaseModel, Field


class SimulationStatus(str, Enum):
    CREATED = "created"
    CONFIGURED = "configured" 
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class CreateSimulationRequest(BaseModel):
    agent_files: Dict[str, str] = Field(description="Agent Python files (filename -> content)")
    bspl_content: str = Field(description="BSPL protocol specification")
    bspl_filename: Optional[str] = Field(default="protocol.bspl", description="Protocol filename")
    description: Optional[str] = Field(default=None, description="Optional simulation description")


class CreateRunRequest(BaseModel):
    description: Optional[str] = None
    config: Optional[Dict] = None


class UpdateRunConfigRequest(BaseModel):
    agent_pools: Optional[Dict] = Field(default=None, description="Resource pool configuration")
    task_settings: Optional[Dict] = Field(default=None, description="Task duration settings")


class ExecuteRunRequest(BaseModel):
    max_rounds: Optional[int] = Field(default=200, description="Maximum simulation rounds")


class DuplicateRunRequest(BaseModel):
    description: Optional[str] = None


class VirtualTimeStatus(BaseModel):
    current_round: int
    max_rounds: int
    current_virtual_time: float
    progress_percentage: float
    agent_activity: Dict[str, int]  # agent_name -> message_count
    recent_activity: List[str]  # recent log messages


class SimulationInfo(BaseModel):
    simulation_id: str
    created_at: datetime
    updated_at: datetime
    description: Optional[str]
    agent_count: int
    bspl_filename: str
    run_count: int
    warnings: Optional[List[str]] = None


class RunInfo(BaseModel):
    run_id: str
    simulation_id: str
    status: SimulationStatus
    created_at: datetime
    updated_at: datetime
    description: Optional[str]
    has_config: bool
    execution_time: Optional[float] = None
    message_count: Optional[int] = None
    error_message: Optional[str] = None
    max_rounds: Optional[int] = None
    current_round: Optional[int] = None
    virtual_time_status: Optional[VirtualTimeStatus] = None
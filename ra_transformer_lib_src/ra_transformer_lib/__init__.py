"""A library for the Deferred Resource-Agent pattern transformation."""

# Memory-based API
from .memory_api import (
    transform_agents_from_content,
    validate_agent_content,
    validate_bspl_content,
    create_default_config
)

from .simulation_runner import (
    SimulationRunner,
    run_simulation_async,
    cleanup_simulation,
)

# Simulation execution
from .simulation_runner import (
    SimulationRunner,
    run_simulation_async
)

# Data models for memory-based operations
from .data_models import (
    TransformationInput,
    TransformationResult,
    AgentFile,
    GeneratedFile,
    SimulationConfig,
    SimulationResult,
    LogEntry
)

# Core transformation functions
from .transformation_core import transform_memory

__all__ = [
    # Memory-based API (before, there was a file based API)
    "transform_agents_from_content",
    "validate_agent_content",
    "validate_bspl_content",
    "create_default_config",
    "transform_memory",
    
    # Simulation execution
    "SimulationRunner",
    "run_simulation_async", # before, there was also a sync version of this
    "cleanup_simulation",
    
    # Data models
    "TransformationInput",
    "TransformationResult", 
    "AgentFile",
    "GeneratedFile",
    "SimulationConfig",
    "SimulationResult",
    "LogEntry",
]
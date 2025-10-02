#!/usr/bin/env python3
"""
This module defines the data structures (dataclasses) used throughout the
transformation and simulation process. These classes provide a structured way to
handle inputs, outputs, configurations, and results, ensuring type safety and
clarity.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from pathlib import Path


@dataclass
class AgentFile:
    """Represents a single agent file, containing its filename and content."""
    filename: str
    content: str
    
    @property
    def name_without_extension(self) -> str:
        """Returns the filename without the .py extension."""
        return self.filename.replace('.py', '')


@dataclass
class TransformationInput:
    """Encapsulates all necessary inputs for the transformation process."""
    agent_files: List[AgentFile]
    bspl_content: str
    bspl_filename: str = "protocol.bspl"
    config_overrides: Optional[Dict[str, Any]] = None
    business_base_port: int = 8000
    resource_base_port: int = 9000
    
    def get_agent_by_name(self, name: str) -> Optional[AgentFile]:
        """Retrieves an agent file by its name, with or without the .py extension."""
        for agent in self.agent_files:
            if agent.filename == name or agent.name_without_extension == name:
                return agent
        return None


@dataclass
class GeneratedFile:
    """Represents a file created during the transformation process."""
    filename: str
    content: str
    file_type: str  # Categorizes the file, e.g., 'agent', 'config', 'helper'


@dataclass
class TransformationResult:
    """Holds the results of the transformation process."""
    success: bool
    generated_files: List[GeneratedFile] = field(default_factory=list)
    config_content: str = ""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    agent_capabilities: Dict[str, List[str]] = field(default_factory=dict)
    func_to_principal: Dict[str, str] = field(default_factory=dict)
    task_to_agent_mapping: Dict[str, str] = field(default_factory=dict)
    
    def get_file_by_name(self, filename: str) -> Optional[GeneratedFile]:
        """Finds a generated file by its filename."""
        for file in self.generated_files:
            if file.filename == filename:
                return file
        return None
    
    def get_files_by_type(self, file_type: str) -> List[GeneratedFile]:
        """Retrieves all generated files of a specific type."""
        return [file for file in self.generated_files if file.file_type == file_type]
    
    def add_file(self, filename: str, content: str, file_type: str) -> None:
        """Adds a new generated file to the result."""
        self.generated_files.append(GeneratedFile(filename, content, file_type))
    
    def add_error(self, error: str) -> None:
        """Adds an error message to the result and marks it as unsuccessful."""
        self.errors.append(error)
        self.success = False
    
    def add_warning(self, warning: str) -> None:
        """Adds a warning message to the result."""
        self.warnings.append(warning)


@dataclass
class SimulationConfig:
    """Defines the configuration for running a simulation."""
    max_agents: int = 10
    log_level: str = "INFO"
    working_directory: Optional[Path] = None
    max_rounds: int = 200
    
    
@dataclass
class LogEntry:
    """Represents a single, structured log entry from a simulation run."""
    timestamp: str
    agent_name: str
    log_level: str
    message: str
    message_type: Optional[str] = None  # e.g., 'Order', 'Accept', 'GiveTask'
    order_id: Optional[str] = None
    task_id: Optional[str] = None
    raw_line: str = ""


@dataclass
class SimulationResult:
    """Holds the results of a simulation run."""
    success: bool
    logs: List[LogEntry] = field(default_factory=list)
    raw_logs: str = ""
    execution_time: float = 0.0
    agent_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    exit_code: int = 0
    working_dir: Optional[Path] = None
    timed_out: bool = False
    
    def add_error(self, error: str) -> None:
        """Adds an error to the simulation result and marks it as unsuccessful."""
        self.errors.append(error)
        self.success = False
#!/usr/bin/env python3
"""
This module provides the `SimulationRunner` class, which is responsible for
executing a transformed multi-agent simulation and capturing its results.

It handles the complexities of setting up a simulation environment, running the
agent processes, managing their lifecycle, and aggregating the logs. The runner
is designed to work with the output of the transformation process (`TransformationResult`)
and produces a detailed `SimulationResult`.
"""

import asyncio
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import signal
import os
import re
import shutil

from .data_models import (
    TransformationResult,
    SimulationConfig,
    SimulationResult,
    LogEntry,
    GeneratedFile,
)


class SimulationRunner:
    """Runs a transformed agent system and captures the execution results."""

    def __init__(self, config: SimulationConfig = None, simulation_id: str = None, run_id: str = None):
        """
        Initializes the SimulationRunner.

        Args:
            config: Configuration for the simulation run.
            simulation_id: The ID for the simulation, used for logging context.
            run_id: The ID for this specific run, used for logging context.
        """
        self.config = config or SimulationConfig()
        self.simulation_id = simulation_id
        self.run_id = run_id

    async def run_simulation(
        self,
        transformation_result: TransformationResult,
        working_dir: Optional[Path] = None,
    ) -> SimulationResult:
        """
        Runs a simulation based on the provided transformation result.

        This method orchestrates the simulation run. It first sets up the necessary
        files in a working directory (either a temporary or a persistent one), then
        executes the simulation using a subprocess, and finally collects and
        processes the results.

        Args:
            transformation_result: The result object from the transformation process.
            working_dir: An optional path to a directory where simulation files will be
                         written. If not provided, a temporary directory is used.

        Returns:
            A `SimulationResult` object containing the logs, execution time, and other
            data from the run.
        """
        if not transformation_result.success:
            raise ValueError("Transformation failed, cannot run simulation.")

        # Use provided working_dir or create a temporary directory
        if working_dir is not None:
            # Use the provided persistent directory
            working_dir = Path(working_dir)
            working_dir.mkdir(parents=True, exist_ok=True)
            print(f"Running simulation in: {working_dir}")

            # Write all transformed files to the directory
            for file in transformation_result.generated_files:
                file_path = working_dir / file.filename
                file_path.parent.mkdir(parents=True, exist_ok=True)  # Create subdirectories
                file_path.write_text(file.content)

            # Execute the simulation
            return await self._execute_simulation(working_dir)
        else:
            # Use temporary directory (fallback)
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_working_dir = Path(temp_dir)
                print(f"Running simulation in: {temp_working_dir}")

                # Write all transformed files to the directory
                for file in transformation_result.generated_files:
                    file_path = temp_working_dir / file.filename
                    file_path.parent.mkdir(parents=True, exist_ok=True)  # Create subdirectories
                    file_path.write_text(file.content)

                # Execute the simulation
                return await self._execute_simulation(temp_working_dir)

    async def _execute_simulation(
        self, working_dir: Path
    ) -> SimulationResult:
        """Executes the simulation subprocess and captures the results."""
        runner_script = working_dir / "run_complete_system.py"
        if not runner_script.exists():
            result = SimulationResult(success=False)
            result.add_error("No run_complete_system.py found in generated files")
            return result

        start_time = time.time()
        process = None

        try:
            import sys

            # Use virtual environment Python to ensure BSPL package availability
            # Try to find the project root and virtual environment
            current_path = Path(__file__).resolve()
            project_root = None
            
            # Look for project root containing venv and ra_transformer_lib_src
            for parent in current_path.parents:
                if (parent / "venv" / "bin" / "python3").exists() and (parent / "ra_transformer_lib_src").exists():
                    project_root = parent
                    break
            
            if project_root:
                venv_python = project_root / "venv" / "bin" / "python3"
                python_executable = str(venv_python)
                print(f"🐍 Using virtual environment Python: {python_executable}")
            else:
                python_executable = sys.executable
                print(f"⚠️ Virtual environment not found, using system Python: {python_executable}")
                print("   Consider running setup.sh to install BSPL properly")

            # Build command arguments
            cmd_args = [
                python_executable,
                "run_complete_system.py",  # Use relative path since cwd is set
            ]
            
            # Add max_rounds if specified
            if hasattr(self.config, 'max_rounds') and self.config.max_rounds != 200:
                cmd_args.extend(["--max-rounds", str(self.config.max_rounds)])
            
            # Add simulation and run IDs for Redis logging context
            if self.simulation_id:
                cmd_args.extend(["--simulation-id", self.simulation_id])
            if self.run_id:
                cmd_args.extend(["--run-id", self.run_id])
            
            process = await asyncio.create_subprocess_exec(
                *cmd_args,
                cwd=str(working_dir),  # Ensure string path
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=os.setsid,
            )

            stdout, stderr = await process.communicate()
            exit_code = process.returncode
            
            # Debug output for failures
            if exit_code != 0:
                print(f"🐛 Process failed with exit code {exit_code}")
                if stdout:
                    print(f"🐛 STDOUT: {stdout.decode('utf-8', errors='ignore')[:500]}")
                if stderr:
                    print(f"🐛 STDERR: {stderr.decode('utf-8', errors='ignore')[:500]}")

            

        except Exception as e:
            result = SimulationResult(success=False)
            result.add_error(f"Failed to execute simulation: {str(e)}")
            return result
        finally:
            if process and process.returncode is None:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    await process.wait()
                except (ProcessLookupError, OSError):
                    pass

        execution_time = time.time() - start_time
        raw_logs = self._get_raw_logs(working_dir)
        log_entries = self._parse_logs(raw_logs)

        # Check if simulation actually completed all rounds, not just exited cleanly
        # If exit code is 0, trust that TimeService completed successfully
        # Only do detailed round checking if exit code indicates failure
        if exit_code == 0:
            actual_success = True  # Trust clean exit from TimeService
        else:
            actual_success = False  # Failed exit code means simulation failed

        result = SimulationResult(
            success=actual_success,
            logs=log_entries,
            raw_logs=raw_logs,
            execution_time=execution_time,
            agent_stats=self._generate_agent_stats(log_entries),
            exit_code=exit_code,
        )

        if not actual_success:
            result.add_error(f"Simulation exited with code {exit_code}")

        return result

    def _simulation_completed_all_rounds(self, log_entries: List[LogEntry]) -> bool:
        """Checks if the simulation completed all rounds by inspecting TimeService logs."""
        max_rounds = getattr(self.config, 'max_rounds', 200) if self.config else 200
        
        # Look for TimeService final state logs or completion indicators
        for entry in log_entries:
            if entry.agent_name == "timeservice" or "timeservice" in entry.agent_name.lower():
                message = entry.message.lower()
                # Check for final state log that indicates completion
                if "final state" in message and "round=" in message:
                    # Extract the final round number
                    import re
                    round_match = re.search(r'round=(\d+)', message)
                    if round_match:
                        final_round = int(round_match.group(1))
                        # Consider completed if reached close to max_rounds (allow for off-by-one)
                        return final_round >= (max_rounds - 1)
                        
                # Also check for explicit completion messages
                if "completed after" in message and "rounds" in message:
                    return True
                    
        # If no clear completion indicator found, assume incomplete
        return False

    def _get_raw_logs(
        self,
        working_dir: Path
    ) -> str:
        """Aggregates and chronologically sorts decentralized agent logs."""
        # Aggregate decentralized logs
        agent_logs_dir = working_dir / "agent_logs"
        
        # Give some time for logs to be written (especially if simulation failed quickly)
        import time
        for i in range(5):  # Wait up to 1 second
            if agent_logs_dir.exists():
                break
            time.sleep(0.2)
        
        if not agent_logs_dir.exists():
            return f"Decentralized logging was enabled, but agent_logs directory not found at {agent_logs_dir}."

        entries = []
        for log_file in agent_logs_dir.glob("*.log"):
            agent_name = log_file.stem
            try:
                with open(log_file, "r", encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        timestamp = self._parse_log_timestamp(line)
                        entries.append((timestamp, agent_name, line))
            except Exception as e:
                print(f"Warning: Could not read {log_file}: {e}")

        entries.sort(key=lambda x: x[0])

        # Normalize timestamps
        start_time = min((e[0] for e in entries if e[0] > 0), default=0.0)

        aggregated_logs = []
        for timestamp, agent_name, line in entries:
            if timestamp > 0:
                relative_time = timestamp - start_time
                aggregated_logs.append(f"[{relative_time:8.3f}s] [{agent_name:20}] {line}")
            else:
                aggregated_logs.append(f"[  no-time] [{agent_name:20}] {line}")
        
        return "\n".join(aggregated_logs)

    def _parse_log_timestamp(self, line: str) -> float:
        """Extracts a timestamp from a single log line."""
        from datetime import datetime
        match = re.search(r"^(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})", line)
        if not match:
            return 0.0
        
        dt_str = match.group(1)
        try:
            dt_obj = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
            return dt_obj.timestamp()
        except ValueError:
            return 0.0

    def _parse_logs(self, raw_logs: str) -> List[LogEntry]:
        """Parses the raw, aggregated log string into a list of structured LogEntry objects."""
        log_entries = []
        ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        clean_logs = ansi_escape.sub("", raw_logs)

        # Pattern for aggregated decentralized logs: [  time] [agent_name] YYYY-MM-DD HH:MM:SS message
        # Updated to handle both "no-time" and numeric timestamps
        agent_log_pattern = r"\[\s*(?:[\d\.]+s|no-time)\s*\]\s+\[([^\]]+)\]\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(.+)"

        for line in clean_logs.split("\n"):
            line = line.strip()
            if not line:
                continue

            match = re.match(agent_log_pattern, line)
            if match:
                agent_name, timestamp, message = match.groups()
                
                order_id_match = re.search(r"orderID=([^\s,\]]+)", message)
                task_id_match = re.search(r"taskID=([^\s,\]]+)", message)

                log_entry = LogEntry(
                    timestamp=timestamp,
                    agent_name=agent_name,
                    log_level="INFO",
                    message=message,
                    order_id=order_id_match.group(1) if order_id_match else None,
                    task_id=task_id_match.group(1) if task_id_match else None,
                    raw_line=line,
                )
                log_entries.append(log_entry)

        return log_entries

    def _generate_agent_stats(self, log_entries: List[LogEntry]) -> Dict[str, Dict]:
        """Generates basic statistics for each agent based on the log entries."""
        stats = {}
        for entry in log_entries:
            agent = entry.agent_name
            if agent not in stats:
                stats[agent] = {
                    "message_count": 0,
                    "orders_processed": set(),
                    "first_activity": entry.timestamp,
                    "last_activity": entry.timestamp,
                }
            stats[agent]["message_count"] += 1
            stats[agent]["last_activity"] = entry.timestamp
            if entry.order_id:
                stats[agent]["orders_processed"].add(entry.order_id)

        for agent_stats in stats.values():
            agent_stats["unique_orders"] = len(agent_stats["orders_processed"])
            del agent_stats["orders_processed"]

        return stats


async def run_simulation_async(
    transformation_result: TransformationResult,
    config: SimulationConfig = None,
    working_dir: Optional[Path] = None,
    simulation_id: str = None,
    run_id: str = None,
) -> SimulationResult:
    """
    A convenience wrapper for running a simulation asynchronously.

    This function instantiates a `SimulationRunner` and calls its `run_simulation`
    method. It provides a simple, top-level entry point for executing simulations.
    """
    runner = SimulationRunner(config, simulation_id, run_id)
    return await runner.run_simulation(transformation_result, working_dir)


def cleanup_simulation(simulation_result: SimulationResult, force_cleanup: bool = False):
    """
    Safely cleans up the working directory of a simulation.

    This utility function is used to remove the simulation directory after a run.
    It has a safety mechanism to only remove temporary directories by default,
    preventing accidental deletion of persistent, debuggable simulation runs.

    Args:
        simulation_result: The result object from the simulation run.
        force_cleanup: If True, the directory will be removed regardless of whether
                       it is a temporary directory or not.
    """
    if not simulation_result.working_dir or not simulation_result.working_dir.exists():
        return
        
    # Only cleanup if force_cleanup=True or if it's a temporary directory
    is_temp_dir = str(simulation_result.working_dir).startswith('/tmp') or str(simulation_result.working_dir).startswith('/var/folders')
    
    if force_cleanup or is_temp_dir:
        shutil.rmtree(simulation_result.working_dir, ignore_errors=True)
        print(f"🧹 Cleaned up working directory: {simulation_result.working_dir}")
    else:
        print(f"📁 Keeping simulation directory for debugging: {simulation_result.working_dir}")

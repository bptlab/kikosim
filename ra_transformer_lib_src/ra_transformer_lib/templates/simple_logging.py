#!/usr/bin/env python3
"""
Simple logging utility for ResourceAgent pattern with virtual time support.
Provides consistent virtual time timestamps across all components.
"""

import logging
import sys
import hashlib
import os
import json
import redis
from pathlib import Path
from datetime import datetime, timedelta


def colorize_id(id_string: str) -> str:
    """
    Generate consistent ANSI color for an ID string using hash-based randomness.
    Same ID always gets same color for visual tracking across logs.
    
    NOTE: Colorization disabled to improve CSV export and process mining compatibility.
    """
    # Colorization disabled for cleaner CSV exports
    return id_string

# Global virtual time tracker with real-time offset
import time
_virtual_time = 0.0
_simulation_start_date = datetime(2020, 1, 1, 9, 0, 0)  # January 1, 2020, 9:00 AM
_simulation_start_real_time = None  # Will be set from environment or first virtual time update

def set_virtual_time(vtime: float):
    """Set the current virtual time for logging timestamps."""
    global _virtual_time, _simulation_start_real_time
    _virtual_time = vtime
    
    # Initialize real-time baseline - prefer command line arg, then environment variable for consistency
    if _simulation_start_real_time is None:
        import os
        import sys
        
        # Check if start time was passed as command line argument (for business agents)
        sim_start_time = None
        if hasattr(sys.modules.get('__main__', None), 'args') and hasattr(sys.modules['__main__'].args, 'start_time'):
            sim_start_time = sys.modules['__main__'].args.start_time
        
        # Fall back to environment variable (for resource agents)
        if sim_start_time is None:
            sim_start_env = os.getenv("KIKOSIM_START_TIME")
            if sim_start_env:
                try:
                    sim_start_time = float(sim_start_env)
                except ValueError:
                    pass
        
        # Use the provided start time or current time as fallback
        _simulation_start_real_time = sim_start_time if sim_start_time else time.time()

def get_virtual_time() -> float:
    """Get the current virtual time."""
    return _virtual_time

def get_virtual_datetime() -> datetime:
    """Convert virtual time to realistic datetime with real-time offset for sequencing."""
    global _simulation_start_real_time
    
    # Base virtual time (days elapsed)
    days_elapsed = _virtual_time
    base_datetime = _simulation_start_date + timedelta(days=days_elapsed)
    
    # Add real-time offset (seconds and milliseconds since simulation start)
    if _simulation_start_real_time is not None:
        real_elapsed = time.time() - _simulation_start_real_time
        real_seconds_in_minute = real_elapsed % 60  # Keep only seconds/milliseconds within minute
        base_datetime = base_datetime + timedelta(seconds=real_seconds_in_minute)
    
    return base_datetime

class VirtualTimeFormatter(logging.Formatter):
    """Custom formatter that uses virtual time as realistic date timestamps."""
    
    def formatTime(self, record, datefmt=None):
        """Override to use virtual time as realistic date with millisecond precision."""
        vdt = get_virtual_datetime()
        return vdt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # Include milliseconds (3 digits)

class CompactVirtualTimeFormatter(logging.Formatter):
    """Custom formatter with compact virtual time display."""
    
    def formatTime(self, record, datefmt=None):
        """Override to use compact virtual time format."""
        vtime = get_virtual_time()
        return f"vt{vtime:06.2f}"

class RedisHandler(logging.Handler):
    """Custom log handler that sends logs to Redis with hierarchical keys."""
    
    def __init__(self, redis_client=None, key_prefix="logs", simulation_id=None, run_id=None):
        super().__init__()
        if redis_client is None:
            self.redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        else:
            self.redis_client = redis_client
        self.key_prefix = key_prefix
        self.simulation_id = simulation_id
        self.run_id = run_id
    
    def emit(self, record):
        try:
            # Format the log record
            log_entry = {
                'timestamp': self.format(record),
                'level': record.levelname,
                'logger': record.name,
                'message': record.getMessage(),
                'virtual_time': get_virtual_time(),
                'real_time': datetime.now().isoformat()
            }
            
            # Build hierarchical key: logs:sim123:run456:AgentName
            key_parts = [self.key_prefix]
            if self.simulation_id:
                key_parts.append(str(self.simulation_id))
            if self.run_id:
                key_parts.append(str(self.run_id))
            key_parts.append(record.name)
            
            key = ":".join(key_parts)
            self.redis_client.lpush(key, json.dumps(log_entry))
            
            # Keep only recent entries (last 10000 per agent per run)
            self.redis_client.ltrim(key, 0, 9999)
            
        except Exception as e:
            # Redis error - report it clearly and fall back to stderr
            import sys
            error_msg = f"⚠️ REDIS ERROR in {record.name}: {e}\n"
            sys.stderr.write(error_msg)
            sys.stderr.flush()
            
            # Fallback: write the actual log message to stderr so it's not lost
            formatted_msg = f"{self.format(record)} {record.getMessage()}\n"
            sys.stderr.write(f"FALLBACK LOG: {formatted_msg}")
            sys.stderr.flush()

def query_redis_logs(logger_name: str = None, pattern: str = None, limit: int = 1000, 
                     simulation_id: str = None, run_id: str = None) -> list:
    """
    Query Redis logs for specific criteria.
    
    Args:
        logger_name: Name of the logger (e.g., "Market", "Retailer") - if None, gets all loggers
        pattern: Optional regex pattern to filter messages
        limit: Maximum number of entries to return per logger
        simulation_id: Simulation identifier to filter by
        run_id: Run identifier to filter by
    
    Returns:
        List of log entries (newest first)
    """
    try:
        redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        
        # Build key pattern for search
        key_pattern_parts = ["logs"]
        if simulation_id:
            key_pattern_parts.append(str(simulation_id))
        if run_id:
            key_pattern_parts.append(str(run_id))
        if logger_name:
            key_pattern_parts.append(logger_name)
        else:
            key_pattern_parts.append("*")  # Match any logger
        
        key_pattern = ":".join(key_pattern_parts)
        
        # Get all matching keys
        matching_keys = redis_client.keys(key_pattern)
        
        # Collect entries from all matching keys
        all_entries = []
        for key in matching_keys:
            log_entries = redis_client.lrange(key, 0, limit-1)
            
            for entry in log_entries:
                try:
                    log_data = json.loads(entry)
                    # Add key info for context
                    log_data['redis_key'] = key
                    
                    if pattern:
                        import re
                        if re.search(pattern, log_data.get('message', '')):
                            all_entries.append(log_data)
                    else:
                        all_entries.append(log_data)
                except json.JSONDecodeError:
                    continue
        
        # Sort by virtual time (newest first)
        all_entries.sort(key=lambda x: x.get('virtual_time', 0), reverse=True)
        
        return all_entries[:limit]
        
    except Exception as e:
        import sys
        error_msg = f"❌ REDIS QUERY FAILED: {e}\n"
        error_msg += f"   Cannot retrieve logs from Redis!\n"
        sys.stderr.write(error_msg)
        sys.stderr.flush()
        return []

def export_redis_logs_to_files(simulation_id: str = None, run_id: str = None, output_dir: str = "agent_logs"):
    """
    Export Redis logs to individual files in specified directory.
    
    Args:
        simulation_id: If specified, only export logs for this simulation
        run_id: If specified, only export logs for this run  
        output_dir: Directory to write log files (default: "agent_logs")
    """
    try:
        redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        
        # Create output directory structure
        base_dir = Path(output_dir)
        if simulation_id and run_id:
            log_dir = base_dir / simulation_id / run_id
        elif simulation_id:
            log_dir = base_dir / simulation_id
        else:
            log_dir = base_dir
            
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Build key pattern to match
        key_pattern_parts = ["logs"]
        if simulation_id:
            key_pattern_parts.append(str(simulation_id))
        if run_id:
            key_pattern_parts.append(str(run_id))
        key_pattern_parts.append("*")  # Match all loggers
        
        key_pattern = ":".join(key_pattern_parts)
        log_keys = redis_client.keys(key_pattern)
        
        exported_count = 0
        for key in log_keys:
            # Extract logger name from hierarchical key
            key_parts = key.split(":")
            logger_name = key_parts[-1]  # Last part is always the logger name
            
            # Get all log entries for this key (oldest first for file order)
            log_entries = redis_client.lrange(key, 0, -1)
            log_entries.reverse()  # Reverse to get chronological order
            
            # Write to file with context in filename
            if simulation_id and run_id:
                log_file = log_dir / f"{logger_name}.log"
            else:
                # Include context in filename if not using directory structure
                context_parts = key_parts[1:-1]  # Everything except "logs" and logger_name
                if context_parts:
                    context_str = "_".join(context_parts)
                    log_file = log_dir / f"{context_str}_{logger_name}.log"
                else:
                    log_file = log_dir / f"{logger_name}.log"
            
            with open(log_file, 'w') as f:
                for entry_json in log_entries:
                    try:
                        log_data = json.loads(entry_json)
                        # Write log entry with real timestamp, virtual timestamp, and message
                        real_time = log_data.get('real_time', 'unknown')
                        virtual_timestamp = log_data.get('timestamp', 'unknown')
                        message = log_data.get('message', '')
                        logger_name = log_data.get('logger', 'unknown')
                        
                        # Add resource type prefix based on logger name
                        if logger_name in ['market', 'retailer', 'supplier']:
                            resource_type = 'business'
                        else:
                            resource_type = 'resource'
                        
                        # Format: timestamp resource_type:agent_name: message (no redundant prefix)
                        formatted_message = f"{resource_type}:{logger_name}: {message}"
                        f.write(f"{virtual_timestamp} {formatted_message} [REAL: {real_time}] \n")
                    except json.JSONDecodeError:
                        continue
            
            exported_count += 1
            print(f"📄 Exported {len(log_entries)} entries to {log_file}")
        
        print(f"✅ Successfully exported logs from {exported_count} loggers to {log_dir}/")
        
    except Exception as e:
        import sys
        error_msg = f"❌ REDIS EXPORT FAILED: {e}\n"
        error_msg += f"   Cannot export logs from Redis to files!\n"
        error_msg += f"   Check if Redis is running and accessible.\n"
        sys.stderr.write(error_msg)
        sys.stderr.flush()

def setup_logger(name: str, use_virtual_time: bool = True, timestamp_style: str = "realistic", 
                 use_redis: bool = True, backup_to_file: bool = False, log_to_console: bool = False,
                 simulation_id: str = None, run_id: str = None) -> logging.Logger:
    """
    Set up a logger with Redis as primary destination and optional file backup.
    
    Args:
        name: Logger name (e.g., "supplier", "retailer", "ra_helpers")
        use_virtual_time: Whether to use virtual time in timestamps
        timestamp_style: "realistic" for full dates, "compact" for vt format
        use_redis: Whether to send logs to Redis (primary destination)
        backup_to_file: Whether to also write to file (backup)
        log_to_console: Whether to also write to console (disabled by default for performance)
        simulation_id: Simulation identifier for Redis key hierarchy
        run_id: Run identifier for Redis key hierarchy
    
    Returns:
        Configured logger with Redis primary destination
    """
    log = logging.getLogger(name)
    log.setLevel(logging.INFO)
    
    # Clear any existing handlers
    log.handlers.clear()
    
    # Choose formatter based on preferences
    if use_virtual_time:
        if timestamp_style == "realistic":
            formatter = VirtualTimeFormatter('%(asctime)s %(message)s')
        else:
            formatter = CompactVirtualTimeFormatter('%(asctime)s %(message)s')
    else:
        formatter = logging.Formatter(
            '%(asctime)s.%(msecs)03d %(message)s', 
            datefmt='%H:%M:%S'
        )
    
    # Redis handler (primary destination)
    if use_redis:
        try:
            redis_handler = RedisHandler(simulation_id=simulation_id, run_id=run_id)
            # Dedicated formatter for Redis that ONLY includes the timestamp
            if use_virtual_time:
                if timestamp_style == "realistic":
                    redis_formatter = VirtualTimeFormatter('%(asctime)s')
                else:
                    redis_formatter = CompactVirtualTimeFormatter('%(asctime)s')
            else:
                redis_formatter = logging.Formatter(
                    '%(asctime)s.%(msecs)03d', 
                    datefmt='%H:%M:%S'
                )
            redis_handler.setFormatter(redis_formatter)
            log.addHandler(redis_handler)
        except Exception as e:
            import sys
            error_msg = f"❌ CRITICAL: Redis handler setup failed for logger '{name}': {e}\n"
            error_msg += f"   This means logs for {name} will NOT be sent to Redis!\n"
            error_msg += f"   Forcing fallback to file logging...\n"
            sys.stderr.write(error_msg)
            sys.stderr.flush()
            backup_to_file = True  # Force file backup if Redis fails
    
    # File handler (backup)
    if backup_to_file:
        log_dir = Path("agent_logs")
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / f"{name}.log"
        file_handler = logging.FileHandler(log_file, mode='w')
        file_handler.setFormatter(formatter)
        log.addHandler(file_handler)
    
    # Console handler (optional, disabled by default for performance)
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        log.addHandler(console_handler)
    
    log.propagate = False  # Prevent duplicate logging
    
    return log 

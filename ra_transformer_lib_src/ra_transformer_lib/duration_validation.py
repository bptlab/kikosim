#!/usr/bin/env python3
"""
Duration validation utilities for task settings configuration.

This module provides validation functions that can be used by the backend
without importing the full ra_helpers module with its simulation dependencies.
"""

import re
from typing import Tuple, List, Dict, Union


def parse_duration(duration_str: str) -> Tuple[float, float]:
    """
    Parses a duration string into a mean and standard deviation in days.

    This function supports multiple formats:
    - Fixed duration: e.g., "1.5d", "2h", "30m"
    - Normal distribution: e.g., "1.5d±0.5d", "2h±30m"

    It converts all time units (days, hours, minutes, seconds) into a normalized
    representation in days. For fixed durations, the standard deviation is zero.

    Args:
        duration_str: The duration string to parse.

    Returns:
        A tuple containing the mean duration and standard deviation, both in days.

    Raises:
        ValueError: If the duration string format is invalid or violates the
                    normal distribution rule (μ - 2σ < 0).
    """
    duration_str = duration_str.strip()
    
    # Check for normal distribution format: "1.5d±0.5d"
    normal_match = re.match(r'^(\d+\.?\d*)\s*([dhms]?)\s*±\s*(\d+\.?\d*)\s*([dhms]?)$', duration_str)
    if normal_match:
        mean_value = float(normal_match.group(1))
        mean_unit = normal_match.group(2) or 'd'
        std_value = float(normal_match.group(3))
        std_unit = normal_match.group(4) or 'd'
        
        # Convert to days
        unit_multipliers = {'d': 1.0, 'h': 1/24, 'm': 1/(24*60), 's': 1/(24*60*60)}
        
        if mean_unit not in unit_multipliers:
            raise ValueError(f"Invalid time unit for mean: {mean_unit}")
        if std_unit not in unit_multipliers:
            raise ValueError(f"Invalid time unit for std dev: {std_unit}")
        
        mean_days = mean_value * unit_multipliers[mean_unit]
        std_days = std_value * unit_multipliers[std_unit]
        
        # Validate normal distribution rule: μ - 2σ ≥ 0
        if mean_days - 2 * std_days < 0:
            raise ValueError(f"Invalid normal distribution: mean - 2*std_dev = {mean_days:.3f} - 2*{std_days:.3f} = {mean_days - 2*std_days:.3f} < 0. Use smaller standard deviation.")
        
        return mean_days, std_days
    
    # Fixed duration format: "1.5d"
    fixed_match = re.match(r'^(\d+\.?\d*)\s*([dhms]?)$', duration_str)
    if fixed_match:
        base_value = float(fixed_match.group(1))
        unit = fixed_match.group(2) or 'd'
        
        # Convert to days
        unit_multipliers = {'d': 1.0, 'h': 1/24, 'm': 1/(24*60), 's': 1/(24*60*60)}
        if unit not in unit_multipliers:
            raise ValueError(f"Invalid time unit: {unit}")
        
        mean_days = base_value * unit_multipliers[unit]
        return mean_days, 0.0  # No variance for fixed duration
    
    raise ValueError(f"Invalid duration format: {duration_str}. Use formats like '1.5d', '2h±30m', or '1d±0.5d'")


def validate_task_settings(task_settings: Dict) -> Tuple[bool, List[str]]:
    """
    Validates the entire TASK_SETTINGS configuration dictionary.

    This function iterates through a `TASK_SETTINGS` dictionary and checks each
    entry for correctness. It ensures that the structure is valid (a tuple of
    2 or 3 elements) and that the duration specification (whether a simple number,
    a formatted string, or a mean/std_dev pair) is valid.

    Args:
        task_settings: The dictionary of task settings to validate.

    Returns:
        A tuple containing a boolean indicating validity and a list of error
        messages. An empty list means the configuration is valid.
    """
    errors = []
    
    if not isinstance(task_settings, dict):
        errors.append("TASK_SETTINGS must be a dictionary")
        return False, errors
    
    for task_name, task_setting in task_settings.items():
        if not isinstance(task_setting, (list, tuple)):
            errors.append(f"Task '{task_name}': setting must be a list or tuple, got {type(task_setting)}")
            continue
            
        if len(task_setting) < 2 or len(task_setting) > 3:
            errors.append(f"Task '{task_name}': setting must have 2 or 3 elements, got {len(task_setting)}")
            continue
            
        agent_type = task_setting[0]
        if not isinstance(agent_type, str):
            errors.append(f"Task '{task_name}': agent_type must be a string, got {type(agent_type)}")
            continue
            
        if len(task_setting) == 2:
            # Format: (agent_type, duration)
            duration_value = task_setting[1]
            if isinstance(duration_value, str):
                # New string format - validate duration string
                try:
                    parse_duration(duration_value)
                except ValueError as e:
                    errors.append(f"Task '{task_name}': invalid duration format '{duration_value}': {e}")
            elif isinstance(duration_value, (int, float)):
                # Old numeric format - ensure positive
                if duration_value <= 0:
                    errors.append(f"Task '{task_name}': duration must be positive, got {duration_value}")
            else:
                errors.append(f"Task '{task_name}': duration must be string or number, got {type(duration_value)}")
                
        elif len(task_setting) == 3:
            # Format: (agent_type, mean_days, std_days)
            mean_days, std_days = task_setting[1], task_setting[2]
            if not isinstance(mean_days, (int, float)) or not isinstance(std_days, (int, float)):
                errors.append(f"Task '{task_name}': mean and std_dev must be numbers")
                continue
                
            if mean_days <= 0:
                errors.append(f"Task '{task_name}': mean duration must be positive, got {mean_days}")
            if std_days < 0:
                errors.append(f"Task '{task_name}': std_dev must be non-negative, got {std_days}")
            if std_days > 0 and mean_days - 2 * std_days < 0:
                errors.append(f"Task '{task_name}': violates normal distribution rule (μ - 2σ ≥ 0): {mean_days:.3f} - 2*{std_days:.3f} = {mean_days - 2*std_days:.3f} < 0")
    
    return len(errors) == 0, errors
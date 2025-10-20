#!/usr/bin/env python3
"""
This module handles the creation of default configurations for the simulation.

It provides functions to generate configuration dictionaries from the results of
agent analysis. This is crucial for ensuring that a simulation can be run even
without explicit user-provided configuration, by creating sensible defaults for
resource agent pools and task settings.
"""

from typing import Dict, List, Tuple


def create_default_config_dict(
    agent_capabilities: Dict[str, List[str]],
    func_to_principal: Dict[str, str]
) -> Tuple[Dict[str, List[dict]], Dict[str, tuple], Dict[str, str]]:
    """
    Creates default configuration dictionaries based on agent analysis.

    This function generates a set of default configurations required to run a
    simulation. It creates a generic resource agent for each business agent
    (principal) and assigns all of that principal's deferred functions (tasks)
    to this generic resource agent with a default duration.

    Args:
        agent_capabilities: A dictionary mapping principal names to a list of their
                            deferred function names (capabilities).
        func_to_principal: A dictionary mapping each deferred function name to its
                           parent principal.

    Returns:
        A tuple containing three dictionaries:
        - `agent_pools_spec`: Defines a default resource agent pool for each principal.
        - `task_settings_spec`: Maps each task to a resource agent type and a default
                              duration.
        - `task_to_agent_mapping`: Maps each task to its principal.
    """
    # --- AGENT_POOLS spec --------------------------------------------------
    agent_pools_spec: Dict[str, List[dict]] = {}
    for principal in agent_capabilities:
        generic_name = f"{principal}RA"
        agent_pools_spec[principal] = [{generic_name: {"count": 1, "strategy": "round_robin"}}]

    # --- TASK_SETTINGS spec -------------------------------------------------
    task_settings_spec: Dict[str, tuple] = {}
    for func, principal in func_to_principal.items():
        generic_name = f"{principal}RA"
        task_settings_spec[func] = (generic_name, 1)
    
    # --- TASK_TO_AGENT mapping (same as func_to_principal) -----------------
    task_to_agent_mapping = dict(func_to_principal)
    
    return agent_pools_spec, task_settings_spec, task_to_agent_mapping



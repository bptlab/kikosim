#!/usr/bin/env python3
"""
This module is responsible for generating the various code and configuration files
that make up a runnable simulation.

It uses the Jinja2 templating engine to render Python scripts, configuration files,
and other necessary artifacts based on the results of the transformation process.
This approach separates the structure and boilerplate of the generated files (in
Jinja2 templates) from the dynamic data (e.g., agent names, port numbers,
resource pools) provided by the transformation core.

Key responsibilities include:
- Rendering `configuration.py`: Defines the BSPL systems, agent addresses, and
  resource agent pools.
- Rendering `run_complete_system.py`: Creates the main script that launches and
  manages all the agent processes for a simulation run.
- Generating `task_config.py`: Maps deferred business logic functions to their
  corresponding resource agent types and task durations.
"""

import textwrap
from typing import Dict, List, Sequence
import jinja2
from pathlib import Path

def _render_configuration(
    business_protocol_file: str, business_protocol_export: str, resource_pools: Dict[str, Dict[str, List[int]]], override_principals: List[str] = None, business_base_port: int = 8000, resource_base_port: int = 9000
) -> str:
    """
    Renders the `configuration.py` file content.

    This function dynamically constructs the BSPL system definitions, agent network
    addresses, and resource agent pools based on the transformation analysis. It uses
    a Jinja2 template to ensure the output is a well-formed Python configuration file.

    Args:
        business_protocol_file: The filename of the main business protocol.
        business_protocol_export: The name of the protocol variable to be exported.
        resource_pools: A dictionary defining the resource agent pools, their types,
                        and their allocated system IDs.
        override_principals: A list of principal names, typically from the BSPL roles,
                             to ensure all business participants are configured.
        business_base_port: The starting port for business agents.
        resource_base_port: The starting port for resource agents.

    Returns:
        The rendered content of the `configuration.py` file as a string.
    """

    business_protocol_var = "business_protocol"
    ra_protocol_filename = "resource_agent.bspl"

    # Use override principals if provided (from BSPL roles), otherwise use resource_pools keys
    # Business agents always need addresses, even without resource pools
    if override_principals:
        principals = override_principals  # Use BSPL roles directly
    else:
        principals = sorted(resource_pools.keys())

    agents_block_lines: List[str] = []
    systems_block_lines: List[str] = [
        "    # System 0: Business logic between agents",
        "    0: {",
        f"        \"protocol\": {business_protocol_var},",
        "        \"roles\": {",
    ]

    # Map business roles to principal names (simplistic – assumes same)
    for p in principals:
        systems_block_lines.append(f"            {p}: \"{p}\",")

    systems_block_lines.extend(["        },", "    },"])

    # Use provided base ports instead of searching for available ones
    # Port allocation is now handled by the web app
    base_port = business_base_port
    ra_port = resource_base_port

    # Business agents first
    for idx, p in enumerate(principals):
        agents_block_lines.append(f'    "{p}": [("127.0.0.1", {base_port + idx})],')

    # ResourceAgents per capability - grouped by principal
    resource_system_id = 1  # Start after main business system (0)
    for p in principals:
        if p not in resource_pools:
            continue  # Skip principals without resource pools
        
        # Create agent addresses for all resource agents under this principal
        for cap, pool in resource_pools[p].items():
            for idx in range(len(pool)):
                ra_name = f"RA_{cap}_{p}_{idx+1}"
                agents_block_lines.append(f'    "{ra_name}": [("127.0.0.1", {ra_port})],')
                ra_port += 1
        
        # Create one ResourceAgent system per principal (not per individual agent)
        ra_agent_names = []
        for cap, pool in resource_pools[p].items():
            for idx in range(len(pool)):
                ra_name = f"RA_{cap}_{p}_{idx+1}"
                ra_agent_names.append(ra_name)
        
        systems_block_lines.append(f"    # System {resource_system_id}: ResourceAgent system for {p}")
        systems_block_lines.append(f"    {resource_system_id}: {{")
        systems_block_lines.append(f"        \"protocol\": ra_spec,")
        systems_block_lines.append("        \"roles\": {")
        systems_block_lines.append(f"            Principal: \"{p}\",")
        systems_block_lines.append(f"            Agent: {ra_agent_names},")
        systems_block_lines.append("        },")
        systems_block_lines.append("    },")
        
        resource_system_id += 1

    # Generate agent pools for destination passing
    agent_pools_block_lines: List[str] = []
    for p in principals:
        if p not in resource_pools:
            continue
        agent_pools_block_lines.append(f'    "{p}": {{')
        for cap, pool in resource_pools[p].items():
            agent_names = [f"RA_{cap}_{p}_{idx+1}" for idx in range(len(pool))]
            agent_pools_block_lines.append(f'        "{cap}": {agent_names},')
        agent_pools_block_lines.append('    },')

    agents_block = textwrap.indent("\n".join(agents_block_lines), "    ")
    systems_block = textwrap.indent("\n".join(systems_block_lines), "    ")
    agent_pools_block = textwrap.indent("\n".join(agent_pools_block_lines), "    ")

    tmpl_dir = Path(__file__).resolve().parent / "jinja_templates"
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(tmpl_dir)),
        autoescape=False,
        keep_trailing_newline=True,
    )

    template = env.get_template("configuration.py.j2")

    # TimeService configuration
    timeservice_port = base_port + len(principals)  # Next port after business agents
    
    # Calculate TimeService system ID - after all resource agent systems
    num_principals_with_resources = len([p for p in principals if p in resource_pools])
    timeservice_system_id = 1 + num_principals_with_resources  # After business system (0) and resource systems
    
    # Build list of all agents for TimeService coordination
    all_agents = list(override_principals if override_principals else principals)
    for p in principals:
        if p in resource_pools:
            for cap, pool in resource_pools[p].items():
                for idx in range(len(pool)):
                    ra_name = f"RA_{cap}_{p}_{idx+1}"
                    all_agents.append(ra_name)
    
    result = template.render(
        business_protocol_var=business_protocol_var,
        business_protocol_file=business_protocol_file,
        business_protocol_export=business_protocol_export,
        ra_protocol_filename=ra_protocol_filename,
        agents_block=agents_block,
        systems_block=systems_block,
        agent_pools_block=agent_pools_block,
        business_roles=override_principals if override_principals else principals,
        timeservice_port=timeservice_port,
        timeservice_system_id=timeservice_system_id,
        timeservice_agent_list=repr(all_agents),
    )
    
    
    return result


def _render_runner(agent_names: Sequence[str], deferred_filenames: Sequence[str], resource_pools: Dict[str, Dict[str, List[int]]], max_rounds: int = 200) -> str:
    """
    Renders the `run_complete_system.py` script content.

    This function generates the main executable script for a simulation. The script
    is responsible for spawning all the necessary agent processes (business agents,
    resource agents, and the TimeService), managing their lifecycle, and ensuring
    they can communicate with each other.

    Args:
        agent_names: A sequence of business agent principal names.
        deferred_filenames: A sequence of the generated filenames for the transformed
                            business agents.
        resource_pools: A dictionary defining the resource agent pools.
        max_rounds: The maximum number of simulation rounds before timeout.

    Returns:
        The rendered content of the `run_complete_system.py` file as a string.
    """

    # 1) Build spawn-command snippets for TimeService integration -----------------

    # Resource agents data for TimeService template
    resource_agents = []
    max_pool_size = 1
    for principal, cap_map in resource_pools.items():
        for cap, pool in cap_map.items():
            max_pool_size = max(max_pool_size, len(pool))
            for idx in range(len(pool)):
                ra_label = f"RA_{cap}_{principal}_{idx+1}"
                ra_agent_name = f"RA_{cap}_{principal}_{idx+1}"
                resource_agents.append({
                    "label": ra_label,
                    "agent_name": ra_agent_name
                })

    # Build spawn lines without extra indentation (template will handle indentation)
    ra_spawn_lines = [
        f'    resource_procs.append(_spawn_ra("{ra["label"]}", "{ra["agent_name"]}", env))'
        for ra in resource_agents
    ]

    launch_lines = [
        f'    _spawn_business(business_procs, "{name}", "{filename}", simulation_id, run_id, simulation_start_time)'
        for name, filename in zip(agent_names, deferred_filenames)
    ]

    # 2) Load and render Jinja template -------------------------------------------

    tmpl_dir = Path(__file__).resolve().parent / "jinja_templates"
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(tmpl_dir)),
        autoescape=False,
        keep_trailing_newline=True,
    )

    template_name = "runner.py.j2"
    template = env.get_template(template_name)

    rendered = template.render(
        ra_spawns="\n".join(ra_spawn_lines),
        launch_spawns="\n".join(launch_lines),
        agent_names=list(agent_names),
        deferred_filenames=list(deferred_filenames),
        resource_agents=resource_agents,
        ra_count=len(resource_agents),
        default_duration=10,
        max_rounds=max_rounds,
    )

    return rendered

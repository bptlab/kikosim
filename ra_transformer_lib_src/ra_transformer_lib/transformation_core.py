#!/usr/bin/env python3
"""
This module contains the core logic for the Resource Agent (RA) transformation.
The primary functions here perform AST (Abstract Syntax Tree) manipulation to inject
the deferred execution pattern, analyze agent capabilities, generate configuration,
and assemble the final runnable simulation package.
"""
from __future__ import annotations
import ast
from typing import Dict, List, Tuple, Optional
import jinja2
from pathlib import Path
from .ast_modifier import _WrapReactions, _detect_agent_name
from .data_models import (
    TransformationInput, 
    TransformationResult, 
    AgentFile, 
)
from .code_generator import _render_runner

# -----------------------------------------------------------------------------
#  Core transformation functions
# -----------------------------------------------------------------------------

def transform_agent_content(
    agent_content: str, 
    agent_name: Optional[str] = None,
) -> Tuple[str, str, List[str]]:
    """
    Transform a single agent's content to use the Deferred Resource-Agent pattern.
    
    Args:
        agent_content: The original agent Python code as string
        agent_name: Override for agent name detection (optional)
    
    Returns:
        Tuple of (transformed_content, detected_agent_name, deferred_functions)
    """
    try:
        tree = ast.parse(agent_content)
    except SyntaxError as e:
        raise ValueError(f"Invalid Python syntax in agent content: {e}")

    # Detect agent name if not provided
    if agent_name is None:
        agent_name = _detect_agent_name(tree)

    # Wrap reactions with deferred pattern
    wrapper = _WrapReactions()
    tree = wrapper.visit(tree)  # type: ignore[arg-type]
    ast.fix_missing_locations(tree)

    # Find insertion points
    adapter_insert_at = 0
    main_block_at = len(tree.body)  # Default to end if no main block found
    
    for idx, n in enumerate(tree.body):
        # Look for: adapter = Adapter(...)
        if (isinstance(n, ast.Assign)
            and len(n.targets) == 1
            and isinstance(n.targets[0], ast.Name)
            and n.targets[0].id == "adapter"
            and isinstance(n.value, ast.Call)
            and isinstance(n.value.func, ast.Name)
            and n.value.func.id == "Adapter"):
            adapter_insert_at = idx + 1
        
        # Look for: if __name__ == '__main__':
        if (isinstance(n, ast.If)
            and isinstance(n.test, ast.Compare)
            and isinstance(n.test.left, ast.Name)
            and n.test.left.id == "__name__"
            and len(n.test.ops) == 1
            and isinstance(n.test.ops[0], ast.Eq)
            and len(n.test.comparators) == 1
            and isinstance(n.test.comparators[0], ast.Constant)
            and n.test.comparators[0].value == "__main__"):
            main_block_at = idx
            break
    
    # Prepare Jinja environment
    template_path = Path(__file__).resolve().parent / "jinja_templates"
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_path)),
        autoescape=False,
        keep_trailing_newline=True,
    )
    
    # Insert resource snippet after adapter definition
    resource_template = env.get_template("resource_snippet.py.j2")
    resource_snippet_content = resource_template.render(principal=agent_name)
    snippet_ast = ast.parse(resource_snippet_content)
    tree.body[adapter_insert_at:adapter_insert_at] = snippet_ast.body
    
    # Adjust main_block_at since we inserted code before it
    if main_block_at > adapter_insert_at:
        main_block_at += len(snippet_ast.body)

    # Insert TimeUpdate handler (also for initiator pattern)
    initiator_template = env.get_template("initiator_timeupdate_snippet.py.j2")
    initiator_snippet_content = initiator_template.render(principal=agent_name)
    initiator_handler_ast = ast.parse(initiator_snippet_content)
    tree.body[main_block_at:main_block_at] = initiator_handler_ast.body
    
    # Adjust main_block_at since we inserted more code
    main_block_at += len(initiator_handler_ast.body)

    # Insert complete-handler BEFORE the main block
    complete_template = env.get_template("complete_snippet.py.j2")
    complete_snippet_content = complete_template.render()
    complete_handler_ast = ast.parse(complete_snippet_content)
    tree.body[main_block_at:main_block_at] = complete_handler_ast.body

    # Convert back to source code
    new_src = ast.unparse(tree)

    # Preserve shebang if present
    if agent_content.startswith("#!"):
        shebang, rest = agent_content.split("\n", 1)
        new_src = shebang + "\n" + new_src

    return new_src, agent_name, wrapper.deferred


def analyze_agents(agent_files: List[AgentFile]) -> List[Dict]:
    """
    Analyze agent files to extract capabilities and metadata.
    
    Returns:
        Tuple of (agent_infos, all_deferred_functions)
    """
    agent_infos: List[Dict] = []

    for agent_file in agent_files:
        try:
            tree = ast.parse(agent_file.content)
        except SyntaxError as e:
            raise ValueError(f"Invalid Python syntax in {agent_file.filename}: {e}")
        
        wrapper = _WrapReactions()
        wrapper.visit(tree)

        agent_name = _detect_agent_name(tree)
        capabilities = {fn for fn in wrapper.deferred}

        agent_infos.append({
            "filename": agent_file.filename,
            "principal": agent_name,
            "capabilities": sorted(capabilities),
            "deferred_funcs": wrapper.deferred,
        })

    return agent_infos


def allocate_system_ids(
    agent_pools_spec: Dict[str, List[dict]]
) -> tuple[Dict[str, Dict[str, List[int]]], Dict[tuple[str, str], str]]:
    """
    Allocate system IDs for resource pools and extract strategies.
    
    Returns: (resource_pools, agent_strategies)
    """
    resource_pools: Dict[str, Dict[str, List[int]]] = {}
    agent_strategies: Dict[tuple[str, str], str] = {}
    system_counter = 1  # 0 is reserved for business-protocol system

    for principal, agent_list in agent_pools_spec.items():
        for agent_dict in agent_list:
            for agent_type, value in agent_dict.items():
                # new format (count + strategy)
                if isinstance(value, dict):
                    count = value.get("count", 1)
                    strategy = value.get("strategy", "round_robin")
                else:
                    raise ValueError(f"Invalid value type for {principal} {agent_type}: {type(value)}")
                
                pool = list(range(system_counter, system_counter + count))
                system_counter += count
                resource_pools.setdefault(principal, {})[agent_type] = pool
                agent_strategies[(principal, agent_type)] = strategy

    return resource_pools, agent_strategies


def generate_configuration_content(
    business_protocol_filename: str,
    business_protocol_export: str,
    resource_pools: Dict[str, Dict[str, List[int]]],
    agent_strategies: Dict[tuple[str, str], str],
    override_principals: List[str] = None,
    business_base_port: int = 8000,
    resource_base_port: int = 9000
) -> str:
    """Generate configuration.py content."""
    from .code_generator import _render_configuration
    
    return _render_configuration(
        business_protocol_file=business_protocol_filename,
        business_protocol_export=business_protocol_export,
        resource_pools=resource_pools,
        agent_strategies=agent_strategies,
        override_principals=override_principals,
        business_base_port=business_base_port,
        resource_base_port=resource_base_port
    )


def generate_runner_script(agent_names: List[str], deferred_filenames: List[str], resource_pools: Dict[str, Dict[str, List[int]]], max_rounds: int = 200) -> str:
    """Generate run_complete_system.py content."""
    return _render_runner(agent_names, deferred_filenames, resource_pools, max_rounds)


def generate_task_config_content(
    task_settings: Dict[str, tuple]
) -> str:
    """Generate task_config.py content."""
    template_path = Path(__file__).resolve().parent / "jinja_templates"
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_path)), 
        autoescape=False, 
        keep_trailing_newline=True
    )
    template = env.get_template("task_config.py.j2")
    
    return template.render(
        task_settings_repr=repr(task_settings),
    )


def generate_test_script_content() -> str:
    """Generate test_generated.py content."""
    body_lines = [
        "import compileall, pathlib, sys",
        "DIR = pathlib.Path(__file__).resolve().parent",
        "if not compileall.compile_dir(DIR, quiet=1):",
        "    sys.exit('❌ byte-compile failed')",
        "print('✅ byte-compile passed')",
    ]
    return "\n".join(body_lines)


def get_helper_files() -> Dict[str, str]:
    """Get helper file contents from templates directory."""
    template_dir = Path(__file__).parent / "templates"
    helper_files = {}
    
    # Include all essential helper files for TimeService integration
    essential_files = [
        "ra_helpers.py", 
        "resource_agent.py", 
        "simple_logging.py",
        "timeservice_agent.py"
    ]
    
    for helper_file in essential_files:
        helper_path = template_dir / helper_file
        if helper_path.exists():
            helper_files[helper_file] = helper_path.read_text(encoding="utf-8")
    
    return helper_files



def get_resource_agent_bspl() -> Optional[str]:
    """Get resource_agent.bspl content."""
    ra_bspl_path = Path(__file__).parent / "templates" / "resource_agent.bspl"
    if ra_bspl_path.exists():
        return ra_bspl_path.read_text(encoding="utf-8")
    return None

def get_timeservice_bspl() -> Optional[str]:
    """Get timeservice.bspl content."""
    ts_bspl_path = Path(__file__).parent / "templates" / "timeservice.bspl"
    if ts_bspl_path.exists():
        return ts_bspl_path.read_text(encoding="utf-8")
    return None


def get_requirements_content() -> str:
    """Get requirements.txt content for BSPL and TimeService dependencies."""
    bspl_deps = [
        "TatSu", "simplejson", "ttictoc", "fire", "aiocron",
        "pyyaml", "ijson", "aiorun", "colorama", "agentspeak",
        "croniter", "uvloop", "redis"
    ]
    return "\n".join(bspl_deps)


# -----------------------------------------------------------------------------
#  Main memory-based transformation function
# -----------------------------------------------------------------------------

def transform_memory(input_data: TransformationInput) -> TransformationResult:
    """
    Transform agents using memory-based operations (no file I/O).
    
    Args:
        input_data: TransformationInput containing agent files and configuration
    
    Returns:
        TransformationResult with generated files and metadata
    """
    result = TransformationResult(success=True)
    
    try:
        # 1. Analyze agents
        agent_infos = analyze_agents(input_data.agent_files)
        
        # Store analysis results
        result.agent_capabilities = {
            info["principal"]: info["capabilities"] 
            for info in agent_infos
        }
        result.func_to_principal = {
            func: info["principal"] 
            for info in agent_infos 
            for func in info["deferred_funcs"]
        }
        
        # 2. Use default config, with optional user overrides
        from .config_handler import create_default_config_dict
        default_agent_pools_spec, default_task_settings_spec, task_to_agent_mapping = create_default_config_dict(
            result.agent_capabilities, result.func_to_principal
        )
        
        # Store the task-to-agent mapping in the result for later use
        result.task_to_agent_mapping = task_to_agent_mapping
        
        if input_data.config_overrides is None:
            # Use defaults as-is
            agent_pools_spec = default_agent_pools_spec
            task_settings_spec = default_task_settings_spec
        else:
            # Apply user overrides, using defaults for missing keys
            agent_pools_spec = input_data.config_overrides.get("AGENT_POOLS", default_agent_pools_spec)
            task_settings_spec = input_data.config_overrides.get("TASK_SETTINGS", default_task_settings_spec)
        
        # 3. Allocate system IDs
        resource_pools, agent_strategies = allocate_system_ids(agent_pools_spec)
        
        # 4. Transform agents
        for info in agent_infos:
            agent_file = input_data.get_agent_by_name(info["filename"])
            if agent_file is None:
                result.add_error(f"Agent file not found: {info['filename']}")
                continue
                
            principal = info["principal"]
            
            # Transform the agent content
            transformed_content, detected_name, deferred_funcs = transform_agent_content(
                agent_file.content,
                agent_name=principal
            )
            
            # Generate output filename
            clean_name = agent_file.filename.replace("minimal_", "").replace(".py", "_deferred.py")
            result.add_file(clean_name, transformed_content, "agent")
        
        # 5. Generate supporting files
        agent_names = [info["principal"] for info in agent_infos]
        deferred_filenames = [
            f.filename for f in result.get_files_by_type("agent")
        ]
        
        # Configuration
        # Extract protocol name and roles from BSPL content
        import re
        bspl_content = input_data.bspl_content
        protocol_match = re.search(r'(\w+)\s*\{', bspl_content)
        if protocol_match:
            business_protocol_export = protocol_match.group(1)
        else:
            # Fallback to filename-based generation
            business_protocol_export = input_data.bspl_filename.replace(".bspl", "").replace("_", " ").title().replace(" ", "")
        
        # Extract roles from BSPL content
        roles_match = re.search(r'roles\s+([^\n\r]+)', bspl_content)
        if roles_match:
            # Parse roles like "Retailer, Supplier" 
            bspl_roles = [role.strip() for role in roles_match.group(1).split(',')]
        else:
            bspl_roles = []
        
        # Use BSPL roles if available, otherwise fall back to resource_pools keys
        if bspl_roles:
            principals_for_config = bspl_roles
        else:
            principals_for_config = sorted(resource_pools.keys())
        
        config_content = generate_configuration_content(
            input_data.bspl_filename,
            business_protocol_export,
            resource_pools,
            agent_strategies,
            override_principals=principals_for_config,
            business_base_port=input_data.business_base_port,
            resource_base_port=input_data.resource_base_port
        )
        result.add_file("configuration.py", config_content, "config")
        result.config_content = config_content
        
        # Runner script - extract max_rounds from config if available
        max_rounds = 200  # default
        if input_data.config_overrides and "max_rounds" in input_data.config_overrides:
            max_rounds = input_data.config_overrides["max_rounds"]
        runner_content = generate_runner_script(agent_names, deferred_filenames, resource_pools, max_rounds)
        result.add_file("run_complete_system.py", runner_content, "runner")
        
        task_config_content = generate_task_config_content(task_settings_spec)
        result.add_file("task_config.py", task_config_content, "config")
        
        # Test script
        test_content = generate_test_script_content()
        result.add_file("test_generated.py", test_content, "test")
        
        # Protocol files
        result.add_file(input_data.bspl_filename, input_data.bspl_content, "protocol")
        
        resource_bspl = get_resource_agent_bspl()
        if resource_bspl:
            result.add_file("resource_agent.bspl", resource_bspl, "protocol")
        
        # TimeService protocol
        timeservice_bspl = get_timeservice_bspl()
        if timeservice_bspl:
            result.add_file("timeservice.bspl", timeservice_bspl, "protocol")
        
        # Helper files
        helper_files = get_helper_files()
        for filename, content in helper_files.items():
            result.add_file(filename, content, "helper")

        # Requirements
        requirements_content = get_requirements_content()
        result.add_file("requirements.txt", requirements_content, "helper")
        
    except Exception as e:
        result.add_error(f"Transformation failed: {str(e)}")
    
    return result

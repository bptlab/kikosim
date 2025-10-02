#!/usr/bin/env python3
"""
This module provides a memory-based API for the Resource Agent transformation library.
It allows programmatic transformation of agent and BSPL content provided as strings.
"""

from __future__ import annotations
from typing import Dict, List, Optional

from .data_models import (
    TransformationInput,
    TransformationResult,
    AgentFile,
)
from .transformation_core import transform_memory


def transform_agents_from_content(
    agent_contents: Dict[str, str],
    bspl_content: str,
    bspl_filename: str = "protocol.bspl",
    config_overrides: Optional[Dict] = None,
    business_base_port: int = 8000,
    resource_base_port: int = 9000
) -> TransformationResult:
    """
    Transforms a set of agent files and a BSPL protocol, provided as string content,
    into a complete, runnable simulation environment.

    This function serves as the primary entry point for the library when used in a
    memory-based context (e.g., a web server). It orchestrates the transformation
    process, including parsing, code generation, and configuration, and returns a
    structured result containing all generated files and metadata.

    Args:
        agent_contents: A dictionary mapping filenames to the string content of
                        Python agent code.
        bspl_content: A string containing the BSPL protocol definition.
        bspl_filename: The filename to be used for the BSPL protocol. Defaults to
                       "protocol.bspl".
        config_overrides: An optional dictionary to override default configuration
                          settings for the transformation.
        business_base_port: The starting port number for business agent services.
                            Defaults to 8000.
        resource_base_port: The starting port number for resource agent services.
                            Defaults to 9000.

    Returns:
        A `TransformationResult` object containing the outcome of the transformation,
        including the generated files, success status, and any errors.
    
    Example:
        >>> agents = {
        ...     "retailer.py": "# retailer agent code...",
        ...     "supplier.py": "# supplier agent code..."
        ... }
        >>> bspl = "Protocol BasicSupplyChain { ... }"
        >>> result = transform_agents_from_content(agents, bspl)
        >>> if result.success:
        ...     print(f"Generated {len(result.generated_files)} files")
        ... else:
        ...     print(f"Errors: {result.errors}")
    """
    # Convert string contents to AgentFile objects
    agent_files = [
        AgentFile(filename=filename, content=content)
        for filename, content in agent_contents.items()
    ]
    
    # Create transformation input
    transformation_input = TransformationInput(
        agent_files=agent_files,
        bspl_content=bspl_content,
        bspl_filename=bspl_filename,
        config_overrides=config_overrides,
        business_base_port=business_base_port,
        resource_base_port=resource_base_port
    )
    
    # Perform transformation
    return transform_memory(transformation_input)


def validate_agent_content(content: str) -> tuple[bool, List[str], List[str]]:
    """
    Validate Python agent file content.
    
    Args:
        content: Python agent code as string
    
    Returns:
        Tuple of (is_valid, error_messages, warning_messages)
    """
    errors = []
    warnings = []
    
    # Check if content is not empty
    if not content.strip():
        errors.append("Agent content is empty")
        return False, errors, warnings
    
    # Check Python syntax
    try:
        import ast
        ast.parse(content)
    except SyntaxError as e:
        errors.append(f"Python syntax error: {e}")
        return False, errors, warnings
    
    # Check for required imports/patterns
    required_patterns = ["Adapter", "adapter"]
    missing_patterns = []
    
    for pattern in required_patterns:
        if pattern not in content:
            missing_patterns.append(pattern)
    
    if missing_patterns:
        errors.append(f"Missing required patterns: {', '.join(missing_patterns)}")
    
    # Check for reaction decorators (this is what is transformed)
    if "@adapter.reaction" not in content:
        warnings.append("No @adapter.reaction decorators found - agent may not be transformable")
    
    return len(errors) == 0, errors, warnings


def validate_bspl_content(content: str) -> tuple[bool, List[str]]:
    """
    Validate BSPL protocol content.
    
    Args:
        content: BSPL protocol content as string
    
    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors = []
    
    # Check if content is not empty
    if not content.strip():
        errors.append("BSPL content is empty")
        return False, errors
    
    # Check for basic BSPL structure
    if "{" not in content or "}" not in content:
        errors.append("BSPL content appears to be missing protocol structure (braces)")
    
    # Check for essential BSPL keywords 
    essential_keywords = ["roles"]
    missing_keywords = []
    
    for keyword in essential_keywords:
        if keyword not in content.lower():
            missing_keywords.append(keyword)
    
    if missing_keywords:
        errors.append(f"Missing required BSPL keywords: {', '.join(missing_keywords)}")
    
    # Check if it looks like a valid protocol declaration (ProtocolName {)
    import re
    protocol_pattern = r'\w+\s*\{'
    if not re.search(protocol_pattern, content):
        errors.append("BSPL content does not appear to have a valid protocol declaration (expected: ProtocolName {)")
    
    return len(errors) == 0, errors


def create_default_config(
    agent_contents: Dict[str, str]
) -> Dict:
    """
    Create a default configuration based on agent analysis.
    
    Args:
        agent_contents: Dict mapping filenames to Python agent code content
    
    Returns:
        Default configuration dictionary
    """
    from .transformation_core import analyze_agents
    from .config_handler import create_default_config_dict
    
    # Convert to AgentFile objects
    agent_files = [
        AgentFile(filename=filename, content=content)
        for filename, content in agent_contents.items()
    ]
    
    # Analyze agents
    agent_infos = analyze_agents(agent_files)
    
    # Extract capabilities and mappings
    agent_capabilities = {
        info["principal"]: info["capabilities"] 
        for info in agent_infos
    }
    func_to_principal = {
        func: info["principal"] 
        for info in agent_infos 
        for func in info["deferred_funcs"]
    }
    
    # Create default config
    agent_pools_spec, task_settings_spec, task_to_agent_mapping = create_default_config_dict(
        agent_capabilities, func_to_principal
    )
    
    return {
        "AGENT_POOLS": agent_pools_spec,
        "TASK_SETTINGS": task_settings_spec,
        "TASK_TO_AGENT": task_to_agent_mapping
    }
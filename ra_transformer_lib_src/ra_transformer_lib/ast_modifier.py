#!/usr/bin/env python3
"""
This module provides the core Abstract Syntax Tree (AST) transformation capabilities
for the Resource Agent pattern. It uses Python's `ast` module to parse agent code
into a tree structure, which is then manipulated to inject the necessary logic for
the deferred resource agent pattern

The primary class, `_WrapReactions`, is a NodeTransformer that:
1.  Wraps `@adapter.reaction` decorators to delegate their execution to the
    resource management infrastructure (`deferred_reaction`).
2.  Collects the names of the functions it transforms, which is crucial for
    generating the task configuration.
3.  Injects code to handle simulation-specific context (like simulation and run IDs)
    for logging purposes.

This approach allows the transformation to be applied transparently to the original
agent code, preserving the business logic while adding the required resource
coordination behavior.
"""

import ast
from pathlib import Path
from typing import List


# -----------------------------------------------------------------------------
#  Utility helpers
# -----------------------------------------------------------------------------

def _write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8")


def _read(path: Path) -> str:
    """Read file content."""
    return path.read_text(encoding="utf-8")


# -----------------------------------------------------------------------------
#  Generic AST transformer (wrap reaction-handlers)
# -----------------------------------------------------------------------------

class _WrapReactions(ast.NodeTransformer):
    """
    An AST transformer that injects the deferred execution pattern into an agent's code.

    This transformer traverses the AST of an agent file and performs two key modifications:

    1.  **Wraps Reaction Handlers**: It identifies all functions decorated with
        `@adapter.reaction(X)` and wraps them with a `deferred_reaction` call.
        For example, `@adapter.reaction(Order)` becomes
        `@deferred_reaction(adapter.reaction(Order), "handle_order")`.
        This delegates the execution of the business logic to the resource
        management system.

    2.  **Injects Logging Context**: It modifies calls to `setup_logger` to include
        `simulation_id` and `run_id` arguments. This ensures that logs from
        different simulation runs are correctly isolated and tagged.

    The names of all functions that are wrapped (deferred) are collected in the
    `self.deferred` list, which is later used to generate the task configuration.
    """

    def __init__(self) -> None:
        self.deferred: List[str] = []
        self.added_argparse = False
        self.needs_simple_logging = False
        super().__init__()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:  # type: ignore[override]
        return self._transform_function(node)
    
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:  # type: ignore[override]
        return self._transform_function(node)
    
    def _transform_function(self, node):
        """Transform function decorators for both sync and async functions."""
        new_decs: List[ast.expr] = []
        transformed = False
        for dec in node.decorator_list:
            if (
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Attribute)
                and isinstance(dec.func.value, ast.Name)
                and dec.func.value.id == "adapter"
                and dec.func.attr == "reaction"
            ):
                new_decs.append(
                    ast.Call(
                        func=ast.Name(id="deferred_reaction", ctx=ast.Load()),
                        args=[dec, ast.Constant(node.name)],
                        keywords=[],
                    )
                )
                transformed = True
            else:
                new_decs.append(dec)
        if transformed:
            self.deferred.append(node.name)
            node.decorator_list = new_decs
        return node

    def visit_Assign(self, node: ast.Assign) -> ast.AST:
        """Transform logging assignments to use setup_logger with environment variables."""
        # Check if this is a setup_logger call assignment
        if (isinstance(node.value, ast.Call) and
            isinstance(node.value.func, ast.Name) and
            node.value.func.id == "setup_logger" and
            len(node.value.args) == 1):
            
            # Mark that we need argparse
            if not self.added_argparse:
                self.added_argparse = True
            
            # Change variable name to 'log' for TimeUpdate handler compatibility
            if (len(node.targets) == 1 and
                isinstance(node.targets[0], ast.Name)):
                node.targets[0].id = "log"
            
            # Transform the call to include CLI arguments
            node.value.keywords.extend([
                ast.keyword(
                    arg='simulation_id',
                    value=ast.Attribute(
                        value=ast.Name(id='args', ctx=ast.Load()),
                        attr='simulation_id',
                        ctx=ast.Load()
                    )
                ),
                ast.keyword(
                    arg='run_id',
                    value=ast.Attribute(
                        value=ast.Name(id='args', ctx=ast.Load()),
                        attr='run_id',
                        ctx=ast.Load()
                    )
                )
            ])
        
        # Check if this is a logging.getLogger call assignment
        elif (isinstance(node.value, ast.Call) and
              isinstance(node.value.func, ast.Attribute) and
              isinstance(node.value.func.value, ast.Name) and
              node.value.func.value.id == "logging" and
              node.value.func.attr == "getLogger" and
              len(node.value.args) == 1):
            
            # Mark that we need argparse and simple_logging import
            if not self.added_argparse:
                self.added_argparse = True
            self.needs_simple_logging = True
            
            # Transform from: logger = logging.getLogger("agent_name")
            # To: log = setup_logger("agent_name", simulation_id=args.simulation_id, run_id=args.run_id)
            
            # Change function call from logging.getLogger to setup_logger
            node.value.func = ast.Name(id='setup_logger', ctx=ast.Load())
            
            # Change variable name to 'log'
            if (len(node.targets) == 1 and
                isinstance(node.targets[0], ast.Name)):
                node.targets[0].id = "log"
            
            # Add simulation_id and run_id keyword arguments
            node.value.keywords.extend([
                ast.keyword(
                    arg='simulation_id',
                    value=ast.Attribute(
                        value=ast.Name(id='args', ctx=ast.Load()),
                        attr='simulation_id',
                        ctx=ast.Load()
                    )
                ),
                ast.keyword(
                    arg='run_id',
                    value=ast.Attribute(
                        value=ast.Name(id='args', ctx=ast.Load()),
                        attr='run_id',
                        ctx=ast.Load()
                    )
                )
            ])
        
        return node
    
    def visit_Name(self, node: ast.Name) -> ast.AST:
        """Rename any variable called 'logger' to 'log' for consistency."""
        if node.id == "logger":
            node.id = "log"
        return node
    
    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        """Handle attribute access on logger variables."""
        # First visit children
        node = self.generic_visit(node)
        
        # Then handle logger variable references
        if (isinstance(node.value, ast.Name) and 
            node.value.id == "logger"):
            node.value.id = "log"
        
        return node

    def visit_Module(self, node: ast.Module) -> ast.Module:
        """Transform the entire module, handling logging setup."""
        # Transform the tree normally first
        node = self.generic_visit(node)
        
        # Add simple_logging import if needed
        if self.needs_simple_logging:
            # Check if simple_logging is already imported
            has_simple_logging_import = False
            for n in node.body:
                if isinstance(n, ast.ImportFrom) and n.module == 'simple_logging':
                    has_simple_logging_import = True
                    break
            
            if not has_simple_logging_import:
                # Add from simple_logging import setup_logger at the beginning
                import_node = ast.ImportFrom(
                    module='simple_logging',
                    names=[ast.alias(name='setup_logger', asname=None)],
                    level=0
                )
                node.body.insert(0, import_node)
        
        # Add argparse code if needed
        if self.added_argparse:
            # Check if argparse is already imported
            has_argparse_import = False
            for n in node.body:
                if isinstance(n, ast.Import):
                    for alias in n.names:
                        if alias.name == 'argparse':
                            has_argparse_import = True
                            break
                elif isinstance(n, ast.ImportFrom) and n.module == 'argparse':
                    has_argparse_import = True
                    break
            
            if not has_argparse_import:
                # Add import argparse at the beginning
                import_node = ast.Import(names=[ast.alias(name='argparse', asname=None)])
                node.body.insert(0, import_node)
            
            # Add argument parsing code after imports
            argparse_code = '''
parser = argparse.ArgumentParser()
parser.add_argument('--simulation-id', required=True, help='Simulation ID for logging')
parser.add_argument('--run-id', required=True, help='Run ID for logging')
parser.add_argument('--start-time', type=float, help='Simulation start time for consistent timing')
args = parser.parse_args()
'''
            argparse_ast = ast.parse(argparse_code)
            
            # Find where to insert (after imports, before other code)
            insert_pos = 0
            for i, n in enumerate(node.body):
                if not (isinstance(n, ast.Import) or isinstance(n, ast.ImportFrom)):
                    insert_pos = i
                    break
            else:
                insert_pos = len(node.body)
            
            # Insert argparse code
            node.body[insert_pos:insert_pos] = argparse_ast.body
        
        return node


def _detect_agent_name(tree: ast.Module) -> str:
    """
    Analyzes the AST to find the agent's name from its `Adapter` instantiation.

    This function walks the AST to find the line where the BSPL adapter is created,
    supporting both patterns:
    - `adapter = Adapter("Retailer", ...)` (string literal)
    - `adapter = Adapter(Customer, ...)` (class reference)
    It then extracts the agent's declared name (principal).

    Args:
        tree: The AST of the agent's code.

    Returns:
        The detected agent name as a string.

    Raises:
        ValueError: If the agent name cannot be detected from an `Adapter` call.
    """
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Adapter"
            and node.args
        ):
            # Handle string literal: Adapter("AgentName", ...)
            if (isinstance(node.args[0], ast.Constant) and
                isinstance(node.args[0].value, str)):
                return str(node.args[0].value)
            
            # Handle class reference: Adapter(ClassName, ...)
            elif isinstance(node.args[0], ast.Name):
                return str(node.args[0].id)
    
    raise ValueError("Unable to detect agent name via Adapter(...) call")

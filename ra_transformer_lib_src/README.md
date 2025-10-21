# RA Transformer Library

A library for transforming BSPL (Blindingly Simple Protocol Language) agents to use the **Deferred Resource-Agent pattern**.

This library provides tools to automatically refactor "minimal" agent files, injecting the necessary boilerplate to manage resources and tasks via dedicated Resource Agents. It supports both **file-based operations** (for CLI/research use, and this was the first prototype) and **memory-based operations** (for web applications).

## 🎯 What It Does

The library transforms BSPL agents into a **5-step Deferred Resource-Agent pattern**:

1. **DEFER BUSINESS LOGIC** → The original reaction handler is wrapped and converted into a coroutine.
2. **STORE WITH `taskID`** → The coroutine is placed in a `pending` dictionary keyed by a newly generated `taskID`.
3. **SEND `GiveTask`** → A `GiveTask` message is sent to an appropriate `ResourceAgent`, carrying the `taskID`, expected duration and order reference.
4. **RECEIVE `CompleteTask`** → After the resource work is done, the `ResourceAgent` sends back a `CompleteTask` message containing the same `taskID`.
5. **RESUME & EXECUTE** → The business agent pops the coroutine from `pending` and awaits it, executing the original business logic (which typically sends the business-level reply message).

## 🚀 Quick Start

### Installation

```bash
# Navigate to the project root
cd /path/to/your/master-thesis

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install the library in editable mode
pip install -e ./ra_transformer_lib_src

# Install additional dependencies
pip install jinja2
```

### Basic Usage (Memory-based API)

```python
from ra_transformer_lib import transform_agents_from_content

# Agent code as strings
retailer_code = '''
from bspl.adapter import Adapter
adapter = Adapter("Retailer")

@adapter.reaction("Accept")
async def handle_accept(msg):
    print(f"Received: {msg}")
    return msg
'''

supplier_code = '''
from bspl.adapter import Adapter
adapter = Adapter("Supplier")

@adapter.reaction("Order")
async def handle_order(msg):
    print(f"Processing: {msg}")
    return msg
'''

bspl_protocol = '''
BasicSupplyChain {
    roles Retailer, Supplier
    parameters out orderID key, out product

    Retailer -> Supplier: Order[out orderID key, out product]
    Supplier -> Retailer: Accept[in orderID key, in product]
}
'''

# Transform agents
result = transform_agents_from_content(
    agent_contents={
        "retailer.py": retailer_code,
        "supplier.py": supplier_code
    },
    bspl_content=bspl_protocol,
    bspl_filename="basic_supply_chain.bspl"
)

if result.success:
    print(f"✅ Generated {len(result.generated_files)} files")
    # Access transformed files
    for file in result.generated_files:
        print(f"  {file.filename} ({file.file_type})")
else:
    print(f"❌ Errors: {result.errors}")
```

## 📚 API Reference

### Memory-based API (Recommended for Web Apps)

#### Core Functions

```python
from ra_transformer_lib import (
    transform_agents_from_content,
    validate_agent_content,
    validate_bspl_content,
    create_default_config_memory,
)

# Transform from string content
result = transform_agents_from_content(
    agent_contents: Dict[str, str],
    bspl_content: str,
    bspl_filename: str = "protocol.bspl",
    config_overrides: Optional[Dict] = None
) -> TransformationResult

# Validate inputs
is_valid, errors = validate_agent_content(content: str)
is_valid, errors = validate_bspl_content(content: str)

# Create default configuration
config = create_default_config_memory(agent_contents: Dict[str, str])
```

#### Simulation Execution

```python
from ra_transformer_lib import (
    run_simulation_async,
    SimulationRunner,
    SimulationConfig
)

result = await run_simulation_async(
    transformation_result: TransformationResult,
    config: SimulationConfig = None,
    working_dir: Optional[Path] = None
) -> SimulationResult

# Advanced usage with custom runner
runner = SimulationRunner(config)
result = await runner.run_simulation(transformation_result)
```

#### Data Models

```python
from ra_transformer_lib import (
    TransformationResult,
    AgentFile,
    GeneratedFile,
    SimulationConfig,
    SimulationResult,
    LogEntry,
)

# Access results
result.success: bool
result.generated_files: List[GeneratedFile]
result.config_content: str  # Rendered configuration (string)
result.agent_capabilities: Dict[str, List[str]]  # Capabilities per principal
result.func_to_principal: Dict[str, str]  # Mapping reaction → principal
result.errors: List[str]
result.warnings: List[str]

# Get files by type
agent_files = result.get_files_by_type("agent")
config_files = result.get_files_by_type("config")
helper_files = result.get_files_by_type("helper")
```

### File-based API (For CLI/Research Use)

```python
from ra_transformer_lib import transform_project, generate, create_default_config
from pathlib import Path

# Traditional file-based transformation
output_dir = transform_project(
    output_root=Path("./output"),
    business_bspl_path=Path("protocol.bspl"),
    agent_files=[Path("retailer.py"), Path("supplier.py")],
    config_path=Path(".ra_transformer_config.py")
)

# Alternatively, if you already have AGENT_POOLS / TASK_SETTINGS dicts in memory
# (for example after a web request), you can call the lower-level `generate`:

output_dir = generate(
    output_root=Path("./output"),
    business_bspl_path=Path("protocol.bspl"),
    agent_paths=[Path("retailer.py"), Path("supplier.py")],
    agent_pools_spec=my_agent_pools_dict,
    task_settings_spec=my_task_settings_dict,
)
```

## 🧪 Testing

The library includes comprehensive tests for both APIs:

```bash
# Run all tests
pytest

# Run specific test suites
pytest ra_transformer_lib_src/tests/test_memory_api.py -v
pytest ra_transformer_lib_src/tests/test_ra_transformer_lib.py -v
```

The tests demonstrate:

- Complete system generation and execution
- Memory-based transformations
- Input validation
- Configuration management

## 🌐 Web Application Integration

The memory-based API is designed for web applications. Here's a typical workflow:

### 1. File Upload & Validation

```python
# Validate uploaded files
for filename, content in uploaded_files.items():
    if filename.endswith('.py'):
        is_valid, errors = validate_agent_content(content)
        if not is_valid:
            return {"error": f"Invalid agent {filename}: {errors}"}
    elif filename.endswith('.bspl'):
        is_valid, errors = validate_bspl_content(content)
        if not is_valid:
            return {"error": f"Invalid BSPL: {errors}"}
```

### 2. Generate Default Configuration

```python
# Create default config for user editing
default_config = create_default_config_memory(agent_files)
return {"config": default_config}
```

### 3. Transform with User Configuration

```python
# Apply user's configuration
result = transform_agents_from_content(
    agent_contents=agent_files,
    bspl_content=bspl_content,
    config_overrides=user_config
)

if result.success:
    return {"files": [
        {"name": f.filename, "content": f.content, "type": f.file_type}
        for f in result.generated_files
    ]}
```

### 4. Run Simulation

```python
from ra_transformer_lib import run_simulation_async, SimulationConfig

# Configure simulation
config = SimulationConfig(
    timeout_seconds=30,
    max_agents=10,
    log_level="INFO"
)

# Run simulation
sim_result = await run_simulation_async(result, config)

if sim_result.success:
    print(f"✅ Simulation completed in {sim_result.execution_time:.2f}s")
    print(f"📊 Processed {len(sim_result.logs)} log entries")

    # Access agent statistics
    for agent, stats in sim_result.agent_stats.items():
        print(f"🤖 {agent}: {stats['message_count']} messages, {stats['unique_orders']} orders")

    # Access structured logs
    for log in sim_result.logs[:5]:  # First 5 entries
        print(f"[{log.agent_name}] {log.timestamp}: {log.message}")
else:
    print(f"❌ Simulation failed: {sim_result.errors}")
```

## 📁 Generated Files

The transformer generates a complete, self-contained system:

- **Agent Files**: `*_deferred.py` - Transformed agents with resource management
- **Configuration**: `configuration.py` - System configuration and networking
- **Runner**: `run_complete_system.py` - Script to start all agents
- **Task Config**: `task_config.py` - Resource pool and task duration settings
- **Protocols**: `*.bspl` - BSPL protocol definitions
- **Helpers**: `ra_helpers.py`, `resource_agent.py`, `simple_logging.py`
- **Dependencies**: `requirements.txt` - BSPL framework dependencies
- **Tests**: `test_generated.py` - Validation script

## 🔧 Configuration

### Agent Pools

Define how many ResourceAgent instances each principal has:

```python
AGENT_POOLS = {
    "Retailer": [{"RetailerRA": 1}],
    "Supplier": [{"SupplierRA": 2}]  # 2 instances for load balancing
}
```

### Task Settings

Map reaction functions to ResourceAgent types and durations:

```python
TASK_SETTINGS = {
    "handle_accept": ("RetailerRA", 1.5),    # 1.5 second tasks
    "handle_order": ("SupplierRA", 2.0),     # 2.0 second tasks
}
```

### Assignment Strategies

Control how tasks choose a ResourceAgent within each pool by providing a `strategy` in `AGENT_POOLS` (new format):

```python
AGENT_POOLS = {
    "Retailer": [{"RetailerRA": {"count": 2, "strategy": "round_robin"}}],
    "Supplier": [{"SupplierRA": {"count": 3, "strategy": "one_per_case"}}],
}
```

Supported strategies:
- `round_robin`: cycles through agents evenly (default)
- `random`: picks an agent uniformly at random
- `one_per_case`: same-resource-for-same-case-id (deterministic by case `id`)

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    TRANSFORMED SYSTEM                          │
├─────────────────────────────────────────────────────────────────┤
│ ┌─────────────────┐    ┌─────────────────┐                     │
│ │ RetailerResource│    │ SupplierResource│                     │
│ │     Agent       │    │     Agent       │                     │
│ │   (port 9000)   │    │   (port 9001)   │                     │
│ └─────────────────┘    └─────────────────┘                     │
│         ↑                       ↑                              │
│ ┌───────┴───────┐       ┌───────┴───────┐                     │
│ │   Retailer    │◄─────►│   Supplier    │                     │
│ │ (port 8000)   │       │ (port 8001)   │                     │
│ └───────────────┘       └───────────────┘                     │
│                                                                │
│ Business Logic: Original BSPL Protocol                         │
│ Resource Logic: ResourceAgent Protocol                         │
└─────────────────────────────────────────────────────────────────┘
```

## 🚨 Example Complete Workflow

See `example_memory_usage.py` for a complete demonstration:

```bash
source venv/bin/activate
python3 example_memory_usage.py
```

This example shows the entire transformation process from input validation through system generation and simulation execution.

## 🤝 Getting Started (Development)

1. Install the package in editable mode: `pip install -e ./ra_transformer_lib_src`
2. Install additional deps: `pip install jinja2 pytest`
3. Run the test-suite: `pytest ra_transformer_lib_src/tests/ -v`
4. Follow existing code patterns for new features and keep the README in sync with the codebase.

## 📖 Research Context

This library is part of an ongoing master's thesis on BSPL agent patterns. It enables researchers to:

- Experiment with resource-management patterns at scale
- Generate complete multi-agent systems from minimal inputs
- Study protocol composition and system scaling behaviour
- Build web interfaces for protocol simulation and analysis

The Deferred Resource-Agent pattern provides a clean separation between business logic and resource management, making BSPL systems more scalable and maintainable.

```

```

# KikoSim - Event-Driven Resource-Aware Simulation Framework

This repository contains the complete implementation and evaluation materials for my master's thesis on resource-aware simulation of kiko agents.

## 📖 About This Project

KikoSim offers event-driven, resource-aware simulations for Kiko agents. The main features are resource allocation, time coordination, and output of minable logs. The agent that is being simulated can also run in production

**Key capabilities:**

- Virtual time coordination enabling fast-forward simulation
- Resource allocation with configurable capacity and timing
- Process mining integration with analysis-ready logs
- Non-intrusive instrumentation preserving business logic

## 🚀 Quick Start

Get the simulation framework running in 3 simple steps:

### 1. Setup Dependencies

```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# install dependencies
pip install -r backend/requirements.txt
cd ra_transformer_lib_src && pip install -e . && cd ..
# clone bspl in the ra_transformer_lib_src directory and install its dependencies
cd ra_transformer_lib_src && git clone https://gitlab.com/masr/bspl.git && cd ..
cd ra_transformer_lib_src/bspl && pip install -e . && cd ../..

# Verify BSPL installation
python -c "import bspl; print('✅ BSPL OK')"

# Install frontend dependencies
cd frontend && npm install && cd ..
```

### 2. Start Backend Server

```bash
# Ensure virtual environment is active
source venv/bin/activate

# Start the FastAPI backend (auto-starts Redis)
cd backend && python main.py
```

**Backend running at:** http://localhost:8080

### 3. Start Frontend Interface

```bash
# In a new terminal
cd frontend && npm run dev
```

**Frontend running at:** http://localhost:5173

## Getting Started with a First Simulation

Here's a quick first walkthrough:

1. **Make sure both backend and frontend are running** (follow steps above)
2. **Open the web interface** at http://localhost:5173
3. **Upload the Alice & Bob protocol**:
   - Click "Upload Protocol"
   - Navigate to `benchmarking/alice_asks_bob`
   - Upload the bspl protocol and the alice and bob agents
4. **Configure your first simulation**:
   - Set **Simulation Rounds**: `100`
   - Try different **Resource Configurations**:
     - Start with 2 Alice resources, 2 Bob resources
     - Experiment with 1 Alice, 3 Bob resources to see queuing effects
   - Adjust **Task Durations** (e.g., "1-3s", "500ms-2s") to see timing impacts
5. **Run the simulation** and watch the real-time monitoring
6. **Explore the results**: Check the generated CSV logs for process mining analysis

---

## 📋 Prerequisites

- **Python 3.11+** for the backend and transformation library
- **Node.js 18+** for the React frontend
- **Redis** (automatically started by backend - no manual setup needed)

## Architecture

- **Backend**: FastAPI server managing simulations and API
- **Frontend**: React application for simulation monitoring
- **BSPL**: Protocol verification and agent generation
- **RA Transformer**: Library for resource agent pattern implementation and time agent pattern
- **Virtual Time System**: Coordinated simulation time management

## 📊 Evaluation and Reproducibility

This repository contains complete evaluation materials including:

- **Demonstration runs**: Three MarketSupplyChain scenarios testing different resource configurations
- **Production baseline**: Compatibility tests running agents outside simulation
- **Scaling tests**: Performance evaluation with 50× and 75× resource agents
- **Cross-process compatibility**: Logistics and approver protocol integration testing

**Reproducing results**: Navigate to `evaluation/evaluation_runs/` and follow the README instructions for each study. All outcome data, scripts, and configurations are preserved.

### OrderManagement Sequence Analysis

For the `benchmarking/ordermanagement` scenario, the backend can export compact, sequence-ready logs and a helper script can analyze path coverage:

- Auto-export: After a run completes, the backend writes `backend/ordermanagement_sequences_latest.csv` with one row per sent business message: `id, step, code (e.g., B>S:order), message, agent, timestamp`.
- Analyze: From repo root (venv active), run:

```bash
python backend/analyze_ordermanagement_sequences.py
```

The analyzer reports:
- Earliest/latest virtual time and a half-time threshold
- Coverage on terminal cases only (matched canonical sequences among the 34 you defined)
- Count of non-terminal cases (in the filtered set)
- Top matched canonical sequences (with counts)
- Variant diversity on terminal cases:
  - Distinct executed variants
  - Distinct canonical variants matched
  - Distinct non-canonical variants (also listed with counts)

Tip: To surface more cancellation variants, increase durations for Seller `send_delivery_req` and Logistics `send_deliver` relative to Buyer `send_pay` in the UI configuration.

## Development

### Project Structure

```
master-thesis/
├── backend/              # FastAPI web server and API
│   └── simulation_runs/  # Generated simulation instances
├── frontend/             # React simulation interface
│   └── src/              # React components and logic
├── ra_transformer_lib_src/  # Core framework libraries
│   ├── bspl/            # BSPL protocol interpreter (embedded)
│   ├── ra_transformer_lib/  # Resource allocation transformer
│   │   ├── jinja_templates/ # Code generation templates
│   │   └── templates/    # Agent template files
│   └── tests/           # Library unit tests
├── benchmarking/         # Business process examples
│   ├── alice_asks_bob/   # Simple two-agent protocol
│   ├── basic-supply-chain-test/ # Basic supply chain examples
│   ├── bspl-scenarios/   # Various BSPL protocol scenarios
│   └── market_supply_chain/  # MarketSupplyChain protocol
├── evaluation/          # Complete evaluation materials
│   └── evaluation_runs/ # Demonstration, production, and scaling tests
│       ├── demonstration_runs/ # Feature demonstration results
│       ├── extreme_scaling/    # Performance scaling tests
│       └── prod_baseline/      # Production compatibility tests
├── deferred_resourceagent_pattern/ # Original resource pattern implementation. Used during development, no virtual time
├── run_timeservice_prototype/      # Virtual time system prototype. Used during development
```

### Adding Dependencies

- Backend: Add to `backend/requirements.txt`
- Frontend: Use `npm install` in `frontend/`
- Core library: Update `ra_transformer_lib_src/pyproject.toml`

## ⚠️ Important Notes

1. **🐍 Virtual Environment**: The backend must run in the virtual environment for simulations to work

   - Start backend with: `source venv/bin/activate && python main.py`
   - Simulation runner automatically detects and uses the correct Python executable

2. **🌐 Port Usage**:
   - Backend: 8080
   - Frontend: 5173
   - Simulations: 8000-9999 range
   - Redis: 6379 (started automatically)

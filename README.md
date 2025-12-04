# KikoSim: A Resource-Aware Agent-Based Simulation Framework for Flexible Process Interactions

This repository contains the complete implementation and evaluation materials for the paper titled "Agent-Based Simulation of Flexible Process Interactions."

## 📋 Prerequisites

- **Python 3.11+** for the backend and transformation library
- **Node.js 18+** for the React frontend


## 🚀 Quick Start
Get the simulation framework running in 3 simple steps:

### 1. Setup Dependencies

Install Redis, if you do not already have it installed, according to your operating system: https://redis.io/docs/latest/operate/oss_and_stack/install/archive/install-redis/

```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt
cd ra_transformer_lib_src && pip install -e . && cd ..

# Clone BSPL in ra_transformer_lib_src directory and install its dependencies
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

# Start the FastAPI backend (automatically starts Redis)
cd backend && python main.py
```

**Backend running at:** http://localhost:8080

### 3. Start Frontend Interface
In a new terminal window or tab, run:
```bash
cd frontend && npm run dev
```

**Frontend running at:** http://localhost:5173

You can watch a screencast showing how to use KikoSim at: https://youtu.be/HQ9nCgoX1NY

## Scenarios
The /scenarios directory includes three scenarios: order management, policy management, and treatment. For each scenario, a BSPL protocol and agent implementations are provided. Below, we outline the baseline experimental setup and the results of each simulation experiment for the order management scenario, which is used throughout the paper.

## ⚙️ Baseline Experimental Setup for the Order Management Scenario
### 1. Configuration of Resources
| Orchestrator | Resource Type | Resource Capacity | Resource Allocation Strategy |
| :--- | :--- | :--- | :--- |
| Buyer | Purchaser | 1 | Round Robin |
| Seller | Clerk | 1 | Round Robin |
| Seller | Accountant | 1 | Round Robin |
| Logistics Provider | Courier | 1 | Round Robin |
| Logistics Provider | Warehouse Worker | 1 | Round Robin |

### 2. Configuration of Processing Times for the Order Management Scenario
| Orchestrator | Resource Type | Activity | Processing Time (minute) |
| :--- | :--- | :--- | :--- |
| Buyer | Purchaser | send_order | 5 |
| Buyer | Purchaser | send_pay | 15 |
| Buyer | Purchaser | send_confirm | 10 |
| Buyer | Purchaser | send_cancel_req | 10 |
| Buyer | Purchaser | on_invoice | 5 |
| Buyer | Purchaser | on_deliver | N(15, 2) |
| Buyer | Purchaser | on_reject | 5 |
| Buyer | Purchaser | on_cancel_ack | 5 |
| Logistics Provider | Warehouse Worker | on_delivery_req | N(60, 6) |
| Logistics Provider | Courier | send_deliver | N(360, 30) |
| Seller | Clerk | send_delivery_request | 30 |
| Seller | Clerk | send_cancel_ack | 5 |
| Seller | Clerk | send_reject | 5 |
| Seller | Clerk | on_order | N(45, 7) |
| Seller | Clerk | on_cancel_req | N(35, 3) |
| Seller | Clerk | on_confirm | 10 |
| Seller | Accountant | send_invoice | N(30, 5) |
| Seller | Accountant | on_pay | 30 |

## Results for the Order Management Scenario
The statistics computed for each simulation experiment are shown below.

| # Clerks |# Couriers | Avg. CT (hour) | Avg. QT Courier (hour) | Avg. QT Clerk (hour) |
| :--- | :--- | :--- | :--- | :--- |
| 1 | 1 | 113.27 | 149.22 | 5.04 |
| 1 | 2 | 49.54 | 43.96 | 3.06 |
| 1 | 3 | 34.43 | 15.35 | 5.89 |
| 1 | 4 | 32.93 | 1.24 | 8.67 |
| 2 | 1 | 187.37 | 305.83 | 0.87 |
| 3 | 1 | 220.73 | 298.78 | 0.37 |
| 4 | 1 | 237.96 | 339.26 | 0.25 |

For each experiment, the /results directory contains raw simulation logs that include all initiated enactments. Additionally, it contains filtered simulation logs that include only completed enactments, which we used for our analysis.

#!/usr/bin/env python3
"""
Insurer agent for PolicyManagement.

Behavior:
- Initiates offers with a new policy id and random premium.
- On accept: sends create with a date.
- On reject: records date, no create.
- On request from Auditor: reports policies whose premium <= amount (only for accepted/created policies).
"""

import uuid, random
from datetime import datetime
from bspl.adapter import Adapter
from configuration import systems, agents
from PolicyManagement import offer, accept, reject, create, request, report
from simple_logging import setup_logger

log = setup_logger("insurer")
adapter = Adapter("Insurer", systems, agents)


async def send_offer(message: offer):
    await adapter.send(message)
    try:
        pid = message["id"]
        prem = message["premium"]
        log.info(f"SENT offer: id={pid}, premium={prem}")
    except Exception:
        log.info("SENT offer")


async def send_create(message: create):
    await adapter.send(message)
    try:
        pid = message["id"]
        date = message["date"]
        log.info(f"SENT create: id={pid}, date={date}")
    except Exception:
        log.info("SENT create")


async def send_report(message: report):
    await adapter.send(message)
    try:
        rid = message["r_id"]
        pid = message["id"]
        prem = message["premium"]
        info = message["info"]
        # Policy-centric id (policy id) with explicit r_id for audit-centric view
        log.info(f"SENT report: id={pid}, r_id={rid}, premium={prem}, info={info}")
    except Exception:
        log.info("SENT report")




# Simple state stores
policies: dict[str, dict] = {}
created_low: list[str] = []   # policies created with premium 10, not yet used in a report
created_high: list[str] = []  # policies created with premium 20, not yet used in a report
pending_requests: list[dict] = []  # each: {r_id, amount, fulfilled}

def _policy(pid: str) -> dict:
    return policies.setdefault(pid, {
        "premium": None,
        "agreed": False,
        "date": None,
        "created": False,
    })


@adapter.reaction(accept)
async def on_accept(msg):
    pid = msg["id"]
    prem = msg["premium"]
    agr = msg["agreed"]
    s = _policy(pid)
    s["premium"] = prem
    s["agreed"] = True if agr else True
    # Send create with a date (ISO)
    date = datetime.utcnow().isoformat()
    c = create(id=pid, premium=prem, agreed=agr if agr else "YES", date=date)
    await send_create(c)
    s["date"] = date
    s["created"] = True
    # Track created policy in category queue
    try:
        prem_val = float(prem)
        if prem_val <= 10:
            created_low.append(pid)
        else:
            created_high.append(pid)
    except Exception:
        # Unknown premium; do not categorize
        pass
    return msg


@adapter.reaction(reject)
async def on_reject(msg):
    pid = msg["id"]
    prem = msg["premium"]
    date = msg["date"]
    s = _policy(pid)
    s["premium"] = prem
    s["agreed"] = False
    s["date"] = date
    log.info(f"RECEIVED reject: id={pid}, premium={prem}, date={date}")
    return msg


@adapter.reaction(request)
async def on_request(msg):
    rid = msg["r_id"]
    amount = msg["amount"]
    # Queue this request and attempt matches across all pending requests
    try:
        amt = float(amount)
    except Exception:
        amt = None

    pending_requests.append({"r_id": rid, "amount": amount, "amount_f": amt, "fulfilled": False})

    # Matching policy:
    # - For amount <= 15: try to match one low-premium (10) policy
    # - For amount >= 25: try to match one high-premium (20) policy; if none, fallback to low
    # Greedy matching across all pending requests upon each new request arrival
    for req in pending_requests:
        if req["fulfilled"]:
            continue
        amt_f = req.get("amount_f")
        if amt_f is None:
            continue
        pid_to_report = None
        prem_val = None
        if amt_f <= 15 and created_low:
            pid_to_report = created_low.pop(0)
            prem_val = 10
        elif amt_f >= 25:
            if created_high:
                pid_to_report = created_high.pop(0)
                prem_val = 20
            elif created_low:
                pid_to_report = created_low.pop(0)
                prem_val = 10

        if pid_to_report:
            req["fulfilled"] = True
            p = policies.get(pid_to_report, {})
            prem = p.get("premium", prem_val)
            info = f"Policy {pid_to_report} premium {prem}"
            # With premium as 'out' on report, we can emit directly
            rep = report(r_id=req["r_id"], id=pid_to_report, amount=req["amount"], premium=prem, info=info)
            await send_report(rep)
    return msg


async def initiator():
    """Emit a new offer with random premium."""
    pid = f"P{uuid.uuid4().hex[:8]}"
    premium = random.choice([10, 20])
    s = _policy(pid)
    s["premium"] = premium
    o = offer(id=pid, premium=premium)
    await send_offer(o)


if __name__ == "__main__":
    log.info("Insurer STARTING...")
    try:
        adapter.start()
    except KeyboardInterrupt:
        log.info("Insurer INTERRUPTED")
    except Exception as e:
        log.error(f"Insurer CRASHED: {e}")
        import traceback; traceback.print_exc()
    finally:
        log.info("Insurer ENDING...")

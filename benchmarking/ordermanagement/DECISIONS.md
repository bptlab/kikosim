# OrderManagement – Decision Logic (current)

This scenario demonstrates flexible agent behavior within BSPL constraints while keeping the code simple and RA‑compatible.

Buyer (buyer.py)

- State per id: price, payment_ref, delivery_date, outcome, and flags (invoice_received, pay_sent, cancel_sent, pre_cancel, delivery_received, confirm_sent).
- Initiator behavior: after sending order, may mark the case for pre‑cancel (≈20%). Pre‑cancels are dispatched via a RA‑deferred send (send_cancel_req) in a later initiator call when safe (not delivered, no outcome).
- Decision tree (on reactions):
  - If cancellation was requested (cancel_sent) or outcome set → do nothing further (no pay/confirm after cancel).
  - If payment_ref and delivery_date exist and no outcome → send confirm (deterministic).
  - If delivery_date exists, price is known, and pay not sent → send pay then confirm (fallback to ensure progress).
  - If invoice (price) is known, no outcome, and no prior cancel → usually pay (70%); else (30%) send cancel_req (RA‑deferred) if not delivered yet.
- Rationale:
  - Confirm requires both payment_ref and delivery_date; pay/cancel are valid only while outcome is unset.
  - Fallback guarantees completion when delivery arrives before pay.

Seller (seller.py)

- State per id: item, invoice_sent, delivery_req_sent, outcome, cancel_req_received, rescind.
- Cancellation based on actual emission: on cancel_req, if no delivery_req has been emitted yet (checked via adapter.history), send cancel_ack and close the case.
- Mixed sending patterns on order (randomized):
  - Sometimes send only invoice now (delivery_req sent later on pay).
  - Sometimes send invoice then delivery_req in the same decision call.
  - Sometimes send delivery_req then invoice in the same decision call.
- on_pay: if delivery_req is still pending (invoice‑only path), send delivery_req to progress.
- 10% chance to reject immediately on order (demonstrates rejection path).
- Rationale:
  - cancel_ack requires nil delivery_req; checking actual emission avoids races with RA delays.
  - Mixed ordering unlocks legal interleavings without timers while preserving progress.

Logistics (logistics.py)

- Sends deliver immediately on delivery_req (no randomness).

Deferred sends

- All outbound messages are wrapped in single‑arg `send_*` functions and are automatically delayed by ResourceAgents; durations/strategies configurable in UI.

Progress guarantees

- Buyer fallback ensures cases finish even if delivery arrives before pay.
- Seller deterministically acknowledges cancellation only if consistent (before delivery_req emits), otherwise proceeds to fulfillment per policy.

Notes / future options

- Tune policy weights or cancel probabilities to bias towards certain variants.
- Add a time‑triggered wait to support "cancel after pay + cancel_ack" without stalling (would require a tiny initiator or RA timer).

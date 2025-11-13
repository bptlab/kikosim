# OrderManagement – Decision Logic (current)

Buyer (buyer.py)

- State per id: price, payment_ref, delivery_date, outcome, and flags (invoice_received, pay_sent, cancel_sent, pre_cancel, delivery_received, confirm_sent).
- Initiator behavior: after sending order, may mark the case for pre‑cancel (≈20%). Pre‑cancels are dispatched via a RA‑deferred send (send_cancel_req) in later initiator calls when safe (not delivered, no outcome).
- Decision tree (on reactions):
  - If a cancellation was requested (cancel_sent) or outcome is set → do nothing further (no pay/confirm after cancel).
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

Notes

- Tune randomization weights or durations to bias variants.

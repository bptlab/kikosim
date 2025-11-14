# PolicyManagement – Decision Logic

Roles: Insurer, Subscriber, Auditor

Protocol

```
PolicyManagement {
  roles Insurer, Subscriber, Auditor
  parameters out r_id key, out id key, out premium, out date, out amount, out info
  private agreed

  Insurer   -> Subscriber: offer   [out id key, out premium]
  Subscriber -> Insurer:   accept   [in  id key, in premium, out agreed, nil date]
  Subscriber -> Insurer:   reject   [in  id key, in premium, nil agreed, out date]
  Insurer   -> Subscriber: create  [in  id key, in premium, in agreed, out date]
  Auditor   -> Insurer:   request  [out r_id key, out amount]
  Insurer   -> Auditor:   report   [in  r_id key, in id, in amount, out premium, out info]
}
```

Behavior

- Insurer:
  - Initiates `offer(id, premium)` every initiator round; `premium ∈ {10, 20}`.
  - On `accept`, sends `create(id, premium, agreed, date)`; stores and categorizes created policies (low=10, high=20).
  - On `request(r_id, amount)`, greedily matches exactly one created policy per request:
    - amount ≤ 15 → match one low (10) policy if available
    - amount ≥ 25 → match one high (20) policy if available; otherwise fallback to low (10)
  - Emits `report(r_id, id, amount, premium, info)` directly (premium is an output on report to avoid cross-key joins).
  - Unused created policies remain available for future requests; fulfilled requests are not reused.
- Subscriber:
  - On `offer`, accepts with ≈20% probability; otherwise rejects with a `date`.
  - `accept` has `nil date`; `reject` has `nil agreed` as per constraints.
- Auditor:
  - Initiates `request(r_id, amount)` every 5 initiator rounds; `amount ∈ {15, 25}`; logs `report`s.

Views and Export (Disco)

- Policy view (id-centric):
  - Business logs use `id=<policy_id>` for offer/accept/reject/create and for `report` as well.
  - This lets Disco group the policy lifecycle and associated resource actions by policy id.
- Audit view (r_id-centric):
  - Auditor business logs set `id=<r_id>` on "SENT request" so the request shows up as its own case.
  - Auditor’s ResourceAgent logs (`TASK_*`) also use the request id as enactment id (helper falls back to `r_id` when `id` is absent).
  - Net effect in Disco: you see the auditor’s request as a small tree (top-right), while the rest of the process tree follows the policy enactment id (id).

Notes

- KikoSim currently doesn’t fully understand composite ids in exports/visualization. The audit (r_id) and policy (id) keys form a composite context in the protocol, but joining these across views is limited.
- To keep the model faithful yet pragmatic:
  - `report` uses `out premium` so Insurer can emit reports without cross-key joins.
  - We intentionally set `id=<r_id>` on the auditor’s "SENT request" and let the RA helper fall back to `r_id` as enactment id when `id` is absent. This small hack makes the audit request visible as a separate case in Disco, while the policy view remains coherent.
  - We only overload `id` for the Auditor’s request; all other business logs keep `id=<policy_id>` to preserve policy-centric grouping.
- Disco can show both perspectives simultaneously because resource events for the Auditor use `r_id` as the enactment id, while business and other resource events for Insurer/Subscriber use policy `id`.

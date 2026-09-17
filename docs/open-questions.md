# Open questions

Track questions that need evidence, a decision, or an assigned owner.

| Question | Why it matters | Next action | Owner | Status |
| --- | --- | --- | --- | --- |
| Which identity provider and authentication methods must the system support? | Determines trust boundaries and integration design | Document the intended deployment environment and identity integrations | Mike | Open |
| What privileged actions and resources require just-in-time access? | Defines the initial authorization model | Inventory roles, systems, and access paths | Mike | Open |

## 2026-09-16 updates

- Prototype identity source: local username/password accounts (decided by Mike).
- First protected resource: SSH access (decided by Mike); enforcement is future work.
- Input: live webcam video. Failed checks should eventually request another check;
  implementation is deferred.
- Define allowed SSH hosts, OS principals, access durations, and approvals.
- Choose SSH certificate issuance or brokered sessions and establish key custody.
- Decide whether identity matching and an explicit liveness challenge are required.
- Validate detector preprocessing/class mapping and calibrate thresholds on labeled
  real and synthetic samples before using results in an access policy.
- Define recheck limits, expiry, terminal outcomes, and audit retention later.

# Decision log

Record decisions that change project direction, architecture, threat exposure, or implementation.

## Template

### YYYY-MM-DD — Decision title

- **Status:** proposed | decided | superseded
- **Decision:**
- **Why:**
- **Security impact:**
- **Alternatives considered:**
- **Consequences / next steps:**

### 2026-09-16 — Modular webcam extraction

- **Status:** decided
- **Decision:** Use local prototype accounts and live webcam video; target SSH
  access in the later PAM integration. Preserve original capstone code.
- **Why:** User selected these boundaries and prioritized testing, maintenance,
  and replaceable components.
- **Security impact:** Media evidence is not identity verification or permission
  to access SSH. Inference errors produce unavailable results.
- **Alternatives considered:** Reusing conferencing rooms would preserve unwanted
  coupling. Immediate microservices add deployment and consistency complexity.
- **Consequences / next steps:** Modular single-process core, injected adapters,
  local webcam harness. Automated repeat-check behavior is explicitly deferred.
  Define SSH targets and authorization before implementing a credential broker.

### 2026-09-17 — CNN-only model check

- **Status:** decided
- **Decision:** Use a single CNN backend and remove model selection from the UI
  and application service. Retain classifier injection for testing and upgrades.
- **Why:** User selected CNN as the only model check going forward.
- **Security impact:** Requests cannot choose another model; failures remain
  unavailable results and do not add evidence.
- **Alternatives considered:** Keeping a multi-model registry adds unused complexity.
- **Consequences / next steps:** Reduced runtime dependencies. Biometric matching
  and device authentication remain separate future layers.

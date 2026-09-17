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

### 2026-09-16 — Per-capture model selection

- **Status:** decided
- **Decision:** Add CNN/ViT radio selection, pin the model per capture, and start a
  fresh evidence window when the user changes models. Keep CNN as default.
- **Why:** User requested a model toggle; adapters preserve modularity.
- **Security impact:** No cross-user global model setting; model errors do not
  silently switch backends or add evidence.
- **Alternatives considered:** A global mutable classifier mixes user choices;
  switching inside an existing window mixes evidence from different detectors.
- **Consequences / next steps:** ViT adds PyTorch/Transformers dependencies.
  Accuracy and threshold calibration remain separate validation work.

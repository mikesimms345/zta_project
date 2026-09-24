# Modular architecture and SSH integration boundary

## Current flow

Browser local account login → authenticated capture session → JPEG validation →
FrameClassifier adapter → rolling evidence policy → informational browser result.

The application layer owns capture lifecycle. The model only produces a label and
model version. Evidence policy produces collecting/flagged/below_threshold, never
an authorization decision. Browser retries, account identity, and future SSH
actions do not belong inside inference code.

Keeping these as Python modules initially makes tests and deployment simple.
Independent services can be introduced later if scaling requires them; doing so
now would add network contracts and distributed state without a demonstrated need.

## Future PAM workflow (proposed, not implemented)

1. Authenticate a local account, then eventually an external identity provider.
2. Request a specific SSH host, OS principal, purpose, and duration.
3. Collect required verification evidence, bound to that account and request.
4. Evaluate authorization using identity, target allowlists, requested privilege,
   evidence freshness, and any approval requirements.
5. An SSH broker issues a narrowly scoped, short-lived credential only after an
   explicit authorization decision. Choose certificate vs. brokered-session
   architecture separately. The web/inference modules must not hold a CA key.
6. Record decisions and credential lifecycle in a dedicated audit sink, without
   passwords, private keys, raw webcam images, or unnecessary biometric data.

A failed media check should eventually request another check. Its challenge,
retry count, timeout, and terminal behavior remain deferred by user instruction.
No SSH endpoints, commands, credential issuance, or automatic retries exist now.

## Prototype limitations and validation needs

- Webcam JPEGs are client supplied. A camera API does not prove live, unmodified
  capture. The current model does not prove identity or resist replay by itself.
- Threshold and class mapping follow the capstone; training preprocessing and
  measured false-positive/false-negative behavior need labeled evaluation.
- Local accounts use hashed passwords and operator provisioning. External IdP,
  MFA, login throttling, durable session revocation, and audit persistence are
  future work. Flask signed cookies are not centrally revocable on logout.
- Evidence exists only in process memory, and inference is serialized. Do not
  deploy multiple workers before extracting a shared capture store and defining
  ordering/concurrency behavior. Expired captures are pruned on service access.
- A process-generated signing key makes sessions invalid after restart. This is
  a local loopback prototype, not an externally deployed PAM service.
- The camera UI has automated HTTP and syntax checks, but physical camera
  permission and end-to-end capture require a manual browser check.

## Extension checklist

To add a model, implement `FrameClassifier.classify(bytes) -> Prediction`, return
a stable version identifier, and raise on failure. Inject it into `create_app`.
To change evidence thresholds, configure `WINDOW_SIZE` and `FAKE_THRESHOLD`.
To add identity matching, introduce a separate evidence contract; do not reinterpret
the REAL media label as an enrolled-identity match.

## CNN model check

The application uses one injected CNN classifier. The browser starts a capture
without a model choice; requests containing a model-selection field are rejected.
Every new capture has a fresh evidence window. Model failures report unavailable
without adding evidence. The classifier protocol remains replaceable for tests
and future CNN upgrades. JPEG validation remains independent of inference.

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

### 2026-10-28 — Python-owned OpenCV capture prototype

- **Status:** superseded
- **Decision:** For the local prototype, Python owns camera capture, RGB frame
  conversion, LiteRT inference of the `.tflite` model, and the native preview. The
  browser only starts or stops a check and receives state over one server-sent
  event stream. The first 75 predictions fill a rolling window; inference then
  continues and replaces the oldest label with each new prediction.
- **Why:** Per-frame browser JPEG uploads added avoidable encoding and HTTP
  overhead to a same-machine prototype. A visible preview remains necessary for
  manual testing, but it does not need to cross the browser/server boundary.
- **Security impact:** Removing client frame uploads narrows one untrusted-input
  boundary, but OpenCV capture does not establish camera integrity or liveness.
  Any authenticated client could trigger the camera attached to the Flask host,
  so the prototype remains loopback-only.
- **Alternatives considered:** Roboflow InferencePipeline was deferred. Browser
  capture with WebRTC is more appropriate if the camera later resides on a remote
  user endpoint. Repeated frame POSTs preserve the old topology but not its need.
- **Consequences / next steps:** OpenCV with GUI support is a runtime dependency.
  Google LiteRT replaces the TensorFlow/`tflite_runtime` fallback. The operator,
  logout/navigation cleanup, capture expiry, or a failure ends the rolling check.
  Manual validation must cover camera selection, native-window behavior, model
  execution, continued inference after 75 frames, and release on stop, logout,
  navigation, expiry, and failure. A remote
  deployment requires a new trusted endpoint/camera transport design.

### 2026-10-28 — RealSense RGB-D liveness prototype

- **Status:** decided
- **Decision:** Replace generic camera-index capture with one `pyrealsense2` owner
  for synchronized D435 RGB and depth. Align depth to RGB, keep LiteRT media
  classification and depth liveness as separate evidence paths, and render RGB
  and colorized depth side by side in one OpenCV window. Liveness uses facial
  depth coverage, non-planar relief, and a move-closer/return challenge.
- **Why:** Depth is available from the selected D435 and can add a prototype
  presentation-attack signal without sending raw biometric media to the browser.
- **Security impact:** A depth candidate or completed movement challenge is not
  identity proof or authorization. The heuristics and thresholds are uncalibrated,
  and the local process still cannot prove sensor or host integrity.
- **Alternatives considered:** Opening RGB through `cv2.VideoCapture` alongside a
  separate depth pipeline risks competing device ownership and unsynchronized
  frames. Folding liveness into the CNN label would erase distinct evidence
  meanings. A learned RGB-D PAD model remains future work pending data and
  evaluation.
- **Consequences / next steps:** `pyrealsense2` and a USB 3-connected D435 are
  required for the default run. Validate alignment, depth quality, thresholds,
  challenge usability, and attack behavior on physical hardware.

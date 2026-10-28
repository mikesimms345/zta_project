# Research log

Use one entry per meaningful finding.

## Template

### YYYY-MM-DD — Finding title

- **Question:**
- **Source:**
- **Finding:**
- **Confidence:** confirmed | plausible | unverified
- **Security implication:**
- **Follow-up:**

### 2026-09-16 — Repository requirements and extraction

- **Question:** What requirements govern the standalone pipeline?
- **Source:** https://github.com/mikesimms345/ZTA_PAM_System/blob/master/docs/brief.md
  and `AGENTS.md`, `README.md`, `docs/decisions.md`, `docs/open-questions.md` on master.
- **Finding:** Repository is in discovery/design. It calls for scoped, time-bounded,
  auditable privileged access and leaves IdP and protected resources unspecified.
  User supplied local accounts, webcam capture, and SSH scope in this session.
- **Confidence:** confirmed
- **Security implication:** Synthetic-media detection is a separate signal from
  identity and authorization; no existing specification establishes it as sufficient.
- **Follow-up:** Define SSH policy and evaluate media detection before enforcement.

### 2026-10-28 — D435 RGB-D liveness feasibility

- **Question:** Can synchronized D435 depth liveness run with the existing local
  LiteRT path and appear in the same OpenCV preview?
- **Source:** RealSense SDK Python OpenCV and depth-to-color alignment examples,
  D435 specifications, NIST SP 800-63B-4 biometric guidance, and RGB-D face PAD
  research cited in `docs/SYSTEM_DESIGN_AND_EXTENSION_GUIDE.md`.
- **Finding:** `pyrealsense2` can provide aligned color/depth NumPy arrays to two
  independent evidence paths and one side-by-side OpenCV renderer. Depth geometry
  and an active movement challenge are feasible prototype signals.
- **Confidence:** confirmed for software structure and one synchronized 640x480
  frameset from a connected D435. GUI behavior, a human challenge, and
  presentation-attack performance remain unverified until manual evaluation.
- **Security implication:** Local RGB-D processing reduces raw-media movement but
  does not establish sensor, endpoint, identity, or authorization integrity.
- **Follow-up:** Test live users, prints, displays, masks, missing depth, lighting,
  distance, replay, and injected frames; calibrate every threshold before policy use.

### 2026-10-28 - Python-owned RGB-D prototype implementation and verification

- **Question:** What was implemented and what evidence supports the current
  RealSense, LiteRT, liveness, and preview prototype?
- **Source:** The active `zta/` modules, `tests/`, dependency files, README, and
  architecture documents; RealSense SDK Python OpenCV and alignment examples:
  https://github.com/realsenseai/librealsense/blob/master/wrappers/python/examples/readme.md
  and
  https://github.com/realsenseai/librealsense/blob/master/wrappers/python/examples/align-depth2color.py.
- **Finding:** The browser no longer owns or uploads camera frames. Python owns
  one local RealSense D435 pipeline and supplies synchronized 640x480 BGR8 color
  and Z16 depth at 30 fps. The adapter aligns depth to color and converts SDK
  frames into SDK-free `RGBDFrame` values. At each sampling point, the same
  capture is routed to two independent evidence paths: RGB is sent to the media
  classifier, while RGB plus aligned depth is sent to the depth-liveness analyzer
  and temporal challenge policy. One OpenCV window displays annotated RGB/LiteRT
  output and colorized depth/liveness output side by side. JavaScript starts and
  stops the check and displays server-sent status, while browser camera and
  microphone permissions remain disabled.
- **Finding:** TensorFlow Lite interpreter use was replaced by
  `ai-edge-litert`. The adapter lazily loads and reuses its interpreter, handles
  supported float and quantized tensors, dequantizes supported output tensors,
  and reports a SHA-256 fingerprint of the model artifact as `model_id`. That
  identifies the model version; it is not a biometric hash. The Roboflow
  Inference Pipeline was deliberately not incorporated.
- **Finding:** The 75-frame value is a rolling media-evidence window, not a
  capture termination limit. The RGB-D worker continues acquiring frames,
  running liveness, and running inference after the first full window until the
  user stops it, the capture expires, or an error occurs. Media and liveness
  state remain separate: a liveness result does not rewrite a media label.
- **Finding:** Depth liveness currently uses an OpenCV frontal-face detector,
  aligned-depth coverage, a 0.3-1.5 m working range, fitted-plane residual
  relief, and a move-closer/return challenge. The implementation requires at
  least 60 percent valid face depth and 12 mm measured relief by default,
  requires five candidate observations, and marks repeated planar observations
  as a suspected spoof. These are prototype defaults, not calibrated biometric
  or presentation-attack performance claims.
- **Finding:** The session added injected tests for continuous camera operation,
  source and preview cleanup, synthetic planar and curved depth, movement-policy
  completion, repeated-planar handling, side-by-side composition, RealSense SDK
  conversion and alignment behavior, LiteRT behavior, and the Flask lifecycle.
  Nine automated tests passed in a fresh Python 3.11 environment containing all
  declared dependencies. Python compilation, JavaScript syntax validation, and
  `git diff --check` also passed. A connected D435 produced one synchronized
  640x480 RGB-D frameset with valid depth, and its captured RGB completed one
  LiteRT inference. That single result is execution evidence, not detector
  accuracy evidence.
- **Confidence:** confirmed for the checked-in structure, injected tests,
  dependency installation, one physical D435 frameset, alignment dimensions,
  analyzer invocation, and one real-model inference. The visible GUI on the
  target host, a human completing the movement challenge, operation across long
  sessions, detector accuracy, threshold calibration, and presentation-attack
  performance remain unverified.
- **Security implication:** Local ownership removes repeated browser frame-upload
  requests and reduces raw-media exposure, but the Python process still trusts
  its host, camera connection, and SDK inputs. A `real` media result or `live`
  depth result does not identify the person, establish trusted sensor provenance,
  authorize access, or issue an SSH credential.
- **Follow-up:** Perform manual end-to-end D435 testing with representative live
  users and attack artifacts; measure latency and error rates; verify long-run
  resource cleanup; and calibrate thresholds before using the results in policy.

### 2026-10-28 - Biometric hash, identity features, and WebAuthn binding

- **Question:** Should this RGB-D layer output the project-note biometric hash,
  which source should provide the feature vector, and where should that output go?
- **Source:** Current contracts and flow in `zta/domain.py`,
  `zta/liveness/domain.py`, `zta/camera.py`, and `zta/web/__init__.py`; the
  proposed architecture in `docs/SYSTEM_DESIGN_AND_EXTENSION_GUIDE.md`; W3C
  WebAuthn Level 3 https://www.w3.org/TR/webauthn-3/; NIST SP 800-63B-4
  https://pages.nist.gov/800-63-4/sp800-63b.html; and FIDO authentication and
  privacy guidance https://fidoalliance.org/specifications/ and
  https://fidoalliance.org/fido-authentication-2/privacy-principles/.
- **Finding:** The current LiteRT model does not produce an identity feature
  vector. It classifies a frame as real or fake; any internal representation is
  trained for that task and is not an enrolled or validated face-identity
  embedding. The current depth path produces face location, depth coverage,
  distance, surface relief, and motion state. Those measurements support
  liveness but are low-dimensional, non-unique, and unsuitable as an identity
  template. Depth should remain a liveness and quality signal unless a dedicated,
  evaluated RGB-D identity model is introduced.
- **Finding:** The appropriate future identity input is a detected, aligned,
  quality-checked RGB face from the same fresh capture, processed by a separate
  face-embedding model. An authorized enrollment process must first create a
  versioned protected reference for the account. Verification then performs a
  noise-tolerant comparison between the fresh embedding and the protected
  reference and returns a typed biometric result containing subject and request
  bindings, model and preprocessing versions, template version, quality and
  match outcomes, timestamps, and expiry. Media and depth-liveness evidence
  should gate acceptance and be bound to that same capture, but neither replaces
  identity matching.
- **Finding:** Direct SHA-256 equality cannot perform biometric matching. Normal
  capture variation means two embeddings of the same person will not be
  byte-identical and will therefore have different SHA-256 values. If the
  project retains the specified hash, it should be treated as an integrity or
  transaction commitment created after probabilistic matching, not as the
  matcher or as proof that a template is protected. A canonical, versioned
  biometric evidence record is generally a more useful digest input than an
  unqualified floating-point array. The fresh embedding should remain transient,
  and template protection, retention, revocation, re-enrollment, and key
  separation require explicit design.
- **Finding:** Standard WebAuthn does not allow the Flask application to append
  arbitrary bytes to `authenticatorData`. That structure is constructed by the
  authenticator and contains the RP ID hash, flags, signature counter, and only
  supported authenticator-extension outputs. WebAuthn signs the combination of
  `authenticatorData` and the hash of `clientDataJSON`. Authenticator-local
  biometric recognition is represented to the relying party by the signed user
  verification flag; the biometric data itself is not returned. The external
  D435 process is therefore application evidence, not automatically a FIDO
  authenticator's biometric verification.
- **Finding:** The standards-compatible prototype design is for the server to
  store a short-lived biometric evidence record and its digest, bind that record
  to the subject, capture, access request, and a fresh one-use WebAuthn challenge,
  and then verify the resulting assertion and user-verification flag. If the
  digest must be cryptographically covered by the ceremony, a commitment that
  combines an unpredictable nonce, request context, and evidence digest can be
  placed in or represented by the WebAuthn challenge; the assertion signature
  covers that challenge through `clientDataJSON`. Literal placement in
  `authenticatorData` would require a supported custom authenticator extension
  and likely a custom authenticator implementation, not an ordinary browser and
  commodity platform authenticator.
- **Finding:** At present the RGB-D layer's outputs originate in the Python
  worker, remain as in-memory media and liveness evidence, and are sent through
  Flask server-sent events only for the local status page. They do not currently
  flow to biometric enrollment or matching, FIDO2, an authorization policy, or
  an SSH broker. The intended future path is RGB-D evidence plus a separate
  biometric match result to an access coordinator, followed by a bound WebAuthn
  assertion, an authorization decision, and only then a scoped SSH grant.
- **Confidence:** confirmed for current repository behavior and the standard
  WebAuthn data and signature boundary. The face-embedding algorithm, protected
  template construction, biometric thresholds, precise evidence digest schema,
  FIDO authenticator and TPM assurance requirements, and final policy remain
  unselected design decisions.
- **Security implication:** Treating a synthetic-media feature or simple depth
  measurement as identity would create false identity assurance. Treating a raw
  SHA-256 embedding digest as a matcher would reject genuine recaptures, while
  exposing stable biometric-derived values can introduce privacy and linkage
  risks. Allowing the browser to assert an unbound `passed` value would permit
  evidence substitution. The coordinator must enforce server-side subject,
  request, capture, freshness, and one-use challenge bindings.
- **Follow-up:** Define the enrollment authority and recovery path; select and
  evaluate a dedicated face-embedding and protected-template scheme; define a
  canonical `BiometricResult` and digest purpose; decide whether `embedded in
  authenticatorData` is a literal custom-authenticator requirement or means
  cryptographically bound to the WebAuthn assertion; and specify policy inputs
  before implementing the biometric or FIDO2 layers.

# Modular architecture and SSH integration boundary

## Current flow

Browser local account login -> authenticated capture session -> Python-owned
RealSense RGB-D source -> independent LiteRT media and depth-liveness paths ->
server-sent status updates -> informational browser result.

The application layer owns capture lifecycle. The model only produces a label and
model version. Evidence policy produces `collecting`, `flagged`, or
`below_threshold`, never an authorization decision. Account identity and future
SSH actions do not belong inside inference code.

Keeping these as Python modules initially makes tests and deployment simple.
Independent services can be introduced later if scaling requires them; doing so
now would add network contracts and distributed state without a demonstrated need.

## Current prototype architecture

The signed-in browser is a control and status surface only. Selecting **Start
camera check** creates a server capture and starts one Python background worker.
That worker owns the complete local media path:

```text
Local camera device
    -> RealSense synchronized color + depth frames
    -> align depth to RGB
    -> RGB --------> LiteRT .tflite inference -> rolling 75-sample media policy
    -> RGB + depth -> face-depth geometry ----> temporal liveness policy
    -> RGB + colorized depth + both results -> side-by-side OpenCV preview
    -> one server-sent event stream to the browser
```

OpenCV opens one native window with RGB/LiteRT status on the left and aligned,
colorized depth/liveness status on the right. The preview is not sent to the
browser. Pressing Q or Esc in that window,
selecting **Stop** in the browser, or signing out stops the worker and releases
the camera. Leaving the page makes a best-effort cleanup request; capture expiry
is the fallback if navigation interrupts it.

The first 75 predictions fill the evidence window; they do not end the check.
Python continues inference, and each later prediction evicts the oldest label
before recalculating `flagged` or `below_threshold`. The camera and preview remain
active until stop, logout/navigation cleanup, capture expiry, or a camera/model
failure. The bounded deque keeps memory use fixed while the monitor runs.

There is no per-frame HTTP endpoint, browser camera permission, canvas encoding,
or JPEG upload. Frames remain transient Python/OpenCV objects and are not saved.
The browser receives small JSON state messages over one EventSource connection.
This removes transport overhead from the inference path without introducing the
Roboflow InferencePipeline package.

The current topology is intentionally local: `pyrealsense2` owns the D435 and
Flask binds to loopback. OpenCV renders SDK-provided NumPy arrays but does not open
a second camera handle.
If Flask later runs on a remote server, this design would inspect the server's
camera rather than the authenticating user's camera. A remote deployment needs a
defined trusted endpoint agent or browser/WebRTC capture boundary; changing only
the bind address would be incorrect and unsafe.

## Future PAM workflow (proposed, not implemented)

1. Authenticate a local account, then eventually an external identity provider.
2. Request a specific SSH host, OS principal, purpose, and duration.
3. Collect required verification evidence, bound to that account and request.
4. Evaluate authorization using identity, target allowlists, requested privilege,
   evidence freshness, and any approval requirements.
5. An SSH broker issues a narrowly scoped, short-lived credential only after an
   explicit authorization decision. Choose certificate vs. brokered-session
   architecture separately. The web/inference modules must not hold a CA key.
6. Record decisions and lifecycle events without recording passwords, private
   keys, raw camera frames, or unnecessary biometric data.

## Prototype limitations and validation needs

- Python owns the camera, but RealSense SDK access does not prove sensor integrity,
  freshness, or resistance to virtual-camera and process-level injection.
- The depth check rejects repeatedly planar face regions and requires a
  move-closer/return sequence. These heuristics are uncalibrated and do not claim
  resistance to 3D masks, injected depth, replayed framesets, or a compromised host.
- An authenticated browser session can trigger the camera attached to the Flask
  host. Loopback binding and operator control are required for this prototype.
- Threshold and class mapping follow the capstone; training preprocessing and
  measured false-positive/false-negative behavior need labeled evaluation.
- Local accounts use hashed passwords and operator provisioning. External IdP,
  MFA, login throttling, durable session revocation, and audit persistence are
  future work. Flask signed cookies are not centrally revocable on logout.
- Evidence and camera-run state exist only in process memory. Do not deploy
  multiple workers before extracting shared state and defining camera ownership,
  ordering, and concurrency behavior.
- A process-generated signing key makes sessions invalid after restart. This is
  a local loopback prototype, not an externally deployed PAM service.
- Automated checks can validate geometry, state transitions, and preview
  composition, but physical D435 alignment, depth quality, OpenCV GUI behavior,
  and end-to-end inference require a manual local run.

## Extension checklist

To add a model, implement `FrameClassifier.classify(rgb_frame) -> Prediction`,
return a stable version identifier, and raise on failure. Inject it into
`create_app`. To change evidence thresholds, configure `WINDOW_SIZE` and
`FAKE_THRESHOLD`. To add identity matching, introduce a separate evidence
contract; do not reinterpret the `real` media label as an enrolled-identity match.
Depth `live` evidence is likewise separate from identity matching and authorization.

## Depth-liveness check

`RealSenseFrameSource` is the only RealSense SDK owner. It requests synchronized
640x480 color and depth at 30 fps, aligns depth to color, and returns an SDK-free
`RGBDFrame`. `DepthLivenessAnalyzer` detects the largest frontal face, measures
valid depth inside an elliptical face region, removes a fitted depth plane, and
requires at least 12 mm of residual relief for a candidate. The accepted median
distance range is 0.3-1.5 m.

`DepthLivenessPolicy` requires five candidate observations plus an active depth
challenge: move at least 5 cm closer, then return at least 4 cm. Five consecutive
planar observations produce `spoof_suspected`; 25 consecutive unusable observations
produce `unavailable`. These constants are prototype defaults and must be calibrated
against labeled live, print, display, mask, lighting, distance, and injection tests.

## CNN model check

The application uses one injected CNN classifier. The browser starts a capture
without a model choice; requests containing a model-selection field are rejected.
Every new capture has a fresh evidence window. Model or camera failures produce a
failed pipeline state without adding fabricated evidence. The classifier protocol
remains replaceable for tests and future CNN upgrades. Frame shape/type validation
remains independent of LiteRT execution.

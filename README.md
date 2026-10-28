# ZTA PAM System Code

## Implemented

Small prototype to prove use case.
Local password accounts, browser start/stop controls, a Python-owned Intel
RealSense RGB-D pipeline, replaceable video classification, depth-liveness
evidence, and per-capture evidence windows. No
conference rooms, WebRTC signaling, Socket.IO, audio initialization, or peer
connections are needed. There is no raw-frame storage. Capture sessions expire
after five minutes.

Media evidence does not establish identity or grant access to anything yet.

## Run locally

For a fresh installation:

On Mac:
```sh
python3.12 -m venv .venv-inference
.venv-inference/bin/python -m pip install -r requirements-inference.txt
```

On Windows:
```sh
py -3.12 -m venv .venv-inference
.\.venv-inference\Scripts\python.exe -m pip install -r requirements-inference.txt
```

Use Python 3.12 to ensure compatibility. From this folder, use the inference
environment's interpreter explicitly:

Virtual environments retain the path to the Python installation that created
them. If an existing environment reports `No Python at ...`, install Python 3.12
and recreate `.venv-inference` with the fresh-install commands above.

On Mac:
```sh
.venv-inference/bin/python -m flask --app zta.web:create_app create-user (insert name here)
.venv-inference/bin/python -m zta
```

On Windows:
```sh
.\.venv-inference\Scripts\python.exe -m flask --app zta.web:create_app create-user (insert name here)
.\.venv-inference\Scripts\python.exe -m zta
```

The first command prompts for a password. Connect the Intel RealSense D435 to a
USB 3 port, then open http://127.0.0.1:8083, sign in, and select **Start camera
check**. Python opens synchronized 640x480 RGB and depth streams through
`pyrealsense2`; the browser does not request camera or microphone access. One
OpenCV window shows RGB/LiteRT output and aligned depth/liveness side by side.
Follow its prompt to move about 5 cm closer and then return to the starting
position. Press **Q** or **Esc** in the preview, or select **Stop** in the browser,
to end the check. Once the first 75 predictions are collected, inference
continues with a rolling 75-frame window: each new result replaces the oldest.
The camera is released on stop, logout/navigation cleanup, capture expiry, or a
camera/model failure.

If more than one RealSense device is attached, select one by serial number before
starting:

```powershell
$env:ZTA_REALSENSE_SERIAL = 'device-serial-number'
.\.venv-inference\Scripts\python.exe -m zta
```

On macOS/Linux, use `export ZTA_REALSENSE_SERIAL=device-serial-number` instead.
The camera must be available to the Python process. Close RealSense Viewer or any
other process that owns it before starting. This local topology is not a
remote-user camera design.


`requirements-macos-py312.lock.txt` records the earlier macOS/Python 3.12
environment snapshot. Install from `requirements-inference.txt`; the snapshot
predates the RGB-D camera refactor and is not the current installation source.

A random signing key is generated at startup, so restarting logs out existing
sessions. Set `ZTA_SECRET_KEY` through your environment for a persistent key.
Never commit it. Local HTTP uses non-Secure cookies; a future HTTPS deployment
must set `ZTA_SECURE_COOKIES=1` and provide deployment-specific controls.
The development server binds to loopback only.

## Module boundaries

| Module | Responsibility | Replace or test independently |
| --- | --- | --- |
| `zta/domain.py` | Media evidence types and classifier protocol | No Flask, database, or ML imports |
| `zta/media.py` | Synchronized RGB-D frame and source contracts | No RealSense SDK dependency |
| `zta/policy.py` | Rolling-window evidence calculation | Pure logic, configurable window and threshold |
| `zta/service.py` | Capture ownership, expiry, and orchestration | Inject classifier, policy, and clock |
| `zta/camera.py` | RGB-D coordination, sampling, status lifecycle | One Python-owned local camera worker |
| `zta/adapters/` | RealSense capture, RGB validation, LiteRT inference | SDK/runtime boundaries are injectable |
| `zta/liveness/` | Depth geometry observations and temporal challenge policy | Independent from CNN media labels |
| `zta/preview.py` | Side-by-side RGB and aligned-depth rendering | Presentation only; no evidence decisions |
| `zta/accounts.py` | Local account storage and password checks | Replace with an identity-provider adapter |
| `zta/web/` | HTTP, signed-in sessions, CSRF, controls, and status events | App factory accepts test adapters |

This is a modular single-process application. Session storage is bounded and
in-memory; a durable store/worker boundary is required before multi-worker use.
The default policy retains the capstone's 75-frame window and 70% fake threshold.
Python samples immediately, then waits 200 ms after each inference before the next
sample. Seventy-five frames therefore need at least approximately 15 seconds plus
inference and camera time. After that warm-up, the bounded window and status keep
updating until the capture ends. Thresholds are inherited, not calibrated.

## Provenance and remaining work

`models/` contains the retained `.tflite` model assets copied from the original
capstone. The CNN adapter uses Google LiteRT, accepts RGB arrays from OpenCV,
resizes them for the model, and removes global model state;
quantized outputs are dequantized before applying the sigmoid threshold. 
The CNN loads lazily on the first frame. Audio assets remain unused. 
The original capstone application is unchanged.

Depth liveness is a prototype presentation-attack signal. It uses an OpenCV face
region, aligned depth coverage, residual surface relief after removing a fitted
plane, and a move-closer/return challenge. Its thresholds are engineering defaults,
not calibrated biometric performance claims. A `live` result does not establish
identity, sensor integrity, or authorization.

See `docs/architecture.md` for integration boundaries and limitations.

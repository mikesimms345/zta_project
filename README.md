# ZTA PAM System Code

## Implemented

Small prototype to prove use case.
Local password accounts, browser start/stop controls, a Python-owned Intel
RealSense RGB-D pipeline, replaceable video classification, depth-liveness
evidence, CPU-only POS rPPG pulse evidence, and per-capture evidence windows. No
conference rooms, WebRTC signaling, Socket.IO, audio initialization, or peer
connections are needed. There is no raw-frame storage. Capture sessions expire
after five minutes.

Media, depth, and pulse evidence do not establish identity or grant access.
See [rPPG implementation and diagram](docs/rppg.md) for the algorithm, configuration,
future biometric-processing boundary, tests, and Linux/Pi validation checklist.

## Run locally

For a fresh installation:

Python <3.11 REQUIRED.

For installing Python 3.10 on a fresh install, run:

```sh
sudo apt update
sudo apt install -y git curl build-essential libssl-dev zlib1g-dev \
  libbz2-dev libreadline-dev libsqlite3-dev libncurses-dev \
  xz-utils tk-dev libffi-dev liblzma-dev

git clone https://github.com/pyenv/pyenv.git ~/.pyenv
~/.pyenv/bin/pyenv install -s 3.10

cd ~/zta_project
~/.pyenv/bin/pyenv local 3.10
~/.pyenv/bin/pyenv exec python -m venv .venv-py310

source .venv-py310/bin/activate
```

Change the environment for the later instructions as appropriate.

On Mac:
```sh
python3 -m venv .<environment-name>
.venv-inference/bin/python -m pip install -r requirements-inference.txt
```

The macOS dependency uses the community-maintained
[`pyrealsense2-macosx`](https://github.com/cansik/pyrealsense2-macosx)
2.56.5 build, which provides the same `import pyrealsense2` module. Its wheel
requires Apple Silicon and macOS 15 or later. Other Mac configurations need a
separately built compatible SDK; these commands do not cover them. Windows/Linux
use the official `pyrealsense2` package. Verify the import before starting:

```sh
.venv-inference/bin/python -c "import pyrealsense2 as rs; print(rs.pipeline)"
```

Import success does not verify camera access or RGB-D behavior on macOS.
On the tested macOS 26.5.1 host, this build crashes at stream startup after
libusb reports that USB device capture requires the `com.apple.vm.device-access`
entitlement or root privilege. Installation is verified; macOS capture is currently
blocked. Do not run the Flask web server as root to work around this. Use a
Windows/Linux capture host or resolve the SDK's macOS device-access requirements
with a separately reviewed camera execution design.

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
position, then hold still in even lighting for at least eight seconds of pulse
collection. Press **Q** or **Esc** in the preview, or select **Stop** in the browser,
to cancel. Capture ends automatically after 15 seconds of measurement; SDK startup,
pending reads, and consumer cleanup can add wall-clock time. Media, depth, and
pulse outcomes are shown separately. A completed capture is not a successful
verification; slow CNN processing may leave its 75-prediction window incomplete.
The camera is released on deadline, stop, logout/navigation cleanup, capture
expiry, or a camera/model failure. Set `ZTA_CAMERA_PREVIEW=0` for headless use.

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
| `zta/deepfake-detection/domain.py` | Media evidence types and classifier protocol | No Flask, database, or ML imports |
| `zta/deepfake-detection/policy.py` | Rolling-window evidence calculation | Pure logic, configurable window and threshold |
| `zta/deepfake-detection/cnn-service.py` | CNN capture ownership, expiry, and orchestration | Inject classifier, policy, and clock |
| `zta/frame-handler.py` | RGB-D frame/source contracts, coordination, sampling, status lifecycle | Shared frame types and one Python-owned local camera worker |
| `zta/realsense.py` | RealSense RGB-D capture, alignment, and conversion | Camera SDK boundary is injectable |
| `zta/deepfake-detection/` | RGB validation and LiteRT inference alongside CNN contracts and policy | Classifier/runtime boundaries are injectable |
| `zta/liveness/` | Depth geometry/challenge and POS pulse extraction | Independent evidence paths; no identity or access decision |
| `zta/preview.py` | Side-by-side RGB and aligned-depth rendering | Presentation only; no evidence decisions |
| `zta/accounts.py` | Local account storage and password checks | Replace with an identity-provider adapter |
| `zta/web/` | HTTP, signed-in sessions, CSRF, controls, and status events | App factory accepts test adapters |

The hyphenated `zta/deepfake-detection/` package and `zta/frame-handler.py` module
are loaded with `importlib.import_module` in `zta/web/__init__.py`. Modules within
the detection package use relative imports for their shared contracts and policy.
`zta/realsense.py` also loads the frame handler through `importlib` to use its
shared frame types. The frame handler imports its default RealSense source when
the worker creates the source, avoiding a circular import.

This is a modular single-process application. Session storage is bounded and
in-memory; a durable store/worker boundary is required before multi-worker use.
The default policy retains the capstone's 75-frame window and 70% fake threshold.
Depth and CNN analysis now consume independent latest-frame queues with a 200 ms
sampling interval; their processing does not add that interval to rPPG sampling.
Pulse extraction consumes RGB arrivals and device timestamps directly. Capture
has a 15-second measurement deadline; 75 CNN results may not fit on slow hardware.
Thresholds are inherited/research defaults, not calibrated performance claims.

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

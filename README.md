# ZTA PAM System Code

## Implemented

Small prototype to prove use case.
Local password accounts, signed-in browser webcam capture, replaceable video
classification, and per-capture rolling evidence windows. No conference rooms,
WebRTC signaling, Socket.IO, audio initialization, or peer connections are needed.
There is no raw-frame storage. Capture windows expire after five minutes.

Media evidence does not establish identity or grant access to anything yet.

## Run locally

Use Python 3.12 for the TensorFlow environment tested on this machine. From this
folder, the existing `.venv-inference` environment is intended for inference:

```sh
.venv-inference/bin/python -m flask --app zta.web:create_app create-user mike
.venv-inference/bin/python -m zta
```

The first command prompts for a password. Open
http://127.0.0.1:8083, sign in, and select **Start camera check**. Allow camera
access in the browser. Microphone access is not requested.

For a fresh installation:

```sh
python3.12 -m venv .venv-inference
.venv-inference/bin/python -m pip install -r requirements-inference.txt
```

`requirements-macos-py312.lock.txt` records the exact installed versions for
reproducing this macOS/Python 3.12 environment.

A random signing key is generated at startup, so restarting logs out existing
sessions. Set `ZTA_SECRET_KEY` through your environment for a persistent key.
Never commit it. Local HTTP uses non-Secure cookies; a future HTTPS deployment
must set `ZTA_SECURE_COOKIES=1` and provide deployment-specific controls.
The development server binds to loopback only.

## Module boundaries

| Module | Responsibility | Replace or test independently |
| --- | --- | --- |
| `zta/domain.py` | Evidence types and classifier protocol | No Flask, database, or ML imports |
| `zta/policy.py` | Rolling-window evidence calculation | Pure logic, configurable window and threshold |
| `zta/service.py` | Capture ownership, expiry, and orchestration | Inject classifier, policy, and clock |
| `zta/adapters/` | Shared JPEG validation, TFLite inference | Instance-based, injectable replacements |
| `zta/accounts.py` | Local account storage and password checks | Replace with an identity-provider adapter |
| `zta/web/` | HTTP, signed-in sessions, CSRF, and browser capture | App factory accepts test adapters |

This is a modular single-process application. Session storage is bounded and
in-memory; a durable store/worker boundary is required before multi-worker use.
The default policy retains the capstone's 75-frame window and 70% fake threshold.
Sampling waits for each response, so 75 frames need at least approximately 15
seconds plus inference/network time. Thresholds are inherited, not calibrated.

## Provenance and remaining work

`models/` contains the retained model assets copied from the original capstone.
The CNN adapter reuses the original preprocessing and removes global model state; 
quantized outputs are dequantized before applying the sigmoid threshold. 
The CNN loads lazily on the first frame. Audio assets remain unused. 
The original capstone application is unchanged.

See `docs/architecture.md` for integration boundaries and limitations.

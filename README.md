# ZTA PAM webcam prototype

Independent extraction from the capstone application, guided by the
[ZTA PAM project brief](https://github.com/mikesimms345/ZTA_PAM_System/blob/master/docs/brief.md).

## Implemented

Local password accounts, signed-in browser webcam capture, replaceable video
classification, and per-capture rolling evidence windows. No conference rooms,
WebRTC signaling, Socket.IO, audio initialization, or peer connections are needed.
There is no raw-frame storage. Capture windows expire after five minutes.

Media evidence does not establish identity or grant access. SSH is the selected
future protected resource. SSH credential issuance, authorization, biometric
identity matching, explicit liveness challenges, and automated requests for
another check are not implemented. Current results are informational.

## Run locally

Use Python 3.12 for the TensorFlow environment tested on this machine. From this
folder, the existing `.venv-inference` environment is intended for inference:

```sh
.venv-inference/bin/python -m flask --app zta.web:create_app create-user mike
.venv-inference/bin/python -m zta
```

The first command prompts for a password (minimum 12 characters). Open
http://127.0.0.1:8083, sign in, and choose **CNN** or **ViT**, then select **Start camera check**. Allow camera
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
| `zta/adapters/` | Shared JPEG validation, CNN/TFLite and ViT inference | Instance-based, lazy model load; injectable replacements |
| `zta/accounts.py` | Local account storage and password checks | Replace with an identity-provider adapter |
| `zta/web/` | HTTP, signed-in sessions, CSRF, and browser capture | App factory accepts test adapters |

This is a modular single-process application. Session storage is bounded and
in-memory; a durable store/worker boundary is required before multi-worker use.
The default policy retains the capstone's 75-frame window and 70% fake threshold.
Sampling waits for each response, so 75 frames need at least approximately 15
seconds plus inference/network time. Thresholds are inherited, not calibrated.

## Tests

```sh
.venv/bin/python -m unittest discover -s tests -v
node --check zta/web/static/app.js
```

Tests inject classifiers to check evidence aggregation, expiry, capture ownership,
CSRF, account login, input bounds, and unavailable models without heavyweight ML
initialization. Real-model smoke testing is separate from accuracy validation.

Validation on 2026-09-16: 12 automated tests passed; JavaScript syntax check passed;
the actual TFLite model accepted a generated 640×480 JPEG and returned a label.
Its input tensor is `[1, 224, 224, 3]`, output `[1, 1]`. This confirms execution,
not classification accuracy. Physical webcam capture remains a manual check.

## Provenance and remaining work

`ai_detector.py` and `models/` retain the unchanged extraction baseline; the new
application does not import the legacy detector. `SOURCE_MANIFEST.json` records
its hashes. The video adapter reuses its preprocessing and removes global model
state; quantized outputs are dequantized before applying the sigmoid threshold.
The ViT option uses the local MobileViT weights on CPU with PyTorch/Transformers.
CNN uses the existing TFLite video model. Both load lazily, only when selected.
Switching models stops capture and resets evidence; press Start for the new model.
Audio assets remain unused.

The GitHub design documents were read on 2026-09-16 and copied under `docs/`.
Local decisions and session notes extend those copies; nothing was pushed to
GitHub. See `docs/architecture.md` for integration boundaries and limitations.

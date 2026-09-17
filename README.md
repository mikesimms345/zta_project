# ZTA PAM webcam prototype

Basic Prototype separated from previous capstone work.

## Implemented

Local accounts, signed-in browser webcam capture, replaceable video
classification, and per-capture rolling evidence windows. There is no raw-frame storage. 
Capture windows expire after five minutes. No special access or any privileges is implemented yet.

## Run locally

Use Python 3.12 for the TensorFlow environment. From this
folder, the existing `.venv-inference` environment is intended for inference:

```sh
.venv-inference/bin/python -m flask --app zta.web:create_app create-user mike
.venv-inference/bin/python -m zta
```

The first command prompts for a password (minimum 12 characters). Open
http://127.0.0.1:8083, sign in, and choose **CNN** or **ViT**, then select **Start camera check**. Allow camera
access in the browser. Microphone access is not enabled yet for this prototype.

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

## Module boundaries

| Module | Responsibility | Replace or test independently |
| --- | --- | --- |
| `zta/domain.py` | Evidence types and classifier protocol | No Flask, database, or ML imports |
| `zta/policy.py` | Rolling-window evidence calculation | Configurable window and threshold |
| `zta/service.py` | Capture ownership, expiry, and orchestration | Inject classifier, policy, and clock |
| `zta/adapters/` | CNN/TFLite and ViT inference | Instance-based, easy model replacements |
| `zta/accounts.py` | Local account storage and password checks | Replace with server-side system later |
| `zta/web/` | HTTP, signed-in sessions, CSRF, and browser capture | Secure further with HTTPS later |

This is a modular single-process application. Session storage is bounded and
in-memory. The default policy retains the capstone's 75-frame window and 70% fake threshold.
Sampling waits for each response, so 75 frames need at least approximately 15
seconds plus inference/network time.


## Provenance and remaining work

`ai_detector.py` and `models/` retain the unchanged extraction baseline; the new
application does not import the legacy detector. The video adapter reuses its preprocessing 
and removes global model state; quantized outputs are dequantized before applying the sigmoid threshold.
The ViT option uses the local MobileViT weights on CPU with PyTorch/Transformers.
CNN uses the existing TFLite video model. Both load only when selected.
Switching models stops capture and resets evidence; press Start for the new model.

The GitHub design documents were read on 2026-09-16 and copied under `docs/`.
Local decisions and session notes extend those copies; nothing was pushed to
GitHub. See `docs/architecture.md` for integration boundaries and limitations.

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

### 2026-09-16 — MobileViT adapter

- **Question:** How should the saved ViT model be loaded and preprocessed?
- **Source:** https://huggingface.co/docs/transformers/model_doc/mobilevit and local
  `models/MobileViT/config.json`, `preprocessor_config.json`.
- **Finding:** The local artifact is MobileViT, with REAL/FAKE class mapping.
  Use its saved image processor configuration with the image classification model.
- **Confidence:** confirmed for artifact configuration and documented API.
- **Security implication:** A model type or successful load does not establish accuracy.
- **Follow-up:** Calibrate both backends on labeled webcam samples.

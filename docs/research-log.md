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

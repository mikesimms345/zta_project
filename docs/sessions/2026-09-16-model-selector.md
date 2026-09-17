# 2026-09-16 — CNN / ViT selector

- Added accessible CNN/ViT radio selection above the camera controls. CNN defaults.
- Model choice is validated and bound per capture, independent of other users.
- Switching stops capture and clears evidence; Start begins a fresh check.
- Added a local CPU MobileViT adapter, shared JPEG validation, and runtime
  dependencies. No global backend mode or silent fallback.
- Validation: all 16 automated tests pass, including model routing, evidence reset,
  invalid selection, cross-user isolation, and ViT failure behavior. JavaScript
  syntax check passes. Both actual model adapters classified a generated 640×480
  JPEG successfully. This checks execution, not accuracy or physical webcam behavior.
- Original capstone code and model assets remain unchanged.

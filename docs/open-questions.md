# Open questions

## 2026-11-20 rPPG follow-up

- Target confirmed: on-device RealSense RGB/depth at 30 FPS, Ubuntu or 64-bit Pi
  OS, Pi 5 16 GB development board with an 8 GB deployment target; desired total
  check time 10–15 seconds, NVIDIA optional. CPU-only POS is implemented first.
- Measure whether the actual depth challenge plus eight steady pulse seconds
  fits the 15-second capture schedule on Pi 5; profile CPU, dropped frames,
  thermal throttling, peak RAM and swap. Owner: Mike; status: Open hardware test.
- Validate a CPU-compatible RealSense/Python build on the selected Pi OS image;
  official ARM64 wheels may target JetPack/CUDA. Owner: Mike; status: Open.
- Calibrate POS quality/region agreement and CNN window length on held-out genuine
  and attack data before adding a combined pass or access-policy dependency.
- Decide whether later processing needs a fresh evidence digest, repeatable
  biometric features, or both. Neither is implemented by this pulse MVP.

- macOS RealSense capture is blocked: 2.56.5 crashes after libusb device-access
  denial on macOS 26.5.1; 2.54.2 reports no device. Next action: select a
  Windows/Linux capture host or validate an entitled macOS SDK/camera process
  without granting root to Flask. Owner: Mike; status: Open.

Track questions that need evidence, a decision, or an assigned owner.

| Question | Why it matters | Next action | Owner | Status |
| --- | --- | --- | --- | --- |
| Which identity provider and authentication methods must the system support? | Determines trust boundaries and integration design | Document the intended deployment environment and identity integrations | Mike | Open |
| What privileged actions and resources require just-in-time access? | Defines the initial authorization model | Inventory roles, systems, and access paths | Mike | Open |

## 2026-09-16 updates

- Prototype identity source: local username/password accounts (decided by Mike).
- First protected resource: SSH access (decided by Mike); enforcement is future work.
- Input: live Intel RealSense D435 RGB-D frames. Failed checks should eventually request another check;
  implementation is deferred.
- Define allowed SSH hosts, OS principals, access durations, and approvals.
- Choose SSH certificate issuance or brokered sessions and establish key custody.
- Calibrate the implemented depth-liveness thresholds and movement challenge on
  labeled live, print, display, mask, and injected-frame attacks.
- Validate detector preprocessing/class mapping and calibrate thresholds on labeled
  real and synthetic samples before using results in an access policy.
- Define recheck limits, expiry, terminal outcomes, and audit retention later.

# Idea backlog

Capture ideas before they are validated. Link supporting evidence when it exists.

## Template

### Idea title

- **Problem:**
- **Who it helps:**
- **Why it may work:**
- **Security assumptions and risks:**
- **Next validation step:**

### SSH-bound verification evidence

- **Problem:** A future SSH request needs fresh evidence associated with the right user.
- **Who it helps:** Privileged operators and administrators.
- **Why it may work:** Bind a short-lived evidence record to an authenticated access request.
- **Security assumptions and risks:** Browser media can be forged/replayed; a REAL
  classification does not establish identity. Credential issuance needs independent policy.
- **Next validation step:** Specify identity/liveness requirements and adversarial test cases.

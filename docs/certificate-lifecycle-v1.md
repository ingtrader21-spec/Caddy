# Certificate Lifecycle v1

## Lifecycle model

```text
ISSUE
→ STORE
→ USE
→ RENEW
→ ROTATE
→ REPLACE / REVOKE
```

## Repository policy

- Private keys, ACME account data, and credential material are never committed to Git.
- Runtime values remain outside Git and are supplied by the deployment environment.
- Example values intentionally fail closed so no live or routable configuration is implied.

## Operational requirements

- certificate issuance must be explicit and environment-controlled
- storage must be protected and separate from source code
- usage must be bound to the approved public host
- renew and rotate operations must be verified before activation
- replacement or revocation must preserve no silent fallback to insecure exposure

## Runtime certification state

Certificate issuance, renewal, trust-chain validation, and live TLS handshake remain `RUNTIME CERTIFICATION PENDING` because they require actual runtime evidence rather than static source inspection.

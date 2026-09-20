# TLS Contract v1

## Canonical TLS posture

Caddy is the secure ingress and edge TLS authority. Kong remains the API gateway behind it. Caddy does not replace the gateway or identity layer.

## Required behaviors

- terminate TLS at the edge for approved public hosts
- prefer secure, supported Caddy defaults
- avoid custom cryptography churn unless required by a governed runtime policy
- reject public plaintext exposure without an explicit and reviewed internal-only reason
- preserve certificate trust and verification for upstream HTTPS and mTLS flows
- never disable TLS verification to make an upstream appear operational

## Listener categories

| Category | Allowed state | Note |
| --- | --- | --- |
| HTTPS | permitted | required for public host exposure |
| HTTP → HTTPS | permitted for redirect workflows | no plaintext public default |
| INTERNAL HTTP | permitted only for trusted internal listeners | not public ingress |
| DISABLED | permitted | public access intentionally closed |

## Upstream classification

| Upstream type | Requirement |
| --- | --- |
| HTTP | plain upstream is acceptable only for internal/test or explicitly reviewed infrastructure |
| HTTPS | hostname validation, SNI, and trust source must be explicit |
| mTLS | client certificate requirement, trust chain, and policy must be explicit |

## Runtime notice

Real certificate issuance, live renewal, handshake verification, and certificate trust-chain validation remain runtime certification tasks and cannot be proven from Git alone.

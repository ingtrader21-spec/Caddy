# n8n Community editor protection

Status: **prepared in source; not applied**.

n8n Community Edition does not depend on n8n Enterprise SSO in this design. The editor path is protected by a two-gate boundary:

1. Caddy terminates HTTPS and proxies only to a private oauth2-proxy listener.
2. oauth2-proxy uses Keycloak OIDC authorization code flow with PKCE S256 and requires either `n8n_operator` or `n8n_admin`.
3. n8n's native owner login remains required after edge authorization. The local owner is a dedicated service-owner identity, not a personal account.

The source route deliberately contains no direct n8n upstream. oauth2-proxy owns the private n8n upstream and all OIDC client secrets. Those secrets must be rendered from OpenBao at runtime and must never be added to this repository, workflow JSON, or GitHub configuration.

## Required runtime gates

- Keycloak issuer is exactly `https://auth.codestra.co/realms/codestra`.
- The oauth2-proxy client uses authorization code flow, PKCE S256, secure cookies, exact redirect URIs, and role checks for `n8n_operator` or `n8n_admin`.
- Caddy can reach only the private oauth2-proxy listener for the editor host.
- The n8n editor port is not host-published and is not reachable directly from the public edge.
- Spoofable identity headers are stripped before the request reaches oauth2-proxy.
- Access logs redact authorization, cookies, OAuth code, state, and session-state values.
- Native n8n owner authentication and session revocation are tested independently.

No reload, deployment, DNS change, Keycloak client creation, or secret mutation is authorized by this source change.

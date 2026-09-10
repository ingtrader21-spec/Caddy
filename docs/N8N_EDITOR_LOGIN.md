# n8n editor login templates

`deploy/community-n8n/compose.security.yaml` loads the Codestra login and error templates from the N8N repository through oauth2-proxy's supported template interface. The page starts the existing Keycloak authorization-code flow with PKCE; native n8n authentication remains in place.

## Runtime inputs

Set `N8N_LOGIN_TEMPLATE_DIR` to the absolute `orbit/login` directory of the approved, revision-verified N8N checkout. The container mounts it read-only at `/etc/oauth2-proxy/templates`; `create_host_path: false` makes a missing directory an error. Both `sign_in.html` and `error.html` must be present and readable. Keep this directory immutable for the running release.

Use an immutable `OAUTH2_PROXY_IMAGE_DIGEST`. The companion N8N rendering test verifies v7.15.2 at `sha256:aa0bd8dd5ab0c78e4c91c92755ad573a5f92241f88138b4141b8ec803463b4fd`. Other digests require the same template test before use. Existing image, runtime-secret and Compose base-service inputs still apply. Use `EDITOR_HOST=n8n.codestra.agency` in production and `n8n-staging.codestra.agency` in staging, matching the reviewed Keycloak callback allowlist.

The Keycloak realm remains the sole identity issuer. oauth2-proxy requires an email-validation setting even when roles authorize access. `--email-domain=*` satisfies that startup requirement while the existing `n8n_operator`/`n8n_admin` checks determine workspace eligibility. An email address alone does not grant editor access. The gateway does not pass bearer credentials to n8n.

The provider button remains visible; login errors hide debug details. Cookies are explicitly Secure, HttpOnly and SameSite=Lax. The gateway filesystem and templates are read-only, capabilities are dropped and privilege escalation is disabled. The listener remains bound to host loopback.

## Apply and verification

`bash scripts/validate-ci.sh` validates the source contract and Caddy configuration. The N8N repository's `scripts/test_editor_login.py` checks actual gateway rendering and the anonymous authentication boundary with synthetic credentials and no network.

Apply through the existing reviewed deployment and certification path only after the Keycloak client, Codestra theme image, root-owned gateway secret files and gateway are ready. Route the editor through the gateway and verify the signed-in role path plus native n8n login before recording success. Retain the current staff-network route until those prerequisites pass. Restore that prior route if the new path fails; do not route the public editor directly to n8n.

As of 2026-09-10 the live client, gateway and credentials were absent. This change is prepared source, not a Caddy reload or runtime certification. It does not change workflow activation or database state.

# n8n Community editor protection

The canonical editor host is `automation.codestra.co`. Caddy first applies the verified administrator source ranges in `CADDY_EDITOR_ADMIN_CIDRS`, blocks test-webhook and owner-bootstrap paths, removes spoofable identity headers, and forwards every accepted request to Kong. Kong owns the Keycloak authorization-code browser flow and session policy; n8n's native owner authentication remains enabled behind the gateway.

The public chain is:

```text
browser → Caddy → Kong → private n8n editor
```

Caddy never routes this hostname directly to n8n, never mints identity, and does not remove the Authorization header before the Kong hop. Access logs use `sanitized_access_log`, which deletes Authorization, cookies, API keys, OIDC codes/state/session material, and response cookies.

The `deploy/community-n8n/` overlay remains a defense-in-depth workload policy for node restrictions, internal networks, outbound allowlisting, and protected credentials. It is not a competing public edge authority. Activation still requires matching Kong and Keycloak contracts, verified source CIDRs, private upstream reachability, and wrong-source/wrong-role denial evidence.

# Upstream Registry v1

## Canonical upstream inventory

| Upstream ID | Environment | Protocol | Host | Port | Health path | TLS expectation | Authority |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `CADDY_KONG_UPSTREAM` | shared | HTTP reverse proxy | `127.0.0.1` or reviewed deployment listener | `8000` | Kong route-specific health policy | explicit if TLS-backed | Kong-owned gateway |
| `CADDY_LEGACY_API_UPSTREAM` | transitional | HTTP | `127.0.0.1` | `18101` | migration-only | no production authority | historical fallback |
| `CADDY_REALTIME_UPSTREAM` | transitional | HTTP | `127.0.0.1` | `18102` | migration-only | no production authority | historical fallback |
| `CADDY_N8N_OAUTH2_PROXY_UPSTREAM` | community editor | HTTP | `127.0.0.1` | `4180` | oauth2-proxy health | internal-only | gateway provider |
| `CADDY_GRAFANA_UPSTREAM` | observability reference | internal-only | `127.0.0.1` | `18003` | runtime-specific | no public listener | repository validation reference |
| `CADDY_SUPERSET_UPSTREAM` | observability reference | internal-only | `127.0.0.1` | `18088` | runtime-specific | no public listener | repository validation reference |
| `CADDY_OPENBAO_UPSTREAM` | observability reference | internal-only | `127.0.0.1` | `18200` | runtime-specific | no public listener | repository validation reference |

## Policy

- No unexplained hard-coded topology is accepted.
- No production path is allowed to bypass the Kong boundary for routes already represented in the reviewed Kong contract.
- Any fallback listener must be explicitly marked transitional and removed when route parity is proven.

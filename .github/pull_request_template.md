## Caddy change summary

Describe the routing, TLS, upstream, header, logging, or controller change.

## Promotion

- Source branch/environment:
- Target branch/environment:
- Reviewed commit SHA:

## Affected hosts/routes/upstreams

- Hosts:
- Routes:
- Upstreams:
- Authentication/API/WebSocket impact:

## Validation evidence

- [ ] `caddy fmt` clean
- [ ] `caddy validate` passed
- [ ] No credentials/private keys/runtime state committed
- [ ] CI validation passed
- [ ] Rollback impact reviewed

## Staging evidence (required before production)

- [ ] DNS/host routing checked
- [ ] TLS/HTTPS checked
- [ ] Expected redirects checked
- [ ] Upstream health checked
- [ ] WebSocket/streaming checked when applicable
- [ ] Authentication boundary checked when applicable
- [ ] Relevant smoke tests passed

## Production deployment evidence

Complete only after deployment:

- Deployed commit:
- Deployment time:
- Backup path/reference:
- Caddy active after reload:
- Post-deploy smoke result:
- Rollback required: yes/no

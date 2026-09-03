# Exact-command production validation

`scripts/caddy_readonly_validator.py` is the canonical fixed-target validator for the shared production Caddy service. It accepts no arguments, reads only the fixed `/etc/caddy` source, invokes only fixed `caddy validate`, `caddy adapt`, and `systemctl is-active caddy.service` commands, and emits sanitized structural JSON rather than raw configuration.

It fails closed when the service or configuration is invalid, required Authorization/API-key log deletion is missing, adapted JSON is malformed, or an upstream cannot be represented as a plain host and optional port.

This repository change does not install the validator, modify SSH, grant sudo, or authorize reload. Installation requires a separately reviewed protected release that pins the file checksum and exposes exactly this no-argument command through the existing bounded operator. Evidence storage must be root-owned mode `0600`.


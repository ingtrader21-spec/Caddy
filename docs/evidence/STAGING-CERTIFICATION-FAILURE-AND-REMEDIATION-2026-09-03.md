# Staging certification failure and remediation evidence

Date: 2026-09-03

## Failed staging source run

Staging source SHA `d5b6c4b1f3784f4563e83904584c92a182ed4bd9` completed the following gates successfully before the final failure:

- exact source and configuration validation;
- immutable image build and OCI identity checks;
- non-root privileged-port proof;
- TCP 80/443 and UDP 443;
- HTTP/2 and a real HTTP/3 request;
- TLS, redirects, HSTS, request limits, and WebSockets;
- Kong handoff, Keycloak behavior, mTLS, access denial, upstream reachability, and credential redaction canary;
- HIGH and CRITICAL vulnerability scan.

The job failed closed during rollback rehearsal because the disposable previous-image validator had no writable `/var/log/caddy` path. The same run showed that hosted-runner access-log files could be unreadable by the invoking user, which meant shell negation around `grep` was not sufficient proof of secret absence.

## Remediation

The rollback rehearsal now provisions disposable non-root tmpfs paths for `/run/caddy`, `/tmp`, `/var/log/caddy`, `/data`, and `/config` while keeping networking disabled, the baseline digest unchanged, and PKI mounts read-only.

Both hosted and bounded-staging redaction gates now:

1. require access-log files to exist;
2. require every generated file to be readable;
3. normalize ownership only inside the disposable evidence directory when privileged access is available;
4. distinguish `grep` result 0 (secret found), 1 (secret absent), and all error states;
5. fail on missing logs, unreadable logs, or search errors.

No production image, baseline SHA or digest, Caddy process, DNS, firewall, SSH, certificate, secret, unrelated workload, or traffic allocation was changed.

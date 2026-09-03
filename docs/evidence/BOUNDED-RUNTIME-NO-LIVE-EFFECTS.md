# Bounded runtime no-live-effects boundary

The staging phase is isolated to a dedicated container network and host loopback. The production phase performs read-only validation of the existing Caddy container. Neither phase changes public routing, DNS, firewall policy, SSH access, certificates, or unrelated workloads. No application mutation endpoint is exercised.

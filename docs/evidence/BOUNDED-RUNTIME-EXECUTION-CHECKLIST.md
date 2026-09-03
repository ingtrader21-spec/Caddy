# Bounded runtime execution checklist

- [ ] Exact protected production SHA recorded.
- [ ] Exact immutable image digest recorded.
- [ ] Exact configuration SHA256 recorded.
- [ ] Cosign signature verified.
- [ ] Source attestation verified.
- [ ] Staging runner label available.
- [ ] Staging protected paths available and root-owned.
- [ ] Bounded staging runtime passed.
- [ ] Staging evidence artifact uploaded.
- [ ] Production read-only runner label available.
- [ ] Production protected mTLS paths available and root-owned.
- [ ] Live fixed-target readback passed before probes.
- [ ] Read-only production probes passed.
- [ ] Live fixed-target readback passed after probes.
- [ ] Pre/post live evidence is byte-identical.
- [ ] Production evidence artifact uploaded.
- [ ] No public traffic, DNS, firewall, SSH, or unrelated workload change occurred.

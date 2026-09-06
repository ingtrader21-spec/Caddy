# Caddy platform-edge certification contract

Issue [#105](https://github.com/appolon1908-hue/Caddy/issues/105) requires a production integration authority that binds the Caddy TLS/WSS edge to Kong, Keycloak, Middleware, and the immutable runtime evidence chain without moving Caddy feature ownership back into the historical platform repository.

## Authority split

- `appolon1908-hue/Caddy` remains the principal source for Caddy configuration and edge behavior.
- `appolon1908-hue/codestra-production-platform` owns cross-workload integration, release, runtime reconciliation, rollback, and certification evidence.
- `appolon1908-hue/Kong` owns API authentication, authorization, rate and route policy.
- `appolon1908-hue/Keycloak` owns token issuance.
- `appolon1908-hue/Middleware-` owns business commands, writes, and provider-effect boundaries.

New Caddy routes and configuration must therefore be implemented and reviewed in this repository. The platform repository may consume the immutable lock and evidence, but it must not become a second deployable Caddy source.

## Squash-stable configuration lock

`contracts/platform-edge-certification.v1.json` pins the reconciled deployable configuration using identities that survive squash merges and branch promotion:

```text
configuration Git tree: 215fbe973e0a60a33fb7a4e5f4dcc0f62a620de7
configuration SHA-256:  7cd21ce91bb11838687412734cf65318ed04b0ac2b83b063a2f7cfcb58cb7347
algorithm:              codestra.config-tree-sha256.v1
identity policy:        git-tree-and-content-digest-survive-squash
```

The digest uses `scripts/hash_config_tree.py`: sorted relative file names and exact bytes beneath `config/`, excluding only the top-level `private/` runtime-mount placeholder. The validator recomputes that digest and requires the current `HEAD:config` Git tree to equal the reviewed tree object.

A feature-branch commit SHA is deliberately not part of the configuration identity. Squash merging creates a new commit and may delete the feature branch, while the accepted configuration tree and deterministic content digest remain unchanged. A configuration change therefore fails CI until the tree and digest lock are intentionally regenerated and reviewed, but normal squash promotion does not invalidate an unchanged lock.

## Enforced certification surface

The contract requires all of the following before production can be certified:

- hostname and TLS inventory;
- renewal monitoring and certificate-expiry readback;
- private upstream identity;
- strict Caddy-to-Kong-to-Middleware forwarding with no generic fallback;
- health, readiness, version, source, image, and configuration readback;
- deterministic fail-closed behavior for unavailable or uncontracted upstreams;
- route parity and explicit exclusion of unimplemented Middleware routes;
- isolated `staging-readonly` proof;
- immutable backup and rollback evidence;
- the same image and configuration digest through staging and the production read-only canary.

The source validator checks that the existing runtime scripts still contain the required certificate-expiry, route-denial, mTLS, log-redaction, exact-version, zero-mutation, zero-provider-effect, and rollback evidence controls.

## Safety boundary

This source contract does not deploy or reload Caddy. It does not authorize DNS, TLS, firewall, SSH, public-traffic, application-write, provider, email, SMS, or PSTN mutation.

Production canary authority remains limited to `GET` and `HEAD`, at no more than one percent, using the exact staging-certified image and configuration digests. Runtime certification remains required and `productionCertified` remains `false` until protected evidence proves otherwise.

## Validation

The contract is enforced by:

```bash
python3 scripts/validate_platform_edge_certification.py
python3 -m unittest tests.test_platform_edge_certification
```

It is also invoked from `scripts/validate-ci.sh`, so it runs for both exact source and synthetic merge-result validation. Regression tests reject reintroducing commit-ancestry coupling into the configuration lock.

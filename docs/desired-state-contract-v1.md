# Desired State Contract v1

## Authority

The canonical deployable desired state is the reviewed repository tree rooted at `Caddyfile`, including the imported files under `snippets/` and `sites/`, the non-secret runtime variable contract, and the machine-readable route/security contracts under `config/`.

No generated runtime JSON, manually edited server file, or historical production-platform copy is an independent production authority.

## Identity

A candidate is identified by Git SHA, environment, configuration SHA-256, desired-state version, and UTC generation timestamp. Runtime secrets are injected externally and never become plaintext evidence.

## Determinism

The same source, environment, and reviewed runtime contract produce the same desired state. Environment values may be supplied at deployment time, but their names and safety constraints are source-controlled.

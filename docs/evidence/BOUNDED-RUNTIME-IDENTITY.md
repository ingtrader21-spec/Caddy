# Bounded runtime immutable identity

Both runtime phases consume the same tuple:

```text
source_sha
image_digest
config_sha256
```

The production read-only job receives this tuple only from the successful bounded staging job. It must not rebuild, retag, or substitute any component.

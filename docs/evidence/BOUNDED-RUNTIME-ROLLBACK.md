# Bounded runtime rollback note

The production read-only canary does not alter the live image or configuration, so a successful or failed canary requires no live restore. The previous signed image remains the activation rollback tuple. The staging candidate is always deleted by the workflow trap.

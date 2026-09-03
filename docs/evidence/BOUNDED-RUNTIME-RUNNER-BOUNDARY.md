# Bounded runtime runner boundary

Only runners bearing the exact `caddy-staging-readonly` or `caddy-production-readonly` labels may execute their respective jobs. Hosted runners are used only for repository and image validation, never as a substitute for environment-bound runtime evidence.

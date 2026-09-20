# Timeout Profiles v1

## Required profiles

### STANDARD_API
- short enough to protect the edge from hung upstream calls
- suitable for ordinary request/response API patterns

### LONG_RUNNING_API
- used for tasks that legitimately exceed normal API request latency
- remains explicit and not silently inherited from the default API timeout

### WEBSOCKET
- separate from generic HTTP timing assumptions
- long-lived upgrade traffic must not be forced into a short API timeout

### SSE_STREAM
- avoids buffering and overly aggressive timeouts
- keeps streaming responses alive without treating them as generic sync HTTP

### HEALTH
- health and readiness endpoints must be explicit and lightweight
- they should reflect the actual health contract rather than generic proxy latency

## Policy

The repository rejects the anti-pattern of one universal timeout being applied to every traffic class.

# Error Contract v1

## Required safe behavior

The edge must respond safely for:

- unknown host
- unknown path
- unsupported method where applicable
- upstream unavailable
- timeout
- maintenance
- request too large

## Forbidden leakage

The edge must not expose:

- container names
- private IPs
- internal ports
- stack traces
- secret configuration
- internal route topology

## Fail-closed policy

When the route or upstream is missing, invalid, or unhealthy, the edge must fail closed instead of silently routing to a less trusted or hidden backend.

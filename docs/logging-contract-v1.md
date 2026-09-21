# Logging Contract v1

## Purpose

Caddy emits operational evidence that is useful to operators without exposing authorization material or business-state data.

## Required fields

The canonical logging contract prefers:

- timestamp
- level
- host
- method
- path
- status
- duration
- upstream
- request_id
- correlation_id

## Redaction rules

The edge must never persist:

- `Authorization`
- `Proxy-Authorization`
- `Cookie`
- `Set-Cookie`
- `access_token`
- `refresh_token`
- `id_token`
- `password`
- `secret`
- `client_secret`
- `api_key`

Query strings that carry these values, including callback material such as `token`, `code`, `state`, or `session_state`, must be stripped or redacted before the event becomes persistent evidence.

## Repository policy

The existing Caddy site logs already redact Authorization and cookie material; Mission 4 formalizes that into an operational contract rather than leaving it implicit.

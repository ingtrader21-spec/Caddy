# Metrics Contract v1

## Purpose

Caddy metrics should support operational incident response without exposing user-level identifiers or unbounded query values.

## Repository implementation status

The current repository does not configure a Caddy metrics endpoint or custom
metric labels. This contract is the source-level boundary for a future
runtime integration; it does not claim that metrics are currently emitted.

## Recommended low-cardinality metrics

- request count
- response status class
- request duration
- TLS failures
- upstream failures
- active connections
- reload failures

## Prohibited labels

The metric contract must avoid labels containing:

- user ID
- token
- full arbitrary URL
- customer ID
- correlation ID
- unbounded query values

## Policy

Metrics remain edge-scoped. Monitoring systems may consume them, but they do not become part of Caddy’s routing or business control authority.

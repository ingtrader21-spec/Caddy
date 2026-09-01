# Codestra Production Readiness Gate — Caddy

Status: NOT PRODUCTION CERTIFIED

Governed by `Infustruction-repo/CODESTRA_PRODUCTION_READINESS_WAVE_20260901.md`.

Required: exact-head config validation; Critical=0; High=0; TLS/security headers; Keycloak-protected administrative routes; correct Kong/Middleware routing; no accidental direct backend/provider exposure; rate limits where applicable; immutable config/source identity; staging route/TLS smoke tests; rollback and production read-back.

Do not change SSH access or expose private service/admin ports.

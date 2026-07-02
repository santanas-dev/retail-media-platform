# ADR-003: Device Identity and Authentication

**Status:** Accepted
**Date:** 2026-07-02
**Phase:** 0 (Architecture Lock)
**Deciders:** Sergey Paschenko (project owner), Hermes Agent

## Context

ТЗ v2.5 §10 requires device registration via one-time `device_code` + `hardware_fingerprint`, issuance of certificate/key, and authentication via mTLS or short-lived token. JWT/access token MUST NOT appear in URLs (§9.1). The `rmp_rewrite_starting_decisions.md` confirms: mTLS is not yet confirmed, so start with device onboarding code + device secret/certificate material + short-lived JWT session, keeping mTLS-ready interfaces.

## Decision

**Device code onboarding + rotated device secret → short-lived JWT session. mTLS-ready but not required for Phase 1–3.**

### Device Lifecycle

```
1. REGISTRATION (one-time)
   Operator generates device_code in Admin UI
   → Device boots, sends: device_code + hardware_fingerprint + device_type
   → Server validates, issues: device_id + device_secret (+ optional certificate)
   → Device stores credentials locally (encrypted)

2. SESSION ESTABLISHMENT (periodic)
   Device sends: device_id + HMAC(device_secret, nonce) + nonce
   → Server validates, issues: short-lived JWT access_token (15 min)
   → Device uses JWT in Authorization: Bearer header for all subsequent requests

3. JWT REFRESH
   Before expiry, device sends: refresh_token (issued alongside JWT)
   → Server rotates: new JWT + new refresh_token
   → Old refresh_token invalidated

4. TOKEN REVOCATION
   Admin can revoke device via UI → device_secret invalidated
   → All active JWTs expire within 15 min (short TTL)
```

### JWT Claims (device)

```json
{
  "sub": "<device_id>",
  "device_code": "<human-readable code>",
  "store_id": "<store_id>",
  "channel_type": "KSO|ANDROID_TV|PRICE_CHECKER|ESL|LED",
  "capability_profile": "<profile_code>",
  "iat": 1719000000,
  "exp": 1719000900,
  "iss": "rmp-device-gateway"
}
```

### Security Properties

| Property | Mechanism |
|----------|-----------|
| Token not in URL | JWT in `Authorization: Bearer` header only |
| Device identity proof | HMAC(device_secret, nonce) during session establishment |
| Secret rotation | Admin-triggered; new secret issued, old invalidated |
| Short-lived access | JWT TTL = 15 min; refresh token TTL = 24h |
| Replay protection | Nonce checked server-side (Redis TTL = 5 min) |
| mTLS readiness | Interfaces accept client certificate; adapter layer can enforce later |

### What is NOT implemented now (deferred)

- Full PKI certificate issuance and rotation
- Hardware-backed keystore (TPM/secure enclave)
- Certificate revocation lists (CRL/OCSP)
- Mutual TLS enforcement at reverse proxy

### Migration Path to mTLS

1. Phase 1–3: device_code + device_secret + JWT (this ADR)
2. Phase 5 (production hardening): if corporate PKI is available, upgrade Device Gateway to require mTLS
3. Migration: deploy mTLS as additional verification alongside JWT; once verified, deprecate device_secret-based auth

## Consequences

- **Positive:** Works without corporate PKI approval; deployable today; mTLS-ready for future.
- **Negative:** Device secret management requires secure storage; JWT refresh adds complexity vs perpetual token.
- **Risk:** If mTLS is mandated later, migration effort is moderate (adapter layer + reverse proxy changes only).

## References

- TZ v2.5 §10 (Device Management), §9.1 (Player Requirements), §14 (Security)
- `rmp_rewrite_starting_decisions.md` — Device identity decision
- `rmp_enterprise_architecture_review.md` — Device auth: mTLS or certificate + JWT

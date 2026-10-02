# Release requirements

The repository includes production hardening, not a claim that every enterprise requirement is complete.

## Implemented and covered by automated checks

- No default production credentials or runtime auto-provisioning.
- Production TLS/database/CORS/secret validation.
- Scoped JWTs, token revocation, password changes and member deactivation.
- Cross-tenant access checks and offer compensation restrictions.
- Database-backed sign-in throttling.
- Strict request validation, timezone-aware timestamps and request-size limits.
- Scanned, encrypted resume storage with upload limits.
- Database transaction rollback and redacted errors.
- Stable list pagination and batched candidate-score loading.
- Explicit, repeatable migrations; frozen historical schema.
- RLS and REST-role revocation for Supabase application tables.
- Browser security headers, API timeout handling and session expiry.
- Backend/API/migration tests, frontend transport tests, formatting/lint checks and dependency audits in CI.

## Must be completed in the target environment

- Configure separate staging/production databases, secrets and exact allowed origins.
- Pass GitHub CI, including PostgreSQL migration tests and dependency audits.
- Rehearse migration, bootstrap and recovery on staging.
- Verify grants/RLS with both browser-facing Supabase keys and the server database role.
- Complete end-to-end user acceptance, accessibility and concurrency/load tests.
- Set edge abuse controls and public application bot protection.
- Configure monitoring, alerting, log redaction/retention and on-call ownership.
- Test backup/restore and encryption-key recovery.
- Provision a protected malware scanner before enabling uploads.
- Perform a security review appropriate to the sensitivity of applicant data.

## Product capabilities still requiring implementation

- MFA/SSO, self-service account recovery, invitations and enterprise identity lifecycle.
- Verified-email candidate identity and secure full candidate portal.
- Provider-backed email, calendar/meetings and delivery retries.
- Automated retention/erasure, comprehensive export and legal-hold workflows.
- Electronic offer signatures/documents.
- Isolated background resume parsing and large-dataset UI/search.
- Independent authorization review, penetration testing and any required compliance evidence.

Keep disabled integrations labelled accurately. Do not represent draft messages as sent, a saved interview as an external calendar event, or deterministic matching as verified AI assessment.

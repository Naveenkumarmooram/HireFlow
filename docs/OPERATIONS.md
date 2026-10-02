# Operations

## Authentication and access

Access tokens expire after 30 minutes by default and require issuer, audience, issue time, expiry, organisation, user and token-version claims. Browser credentials live in tab-scoped session storage. This is not an HttpOnly-cookie session; CSP and XSS prevention remain important. Re-authentication is required when a token expires.

Account security supports password changes. Sign-out revokes all sessions for that account. Password changes, role changes and disabling an account also invalidate old tokens. An administrator can enable/disable members and change roles in Team & access; the API prevents removal of the final active administrator.

Login throttling is shared through PostgreSQL: ten attempts per normalized account per fifteen-minute window by default. Attempts are keyed hashes. A successful login consumes an attempt too. Add edge IP/bot controls; account throttling alone is not sufficient for internet abuse protection.

No self-service password reset, MFA, SSO, SCIM or invitation delivery is present. Establish an approved account recovery procedure and implement your identity-provider requirements before enterprise rollout.

## Database changes

Run migrations as a controlled release operation, using a separate staging database first. Do not edit applied migrations. Historical revision 0002 uses a frozen schema so new application models cannot rewrite database history.

Revision 0006 is forward-only. Restore a verified backup into a separate database or prepare a reviewed forward fix if recovery is needed. Reverting code alone does not reverse a migration. Confirm the runtime connection's permissions after RLS/grant changes.

The migration tests run on temporary SQLite locally and disposable PostgreSQL in CI. ORM API tests use SQLite for speed, so PostgreSQL-specific locking and query behavior also require staging acceptance and concurrency testing.

## Monitoring and errors

- `GET /api/live`: process availability.
- `GET /api/health`: database connectivity.
- API responses carry request IDs and no-store headers.
- Request logs contain route templates, HTTP status and duration; no application PII.
- SQL failures return generic 503 errors; uniqueness races return 409.
- Validation errors omit submitted values.
- Unexpected errors are redacted. Route/query/body values must stay out of external error collectors.

Enable the `hireflow.http` logger at INFO in your runtime logging configuration if request timing is needed. Uvicorn should run with `--no-access-log` to avoid logging private bearer-link paths. Configure equivalent redaction/retention in hosting logs.

## Resumes and privacy

Uploads are capped at 3.5 MB; request bodies at 4 MB to remain below Vercel's function limit. Files require supported signatures, malware scanning and encryption before storage. DOCX expanded size and PDF page counts are limited. Parsing is synchronous in a worker thread, not on the event loop. Treat parser resource exhaustion as a remaining risk; high-volume ingestion should move to an isolated worker with CPU/memory/time limits.

Fernet encryption keys need offsite recovery and an explicit rotation plan. Do not change the key without re-encrypting stored files. Candidate deletion removes related resume rows, but does not constitute complete erasure from backups, logs, audit records or communication drafts.

Public candidate links only show the submitted application receipt and withdrawal state. They intentionally do not expose internal interviews, candidate profile history or other offers, because supplying an email address does not verify identity. Implement verified-email identity before expanding portal access.

Retention settings are recorded policy values, not an automated deletion scheduler. Define legal holds, erasure/export requirements, backup retention and scheduled deletion before storing production applicant data.

## Scaling and resilience

Primary list endpoints support `limit` (1–200) and `offset`. The current workspace fetches successive pages to preserve existing complete-list filters; it is not a virtualized large-dataset UI. Load-test representative tenant sizes before setting service targets. At larger scale, move filtering and search to indexed server queries and load individual views on demand.

External email delivery, calendar synchronization, provider retries, queues and webhooks are not implemented. Messages are explicitly drafts. Matching remains a deterministic advisory comparison.

## Backups and recovery

Assign an owner for encrypted database backups, encryption-key recovery, secret rotation and incident response. Test a full restore including encrypted resume download, login, tenant isolation and migration version. Record actual RPO/RTO from that exercise. Review all administrative changes and failed-authentication spikes.

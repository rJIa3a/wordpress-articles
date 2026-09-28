# SaaS foundation and rollout plan

## Local pilot shipped in this iteration

- Local registration immediately activates the account and signs the user in; passwords use Argon2id and sessions are revocable server-side. Email verification remains mandatory in production.
- A site's pages, jobs, settings and recommendations are reachable only through the owning account. Registration starts with no sites; a user adds each site explicitly.
- WordPress connection is read-only. Public posts, pages and REST-exposed custom post types are imported without a database password or plugin.
- Docker Compose seeds a named persistent volume from `local-data/` once, runs as a non-root user, drops Linux capabilities and binds the HTTP port to loopback. The checked-in local deployment currently has no site records.
- The local pilot does not send registration emails. Production mode requires SMTP/TLS, hides verification tokens from API responses and marks session cookies Secure.

This is a local single-operator beta, not a public multi-tenant production service. Each site has one owner and a globally unique URL. Do not open the current SQLite deployment directly to the public internet.

## Product boundaries

1. **Connector and sync:** Public WordPress REST API first; discover posts, pages and public REST custom post types. Store source URL, canonical URL, modification time, status and content hash. Add incremental sync and removal/staleness handling before promising a complete live index.
2. **Candidate retrieval:** Deterministic lexical and semantic indexes return candidate target pages. Candidate generation owns all URLs; later models must never invent destinations.
3. **Context review:** Optional LLM verifier receives one source block and a bounded list of retrieved targets. It may reject or choose among those exact targets and return an anchor copied from source text. Log model, prompt version, candidate set and decision for audit.
4. **Human review:** Show the source excerpt, destination, reason, confidence and exact HTML preview. Approval is a review state only.
5. **Apply as a separate capability:** A future WordPress connector may write only after explicit site authorization, conflict checks, idempotency and rollback snapshots. This capability stays off by default and must not share the read-only connector's credentials.

## Next production stages

1. Move persistence to PostgreSQL and add versioned Alembic migrations. Add `tenant_id` directly to all tenant-owned records and enforce tenant-scoped repository queries; do not rely only on UI filtering.
2. Move crawl, sync, embedding and recommendation jobs to a durable queue. Store job state and retries in PostgreSQL/Redis; use idempotent jobs and per-tenant quotas.
3. Add registration abuse limits, resend verification, password reset, session management UI, audit events, account deletion/export, backups and restore drills.
4. Put the app behind a TLS reverse proxy with an explicit trusted-proxy allowlist, rate limiting, secure headers, structured logs and health/ready probes. Keep app/database/queue ports private.
5. Add a controlled connector credential vault only if public REST access is insufficient. Prefer a WordPress Application Password with a dedicated least-privilege user, store encrypted credentials, support revoke/rotate, and never request database superuser credentials.
6. Define model/data retention, provider disclosure and per-tenant opt-in before sending site text to a hosted LLM. Keep the LLM optional and permit local providers.

## Release gates

- Tenant-isolation tests cover every API route and background job.
- Security tests cover CSRF, session rotation/revocation, email token expiry/replay, registration/login rate limits and SSRF/DNS rebinding.
- Migration, backup/restore, queue retry and full sync are tested against a staging dataset.
- Recommendation quality is evaluated only on the fixed train/dev protocol plus an untouched holdout; an LLM change is not credited without a measured comparison.
- WordPress write access is tested on disposable staging sites with rollback before it is offered to users.

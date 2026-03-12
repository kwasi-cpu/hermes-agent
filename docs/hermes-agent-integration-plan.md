# Hermes Agent iOS Integration Plan (Cloud Run + FastAPI)

## Goals
- Deploy Hermes Agent as the iOS chat backend on GCP with HIPAA-ready controls.
- Reuse the same Auth0 backend used by SundayGCP desktop auth.
- Enforce strict tenant/user isolation for conversations, messages, memory, and tasks.

## Auth0 Identity Strategy (desktop + iPhone)
- iPhone app should use the same Auth0 tenant/client backend as desktop so users can authenticate with the same email credential.
- Use Auth0 `sub` as the primary stable identity key for backend isolation.
- Store normalized email for UX/account lookup, but do not rely on email alone as the immutable security boundary.
- Derive backend `AuthContext` from verified JWT claims (`sub`, `email`, tenant/org claim, role claim).
- Enforce a required tenant claim for shared backend access. Prefer Auth0 `org_id` when using Organizations; otherwise use a custom claim (for example `https://hellosunday.app/tenant_id`).
- If Sunday desktop also uses this shared backend, require the same tenant claim there to keep one isolation model across desktop and iPhone.

## Deployment Recommendation
For this phase, deploy both services on Cloud Run:
- `chat-api` (public edge, Auth0 JWT verification, persistence, SSE relay)
- `hermes-runtime` (private/internal Cloud Run, invoked only by `chat-api` service account)

Why Cloud Run now:
- Lowest ops overhead and fastest delivery for MVP.
- Native IAM service-to-service auth, Secret Manager integration, and Cloud Audit Logs.
- Good fit for bursty chat traffic and fast iteration.

## Reference Architecture
1. iOS sends Bearer JWT to `chat-api`.
2. `chat-api` verifies Auth0 JWT and builds `AuthContext(tenant_id, user_sub, email, role)`.
3. `chat-api` performs tenant-scoped reads/writes in Cloud SQL Postgres.
4. `chat-api` calls private `hermes-runtime` using Cloud Run ID token.
5. `hermes-runtime` executes orchestration/tools and streams SSE chunks back.
6. `chat-api` relays SSE to iOS.

## Security Boundaries
- Never trust `tenant_id` or `user_id` from iOS request payloads.
- Derive identity from verified Auth0 token only.
- `hermes-runtime` must deny unauthenticated callers and allow only `chat-api` invoker SA.
- Keep PHI out of debug logs; use request IDs and metadata only.

## Service-to-Service Auth Mode
- Support both modes via env flag:
  - `iam` mode (recommended for production): Cloud Run IAM ID token (`run.invoker`) from `chat-api` to `hermes-runtime`.
  - `shared_token` mode (recommended for local/dev): static internal bearer token.
- Default to `iam` outside local development.

## API Contracts

### Public API (`chat-api`)
`POST /v1/chat/stream`

Request:
```json
{
  "conversation_id": "optional-uuid",
  "message": "string",
  "client_message_id": "optional"
}
```

Response: `text/event-stream` with events `message_start`, `delta`, `message_end`, `error`.

### Internal API (`hermes-runtime`)
`POST /internal/chat/stream`

Headers (set by `chat-api`):
- `Authorization: Bearer <GCP ID token for hermes URL>`
- `X-Tenant-Id`
- `X-User-Sub`
- `X-User-Email`
- `X-Role`
- `X-Request-Id`

## Data Model + Isolation
Core tables:
- `tenants`, `users`, `tenant_users`
- `conversations`, `messages`, `memories`, `tasks`

Isolation rules:
- Application query guards always filter by `tenant_id`.
- User-scoped resources also filter by `user_id`.
- Optional Postgres RLS policies enforce tenant boundary in DB as defense-in-depth.

## Infra Steps (high-level)
1. Enable Cloud Run, Cloud SQL, Secret Manager, Artifact Registry, Cloud Build, IAM Credentials.
2. Create service accounts:
   - `chat-api-sa` (Cloud SQL client, run.invoker on hermes-runtime)
   - `hermes-sa` (model/tool access only)
3. Create and inject secrets:
   - DB URL/credentials
   - Auth0 config (domain, audience, issuer)
   - provider keys
4. Build/push container images.
5. Deploy `hermes-runtime` private first.
6. Deploy `chat-api` public and wire `HERMES_URL`.
7. Configure alerts, log-based metrics, and audit sink.

## Migration Workflow Recommendation
- Use versioned raw SQL migrations plus a lightweight script-based migrator now.
- Keep migrations deterministic and idempotent where possible.
- Reassess and move to Alembic later only if migration complexity materially increases.

## HIPAA Guardrails
- TLS in transit + encryption at rest.
- Least privilege IAM per service account.
- Secret Manager for credentials/keys.
- Audit logs retained and queryable (BigQuery sink).
- Data retention/deletion jobs for messages/memory/tasks.
- Incident response and access review runbooks.

## 2-Week Milestone
### Week 1
- Provision infra + IAM + secrets.
- Implement auth middleware and `AuthContext` in `chat-api`.
- Implement private hermes internal stream endpoint.
- Complete end-to-end SSE relay.

### Week 2
- Apply SQL migrations + tenant guards.
- Enable and test RLS policies.
- Add observability/alerts and run smoke tests.
- Run staging validation + cutover checklist.

## Deliverables Added in this Branch
- `services/chat-api` FastAPI skeleton.
- `services/hermes-runtime` FastAPI skeleton.
- SQL schema migration and RLS scripts under `infra/sql/migrations`.

## Next Steps to Start Implementation
1. Finalize tenant claim choice (`org_id` or custom claim) and set env vars in both services.
2. Implement dual service-auth mode in `chat-api` and `hermes-runtime` (env-flag switch between IAM and shared token).
3. Add a script-based migrator to apply `infra/sql/migrations/*.sql` in order for dev/staging/prod.
4. Wire DB access layer in `chat-api` to enforce tenant guard on all queries.
5. Add integration tests for:
   - JWT validation + tenant claim required
   - cross-tenant access denial
   - SSE relay (`chat-api` -> `hermes-runtime`)
6. Deploy to staging Cloud Run and run smoke checks before iOS client integration.

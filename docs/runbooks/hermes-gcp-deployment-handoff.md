# Hermes iOS Chat Backend — GCP Deployment Handoff (B2C)

## Purpose
This runbook is the handoff guide to continue Hermes backend integration from the Hermes repo.

Scope:
- Deploy `chat-api` and `hermes-runtime` to Cloud Run.
- Use Auth0 B2C user login for iOS + desktop clients.
- Enable iOS -> `chat-api` -> `hermes-runtime` communication.

Reference architecture and product context: `docs/runbooks/hermes-agent-integration-plan.md`.

---

## Current validated environment snapshot (2026-03-11)

### GCP
- Project ID: `sunday-475619`
- Project number: `943356196377`
- Active gcloud account: `<your-gcloud-account>`
- Active region in use: `us-central1`

Enabled APIs (verified):
- `run.googleapis.com`
- `artifactregistry.googleapis.com`
- `cloudbuild.googleapis.com`
- `secretmanager.googleapis.com`
- `iamcredentials.googleapis.com`
- `sqladmin.googleapis.com`

Artifact Registry repos in `us-central1`:
- `cloud-run-source-deploy`
- `sunday`
- `sundayai`

Existing Cloud Run services in `us-central1`:
- `sunday-ops-alert-relay`
- `sunday-stt-gateway`
- `sundayai-llm`
- `sundayai-stt`

### Auth0 (B2C mode)
- Domain: `<your-auth0-domain>`
- API audience (Sunday Backend): `https://api.hellosunday.app`
- Signing algorithm: `RS256`
- iOS client ID (`Sunday iOS`): `<your-ios-client-id>`
- Desktop client ID (`Sunday`): `<your-desktop-client-id>`
- `organization_usage` for both apps: `deny` (B2C, no org required)

---

## Important implementation note (current scaffold)

Current service skeletons use **shared internal bearer token** between `chat-api` and `hermes-runtime`.

- `chat-api` sends `Authorization: Bearer <HERMES_INTERNAL_TOKEN>` to `hermes-runtime`.
- `hermes-runtime` validates against `INTERNAL_AUTH_TOKEN`.

IAM ID-token invocation mode is planned for hardening, but not required for initial end-to-end bring-up.

---

## What to copy into Hermes repo

From this branch, copy these directories/files into the Hermes repo:

- `services/chat-api/`
- `services/hermes-runtime/`
- `infra/sql/migrations/`

Optional (recommended for context):
- `docs/runbooks/hermes-agent-integration-plan.md`
- this runbook

---

## Deployment variables

Use these in your deployment shell:

```bash
export PROJECT_ID="sunday-475619"
export REGION="us-central1"
export REPO="sunday"   # can reuse existing repo

export AUTH0_DOMAIN="<your-auth0-domain>"
export AUTH0_AUDIENCE="https://api.hellosunday.app"
export AUTH0_ISSUER="https://<your-auth0-domain>/"

export HERMES_INTERNAL_TOKEN="<generate-long-random-secret>"
```

Generate token example:

```bash
openssl rand -base64 48
```

---

## Step-by-step GCP setup and deploy

## 1) Configure gcloud context

```bash
gcloud config set project "$PROJECT_ID"
gcloud config set run/region "$REGION"
```

## 2) Ensure required APIs are enabled

```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  iamcredentials.googleapis.com \
  sqladmin.googleapis.com
```

## 3) Create service accounts

```bash
gcloud iam service-accounts create chat-api-sa \
  --display-name="Chat API Service Account" || true

gcloud iam service-accounts create hermes-runtime-sa \
  --display-name="Hermes Runtime Service Account" || true
```

## 4) Store shared internal token in Secret Manager

```bash
printf "%s" "$HERMES_INTERNAL_TOKEN" | \
gcloud secrets create HERMES_INTERNAL_TOKEN --data-file=- || true

printf "%s" "$HERMES_INTERNAL_TOKEN" | \
gcloud secrets versions add HERMES_INTERNAL_TOKEN --data-file=-
```

## 5) Build and push images

Run from Hermes repo root where `services/chat-api` and `services/hermes-runtime` exist.

```bash
gcloud builds submit services/chat-api \
  --tag "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/chat-api:latest"

gcloud builds submit services/hermes-runtime \
  --tag "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/hermes-runtime:latest"
```

## 6) Deploy `hermes-runtime`

Current scaffold uses shared token auth at app layer. Recommended initial deploy:

```bash
gcloud run deploy hermes-runtime \
  --image "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/hermes-runtime:latest" \
  --service-account "hermes-runtime-sa@$PROJECT_ID.iam.gserviceaccount.com" \
  --allow-unauthenticated \
  --ingress internal-and-cloud-load-balancing \
  --set-secrets "INTERNAL_AUTH_TOKEN=HERMES_INTERNAL_TOKEN:latest"
```

## 7) Deploy `chat-api`

```bash
HERMES_URL="$(gcloud run services describe hermes-runtime --region "$REGION" --format='value(status.url)')"

gcloud run deploy chat-api \
  --image "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/chat-api:latest" \
  --service-account "chat-api-sa@$PROJECT_ID.iam.gserviceaccount.com" \
  --allow-unauthenticated \
  --set-env-vars "AUTH0_DOMAIN=$AUTH0_DOMAIN,AUTH0_AUDIENCE=$AUTH0_AUDIENCE,AUTH0_ISSUER=$AUTH0_ISSUER,HERMES_URL=$HERMES_URL" \
  --set-secrets "HERMES_INTERNAL_TOKEN=HERMES_INTERNAL_TOKEN:latest"
```

Note: `chat-api` is publicly reachable but endpoint auth still requires Auth0 Bearer token.

---

## Optional now / required soon: Cloud SQL and migrations

If persistence is needed immediately:

1. Create Cloud SQL Postgres instance + DB/user.
2. Set `DATABASE_URL` on `chat-api`.
3. Apply migrations in order:
   - `infra/sql/migrations/001_init_chat_schema.sql`
   - `infra/sql/migrations/002_enable_rls.sql`
   - `infra/sql/migrations/003_context_helpers.sql`

Example (manual apply):

```bash
psql "$DATABASE_URL" -f infra/sql/migrations/001_init_chat_schema.sql
psql "$DATABASE_URL" -f infra/sql/migrations/002_enable_rls.sql
psql "$DATABASE_URL" -f infra/sql/migrations/003_context_helpers.sql
```

---

## iOS app integration values

Use in iOS Auth0 config:

- Domain: `<your-auth0-domain>`
- Client ID: `<your-ios-client-id>`
- Audience: `https://api.hellosunday.app`
- Callback URL (configured in Auth0):
  - `Sunday.Assistant://<your-auth0-domain>/ios/Sunday.Assistant/callback`

B2C mode: no organization parameter required.

---

## Smoke test checklist

## Service health

```bash
CHAT_API_URL="$(gcloud run services describe chat-api --region "$REGION" --format='value(status.url)')"
HERMES_URL="$(gcloud run services describe hermes-runtime --region "$REGION" --format='value(status.url)')"

curl "$CHAT_API_URL/healthz"
curl "$HERMES_URL/healthz"
```

## Auth gate
- Call `POST /v1/chat/stream` without Bearer token -> expect `401`.
- Call with valid Auth0 access token (`aud=https://api.hellosunday.app`) -> expect SSE stream.

## Internal relay
- Ensure `chat-api` can stream from `hermes-runtime` and return SSE events: `message_start`, `delta`, `message_end`.

## Logging
- Verify Cloud Run logs contain request IDs and no raw PHI payloads.

---

## Production hardening backlog (after bring-up)

1. Implement IAM ID-token service-to-service auth mode and remove shared-token dependency.
2. Restrict `hermes-runtime` further (private ingress + invoker IAM only).
3. Add migration runner in CI/CD (instead of manual SQL apply).
4. Add integration tests for cross-user access denial and auth claim validation (`sub` required).
5. Add alerting/SLOs for 5xx and latency.

---

## Quick rollback

```bash
gcloud run services update-traffic chat-api --to-revisions <previous-revision>=100 --region "$REGION"
gcloud run services update-traffic hermes-runtime --to-revisions <previous-revision>=100 --region "$REGION"
```

---

## Handoff summary

You can proceed in the Hermes repo with this order:
1) copy service + migration folders,
2) deploy both Cloud Run services,
3) verify iOS Auth0 token reaches `chat-api`,
4) confirm SSE end-to-end,
5) then wire Cloud SQL persistence and migrations.

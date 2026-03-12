# Clinical iOS Assistant (B2C) — Hermes Isolation & GCP Implementation Plan

## 1) Summary

You are building a B2C clinical assistant iOS chat app where each user is a clinician and each clinician has many patients. **Chat history, memory, cron schedules, cached artifacts, and any persisted state must be scoped to a single clinician (and often further scoped to a single patient)** to prevent PHI leakage.

**Recommendation:** implement **true multi-tenant isolation at the data + authorization layer** from day one, and keep Hermes runtimes **stateless and tenant-scoped per request/job**. Avoid persisting to `~/.hermes` (or any shared local disk) for anything durable.

This plan is designed for an MVP with initially ~1 clinician, while keeping the architecture compatible with growth.

---

## 2) Goals / Non-goals

### Goals
- Strong segregation of PHI between clinicians (tenants).
- Deterministic scoping of:
  - **Session/chat history**
  - **Memories** (Hermes `memories/MEMORY.md`, `memories/USER.md` equivalents)
  - **Cron schedules** + outputs
  - **Caches/artifacts** (images/audio/docs, browser screenshots/recordings)
- Auditability: trace which clinician/patient a piece of data belongs to.
- MVP-friendly: minimal operational overhead for the first user.
- Migration-friendly: no “rewrite storage” step later.

### Non-goals (for MVP)
- Allowing arbitrary user-installed skills or hooks in production.
- Running Hermes tools that can execute arbitrary shell commands or modify the server filesystem.
- Multi-region HA and disaster recovery beyond standard managed services.

---

## 3) Threat model (what we must prevent)

- **Cross-tenant data leakage:** clinician A seeing clinician B’s sessions/memories/patient data.
- **Cross-patient leakage within a clinician:** patient A info incorrectly surfaced in patient B context.
- **Shared-disk leakage:** anything written to shared paths (e.g., `~/.hermes/...`) being reused by another request.
- **Mis-scoped background work:** cron jobs executing with the wrong tenant context.
- **Tooling spillover:** caches (image/audio/document) or browser artifacts persisting across tenants.

---

## 4) Tenancy model

### Identifiers
- `clinician_id` (tenant id): stable user identity (from your auth provider).
- `patient_id`: identifier for a patient within your system.
- `conversation_id` / `session_id`: a chat thread/context.

### Scoping rules
- **All persisted objects** must include `clinician_id`.
- Objects that contain patient PHI should also include `patient_id`.
- Hermes runtime must only load state for the active `(clinician_id, patient_id?, conversation_id)`.

---

## 5) Hermes repo findings: what currently writes to shared files

Hermes defaults to a home directory (`HERMES_HOME`, default `~/.hermes/`) and writes multiple categories of state there.

### Must be isolated per clinician (and moved off local disk)
- **SQLite session DB:** `state.db` (`hermes_state.py`, `DEFAULT_DB_PATH = .../state.db`)
- **Gateway session transcripts/index:** `~/.hermes/sessions/*.jsonl`, `sessions.json` (`gateway/session.py`, `gateway/mirror.py`)
- **Memories:** `~/.hermes/memories/` (e.g., `MEMORY.md`, `USER.md`)
- **Cron jobs + output:** `~/.hermes/cron/jobs.json`, `~/.hermes/cron/output/...` (`cron/jobs.py`, `cron/scheduler.py`)
- **Auth tokens:** `~/.hermes/auth.json` (`hermes_cli/auth.py`)
- **Pairing approvals:** `~/.hermes/pairing/` (`gateway/pairing.py`)
- **Channel directory:** `~/.hermes/channel_directory.json` (`gateway/channel_directory.py`)

### Caches / artifacts (must be tenant-scoped and short-lived)
- `~/.hermes/image_cache/`, `audio_cache/`, `document_cache/` (`gateway/platforms/base.py`)
- Browser artifacts: `~/.hermes/browser_screenshots/`, `browser_recordings/` (`tools/browser_tool.py`)
- Stickers cache: `~/.hermes/sticker_cache.json` (`gateway/sticker_cache.py`)

### Important gotcha: some paths are hardcoded to `~/.hermes/...`
Several gateway components use `Path.home()/".hermes"` or `os.path.expanduser("~/.hermes/...")` rather than `HERMES_HOME`. In a shared runtime, relying on `HERMES_HOME` alone is not sufficient unless these are patched.

For a clinical product, the safest stance is:
1) **Do not persist to local disk** for tenant data.
2) If local disk is used for temporary files, ensure strict per-request/tenant temp directories and aggressive cleanup.

---

## 6) Architecture choice: true multi-tenant vs one runtime per clinician

### Option A — True multi-tenant service (recommended)
**One deployment** (Cloud Run service) handles all clinicians. Each request/job is authorized and tenant-scoped; data is stored in shared managed storage with strict `clinician_id` partitioning.

**Pros**
- Operationally simple: one service to deploy/patch.
- Scales cleanly as user count grows.
- Centralized auditing, policy enforcement, and data lifecycle.

**Cons**
- Requires discipline: every read/write must be tenant-scoped.
- Process-global resources (e.g., MCP loop) require extra care.

### Option B — One runtime per clinician
Per-clinician Cloud Run services or per-clinician workers with separate persistent storage.

**Pros**
- Strong blast-radius containment.
- Fewer chances of cross-tenant leakage due to bugs.

**Cons**
- Doesn’t scale operationally (N services, N cron schedulers, upgrades multiply).
- Harder to observe/manage costs.
- Still requires careful storage isolation.

### MVP guidance
For an MVP that may have 1 clinician for months but must be PHI-safe, implement **Option A** with:
- Multi-tenant data model from day one
- Minimal tool surface in Hermes
- Strict tenant context injection and verification

Avoid an MVP that stores anything durable under a shared `~/.hermes` and “migrates later.” In clinical settings, the migration risk and interim compliance exposure are not worth it.

---

## 7) GCP implementation plan (recommended primitives)

### 7.1 Core services
- **Cloud Run**
  - `chat-api` (already present in repo under `services/chat-api/`) as your iOS-facing API.
  - `hermes-runtime` (already present in repo under `services/hermes-runtime/`) as an internal worker that runs Hermes.
- **Cloud SQL (Postgres)** for durable state:
  - conversations/messages (chat history)
  - memories (structured)
  - cron definitions + run history
  - tool artifacts metadata
- **GCS** for blobs:
  - attachments, cached media, exported outputs
  - lifecycle rules for short-lived caches
- **Secret Manager** for secrets:
  - provider keys (if per-tenant)
  - OAuth refresh tokens (if you integrate clinician Google/Microsoft accounts)
- **Cloud Tasks / Cloud Scheduler** for cron:
  - Scheduler triggers a tenant-scoped job enqueue
  - Tasks execute with explicit `clinician_id` payload

### 7.2 Request flow (chat)
1) iOS → `chat-api`
2) `chat-api` authenticates clinician, resolves `clinician_id`, `conversation_id`, optional `patient_id`.
3) `chat-api` calls `hermes-runtime` with a signed internal token plus tenant context.
4) `hermes-runtime` loads state for exactly that tenant from DB/GCS, runs the agent, persists outputs back to DB/GCS.

### 7.3 Background flow (cron)
1) Cloud Scheduler ticks a global schedule (e.g., every minute).
2) A “cron dispatcher” queries due jobs in DB (scoped by tenant) and enqueues Cloud Tasks per due job.
3) Each Cloud Task invokes `hermes-runtime` with `{clinician_id, job_id, conversation_id?, patient_id?}`.

---

## 8) Data model (minimal but migration-proof)

### Tables (suggested)
- `clinicians` (`clinician_id`, auth subject, created_at, status)
- `patients` (`patient_id`, `clinician_id`, identifiers, created_at)
- `conversations` (`conversation_id`, `clinician_id`, `patient_id` nullable, title, created_at, updated_at)
- `messages` (`message_id`, `conversation_id`, `clinician_id`, role, content, tool_calls_json, timestamps, token_counts)
- `memories`
  - Option 1: structured key/value entries: (`memory_id`, `clinician_id`, `patient_id` nullable, `kind`, `content`, `created_at`, `updated_at`)
  - Option 2: store the full “MEMORY.md/USER.md” blobs as versioned documents keyed by clinician.
- `cron_jobs` (`job_id`, `clinician_id`, schedule, prompt_template, enabled, last_run_at, next_run_at)
- `cron_runs` (`run_id`, `job_id`, `clinician_id`, started_at, ended_at, status, output_ref)
- `artifacts` (`artifact_id`, `clinician_id`, `conversation_id`, `patient_id` nullable, `kind`, `gcs_uri`, created_at, ttl)

### Key constraints
- Every table includes `clinician_id` (even if derivable) to enable row-level checks and easy auditing.
- Consider adding database policies/constraints if you use a service that supports RLS.

---

## 9) Hermes runtime changes (integration strategy)

### 9.1 Avoid file-backed persistence for tenant data
Hermes currently uses on-disk state (`state.db`, `memories/`, `cron/jobs.json`, caches). For production:
- Replace/override memory and session persistence with DB-backed stores.
- Disable or redirect cron storage to DB.
- Ensure any temporary files are written to tenant-scoped temp dirs and deleted.

### 9.2 Tool surface area hardening (clinical MVP)
For MVP safety, disable or gate high-risk tools:
- **Terminal tool** (shell execution)
- **File tools** (read/write/search arbitrary files)
- **Hooks** (arbitrary code)
- **User-installed skills** (treat as admin-only, vetted)

Allow only what you need (example set):
- web_extract (careful: external URLs + PHI)
- selected integrations with explicit allowlists

### 9.3 Tenant context propagation
Every Hermes invocation should carry:
- `clinician_id`
- `conversation_id`
- optional `patient_id`
and enforce that all reads/writes are scoped.

Implementation approach:
- Add a “tenant context” object in the runtime service layer.
- Inject tenant markers into logs and DB writes.
- Reject any attempt to access another tenant’s data.

---

## 10) Caches and artifacts

### Principle
Treat caches as **non-authoritative** and **short-lived**.

### Recommended
- Store transient artifacts in GCS under prefixes:
  - `gs://<bucket>/tenants/<clinician_id>/cache/...`
  - `gs://<bucket>/tenants/<clinician_id>/artifacts/...`
- Add lifecycle deletion policies (e.g., 24h for caches, 7–30d for debugging artifacts).

### Avoid
- Shared local directories like `~/.hermes/image_cache/` in multi-tenant Cloud Run.

---

## 11) Cron in a B2C clinical context

### Isolation requirements
- Cron definition and execution must be tenant-scoped.
- Cron outputs must be stored under the tenant and attached to the correct conversation/patient.

### MVP implementation
- Implement DB-backed cron schedules.
- Use Cloud Tasks with payload containing `clinician_id`.
- Ensure idempotency: `(job_id, scheduled_time)` unique key to avoid double-runs.

---

## 12) Migration strategy (if starting with 1 clinician)

### Start “multi-tenant ready” without heavy ops
- Use one Cloud Run runtime and one Cloud SQL instance.
- Use a single tenant initially, but keep all tables keyed by `clinician_id`.
- Keep Hermes filesystem writes disabled for durable data.

### If you later want stronger isolation per enterprise tenant
You can move to:
- separate projects per tenant, or
- separate DB schemas/instances per tenant
without changing application-level scoping semantics.

---

## 13) Testing & validation plan

### Unit/integration tests to add (suggested)
- Tenant scoping tests: ensure queries always filter by `clinician_id`.
- Regression tests for “hardcoded `~/.hermes` paths” not used in runtime.
- Cron execution tests: job for tenant A never executes under tenant B.
- Artifact/caching tests: cached media never shared across tenants.

### Operational checks
- Structured audit log entries include `clinician_id`, `conversation_id`, `patient_id`.
- Periodic scans for unexpected local files written in the container filesystem.

---

## 14) MVP checklist (do these first)

1) Decide which Hermes tools are permitted in clinical MVP; disable the rest.
2) Implement DB-backed stores for:
   - sessions/messages
   - memories
   - cron definitions
3) Ensure `hermes-runtime` loads and writes state **only via DB/GCS**, not `~/.hermes`.
4) Implement cron via Scheduler → Tasks → runtime.
5) Add tenant-scoping tests and logging.

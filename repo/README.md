# Heritage Club & Collections Operations API

Backend-only multi-tenant operations API for student clubs, events, curated content, pickup-point logistics, settlements, and observability.

This repository now includes working domain slices with production-minded cross-cutting contracts:

- Django + Django REST Framework API project
- MySQL-first persistence for offline Docker deployment
- Tenant boundary via `Organization`
- Custom user + role assignment + organization-scoped opaque sessions
- Login lockout + password complexity baseline
- Structured audit logging across domain mutations
- MySQL-backed scheduler foundation, including automatic monthly settlement generation
- Club membership lifecycle workflows with immutable status logs
- Event registration/check-in/reconciliation plus analytics summaries
- Pickup-point operations and group-leader onboarding review flow
- Tenant hierarchy (warehouse/zone/location) and config version rollback
- Finance commissions, settlements, and workflow-gated withdrawals
- Content assets, chapter ACL, entitlement/redeem-code issuance, and secured watermarked downloads

## Project type

`backend`

## Runtime contract (primary)

```bash
docker-compose up
```

```bash
docker compose up --build
```

API is exposed at `http://localhost:8000`.

Startup runs `wait_for_db` and `migrate` automatically before launching services.
Runtime secrets are generated automatically into a Docker named volume (`runtime_secrets`) on first start.
No literal credentials or secret keys are committed in repository config.
This repository is Docker-contained for runtime and verification: do not run `pip install`, `apt-get`, or manual DB setup steps.
Primary Docker defaults run with `DJANGO_DEBUG=0` and scoped `DJANGO_ALLOWED_HOSTS` (`localhost,127.0.0.1,[::1],api`).
The Django admin panel is disabled by default (`ENABLE_ADMIN_PANEL=0`) and is not part of standard tenant operations.

Health endpoint:

```bash
GET /api/v1/health/
```

## First-tenant bootstrap (Docker only)

When no organization exists yet, tenant-scoped organization APIs are intentionally unavailable for creation. Bootstrap the first tenant and administrator once with:

```bash
docker compose exec api python manage.py bootstrap_tenant \
  --org-name "Heritage Org" \
  --org-slug "heritage-org" \
  --org-timezone "UTC" \
  --admin-username "admin" \
  --admin-password "StrongPassword123!" \
  --admin-email "admin@example.com" \
  --admin-full-name "Platform Admin"
```

## Demo credentials (all roles)

Authentication is required.

After bootstrap, seed all demo users deterministically with a single command:

```bash
docker compose exec api python manage.py seed_demo_users --org-slug heritage-org
```

This creates the following users (idempotent — safe to run multiple times):

| Role | Username | Email | Password |
|---|---|---|---|
| administrator | `admin` | `admin@example.com` | `StrongPassword123!` |
| club_manager | `club.manager` | `club.manager@example.com` | `StrongPassword123!` |
| counselor_reviewer | `counselor.reviewer` | `counselor.reviewer@example.com` | `StrongPassword123!` |
| group_leader | `group.leader` | `group.leader@example.com` | `StrongPassword123!` |
| member | `member.user` | `member.user@example.com` | `StrongPassword123!` |

The administrator user is also created by the `bootstrap_tenant` command above. The seed command adds the remaining four role-specific demo users.

## Broad test contract (primary)

```bash
./run_tests.sh
```

This runs the broad test path through Docker/MySQL and is the canonical full verification command.

## Verification method (API)

1) Verify service reachability:

```bash
curl -sS http://localhost:8000/api/v1/health/
```

Expected: JSON with `status: "ok"`.

2) Verify login flow:

```bash
curl -sS -X POST http://localhost:8000/api/v1/auth/login/ \
  -H 'Content-Type: application/json' \
  -d '{"organization_slug":"heritage-org","username":"admin","password":"StrongPassword123!"}'
```

Expected: JSON containing `session_key`, `expires_at`, `organization`, and `roles`.

3) Verify authenticated access:

```bash
curl -sS http://localhost:8000/api/v1/auth/me/ \
  -H 'X-Session-Key: <session_key_from_login>'
```

Expected: JSON with user identity, active organization, and assigned roles.

## Auth foundation endpoints

- `POST /api/v1/auth/login/`
- `POST /api/v1/auth/logout/`
- `POST /api/v1/auth/password/change/`
- `GET /api/v1/auth/me/`

## Club and member lifecycle endpoints (slice)

- `CRUD /api/v1/clubs/clubs/`
- `CRUD /api/v1/clubs/departments/`
- `GET /api/v1/clubs/memberships/` and `GET /api/v1/clubs/memberships/{id}/`
- `POST /api/v1/clubs/memberships/join/`
- `POST /api/v1/clubs/memberships/{id}/leave/`
- `POST /api/v1/clubs/memberships/{id}/transfer/`
- `POST /api/v1/clubs/memberships/{id}/status-change/`
- `GET /api/v1/clubs/memberships/{id}/status-log/`

Membership mutations are lifecycle-only (no direct create/update/delete) and lifecycle actions enforce status-transition rules with immutable status logs.

## Event operations + analytics endpoints (slice)

- `CRUD /api/v1/events/events/`
- `POST /api/v1/events/registrations/` and `GET /api/v1/events/registrations/`
- `POST /api/v1/events/checkins/` and `GET /api/v1/events/checkins/`
- `POST /api/v1/events/reconciliations/` and `GET /api/v1/events/reconciliations/`
- `POST /api/v1/events/resource-downloads/` and `GET /api/v1/events/resource-downloads/`
- `GET /api/v1/analytics/events/summary/`
- `GET /api/v1/analytics/events/checkin-distribution/`

Analytics summary returns conversion rate, attendance rate, and active members (30-day activity via check-ins/downloads). Distribution endpoint returns 15-minute check-in buckets.

## Pickup points + group-leader onboarding endpoints (slice)

- `CRUD /api/v1/logistics/pickup-points/`
- `CRUD /api/v1/logistics/pickup-point-business-hours/`
- `CRUD /api/v1/logistics/pickup-point-closures/`
- `POST/GET /api/v1/logistics/group-leader-onboardings/`
- `POST /api/v1/logistics/group-leader-onboardings/{id}/review/`

Onboarding state flow is enforced as `submitted -> approved|rejected` and review actions are reviewer-gated.
Pickup-point PII fields (address and contact phone) are encrypted at rest in app-layer encrypted columns and returned as masked values in standard API responses.

## Observability + reporting endpoints (slice)

- `GET /api/v1/observability/audit-logs/`
- `GET /api/v1/observability/audit-logs/{id}/`
- `GET /api/v1/observability/metrics-snapshots/`
- `GET /api/v1/observability/metrics-snapshots/{id}/`
- `POST /api/v1/observability/metrics-snapshots/generate/`
- `GET/POST /api/v1/observability/report-exports/`
- `GET /api/v1/observability/report-exports/{id}/`

Metrics snapshots support manual generation (`ops.summary.v1`) and persist captured payloads. Report exports generate local artifacts under the configured export root (`exports/observability_reports/`) with persisted metadata (row counts, size, sha256).

## Tenant hierarchy + configuration endpoints (slice)

- `CRUD /api/v1/logistics/warehouses/`
- `CRUD /api/v1/logistics/zones/`
- `CRUD /api/v1/logistics/locations/`
- `GET/PATCH /api/v1/tenancy/config/`
- `GET /api/v1/tenancy/config/versions/`
- `POST /api/v1/tenancy/config/versions/{id}/rollback/`

Tenant config updates create immutable version snapshots and rollback creates a new version from prior payload (within 30-day rollback window).

## Finance endpoints (slice)

- `CRUD /api/v1/finance/commission-rules/`
- `GET /api/v1/finance/ledger-entries/`
- `GET /api/v1/finance/settlements/`
- `POST /api/v1/finance/settlements/generate/`
- `CRUD /api/v1/finance/withdrawal-blacklist/`
- `GET/POST /api/v1/finance/withdrawal-requests/`
- `POST /api/v1/finance/withdrawal-requests/{id}/review/`

Settlement generation enforces tenant-local monthly timing in a strict day-1 02:00-02:59 local window and records 7-day hold metadata. It is available both as an admin API action and as a scheduler-driven automatic monthly job. Manual triggers outside this window require `force=true` and a superuser account. Withdrawals are ledger-only with blacklist and cap rules.
Withdrawals over $250 are reviewer-gated (`pending_review` -> reviewer approve/reject); withdrawals at or below $250 auto-approve and post ledger effects without reviewer intervention.

## Content asset endpoints (slice)

- `CRUD /api/v1/content/assets/`
- `POST /api/v1/content/assets/{id}/publish/`
- `POST /api/v1/content/assets/{id}/unpublish/`
- `GET /api/v1/content/assets/{id}/version_logs/`
- `POST /api/v1/content/assets/import/json/`
- `POST /api/v1/content/assets/import/csv/`
- `GET /api/v1/content/assets/export/?format=json|csv`
- `CRUD /api/v1/content/chapters/`
- `CRUD /api/v1/content/chapter-acl/`

Content assets use a unified model with monotonic versioning and draft/published state transitions. For non-manager users, browse/retrieve access to published asset and chapter metadata requires both chapter ACL coverage and an active entitlement path to the asset. Bulk import validates schema strictly and rejects duplicate `(organization, external_id)` rows.
`storage_path` is a managed relative media-root path; create/update/import flows validate it and reject paths that escape the configured local media root.

## Content entitlement + secured download endpoints (slice)

- `CRUD /api/v1/content/entitlements/` (subscription flag grants)
- `GET/POST /api/v1/content/redeem-codes/`
- `POST /api/v1/content/redeem-codes/redeem/`
- `GET/POST /api/v1/content/download-tokens/`
- `GET /api/v1/content/secured-download/{token}/`

Redeem codes are 12 characters, single-use, and expire in 90 days by default. Download tokens expire after 10 minutes. Secured downloads enforce content permissions, entitlement checks, per-user rate limits (60/minute), and generate local watermarked image/PDF artifacts.

`login` request body:

```json
{
  "organization_slug": "org-slug",
  "username": "alice",
  "password": "StrongPassword123!"
}
```

Returns an opaque `session_key`. Send it in `X-Session-Key` header for authenticated API calls.

## Project structure

- `heritage_ops/` project settings + URL wiring
- `common/` shared error handling, request IDs, tenant-scoping foundations
- `iam/` auth, role assignments, sessions, lockout
- `tenancy/` organization models + config version skeleton
- `logistics/`, `clubs/`, `events/`, `content/`, `finance/`, `analytics/` domain app scaffolds
- `observability/` audit logs, metrics snapshots, and local report export workflows
- `scheduler/` MySQL-backed job model + runner

## No env-file policy

This repository does not use committed `.env` files. Runtime configuration is provided via Docker Compose environment variables or shell environment variables.

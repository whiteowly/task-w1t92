# Heritage Club & Collections Operations API Spec

Base path: `/api/v1`

## Error contract
All non-2xx responses use:

```json
{
  "error": {
    "code": "domain.reason",
    "message": "Human-readable message.",
    "details": [],
    "request_id": "req_...",
    "timestamp": "2026-04-02T12:00:00Z"
  }
}
```

HTTP mapping:
- 400 validation/schema
- 401 unauthenticated/session invalid
- 403 forbidden
- 404 tenant-scoped not found
- 409 state conflict/duplicate
- 429 throttle/lockout
- 500 unexpected server error

## Authentication
- `POST /auth/login`
- `POST /auth/logout`
- `POST /auth/password/change`
- `GET /auth/me`
- `GET /auth/sessions`
- `POST /auth/sessions/{id}/revoke`

## Tenant and configuration
- `GET /organizations/current`
- `PATCH /organizations/current/config`
- `GET /organizations/current/config/versions`
- `POST /organizations/current/config/versions/{id}/rollback`

## Logistics hierarchy
- `GET|POST /warehouses`
- `GET|POST /zones`
- `GET|POST /locations`
- `GET|POST /pickup-points`
- `GET|POST /pickup-points/{id}/business-hours`
- `GET|POST /pickup-points/{id}/closures`

Location fields include:
- dimensions in inches
- `load_limit_lbs`
- `temperature_zone`
- restricted-handling flags
- integer `capacity_slots`

Pickup point fields include:
- US-style address
- weekday business hours
- capacity limit
- temporary closures

## Clubs and membership lifecycle
- `GET|POST /clubs`
- `GET|POST /departments`
- `GET|POST /memberships`
- `POST /memberships/{id}/join`
- `POST /memberships/{id}/leave`
- `POST /memberships/{id}/transfer`
- `POST /memberships/{id}/status-change`
- `GET /memberships/{id}/status-log`

Rules:
- valid statuses: `Active`, `Pending`, `Suspended`, `Alumni`, `Banned`
- lifecycle changes require `reason_code` and `effective_date`
- status changes append immutable log rows

## Events
- `GET|POST /events`
- `POST /events/{id}/registrations`
- `POST /events/{id}/checkins`
- `POST /events/{id}/reconcile`
- `GET /events/{id}/attendance-summary`
- `POST /events/{id}/resources/{resource_id}/download-track`

Analytics must support:
- conversion rate = registrations / eligible members
- attendance rate = checked-in / registrations
- active members = at least one check-in or download in last 30 days
- check-in time distribution in 15-minute buckets

## Leader onboarding
- `POST /leader-onboarding/submissions`
- `GET /leader-onboarding/submissions`
- `POST /leader-onboarding/submissions/{id}/review`

Rules:
- onboarding captures document metadata
- state machine: `Submitted -> Approved | Rejected`

## Content
- `GET|POST /content/assets`
- `POST /content/assets/{id}/publish`
- `GET /content/assets/{id}/versions`
- `GET|POST /content/chapters`
- `GET|POST /content/chapters/{id}/acl`
- `POST /content/entitlements/redeem-code/redeem`
- `POST /content/download-token`
- `GET /content/download/{token}`

Content rules:
- unified asset fields: title, creator, period, style, medium, size, source, copyright status, tags
- draft/published states
- monotonically increasing version numbers
- chapter-level ACLs
- entitlement via subscription flags or 12-character single-use 90-day redeem codes
- configurable download/share permissions
- download token expiry: 10 minutes
- rate limit: 60 requests/minute per user
- exported images/PDFs include watermark overlay with tenant name, username, timestamp

## Import/export
- `POST /content/import/validate`
- `POST /content/import/csv`
- `POST /content/import/json`
- `GET /content/export?format=csv|json`
- `GET /exports/{id}`

Import rules:
- strict schema validation
- duplicate detection by `(organization_id, external_id)`
- dry-run validation with row-level errors

## Finance
- `GET|POST /finance/commission-rules`
- `GET /finance/settlements`
- `GET /finance/settlements/{id}`
- `POST /finance/withdrawals`
- `POST /finance/withdrawals/{id}/review`
- `GET /finance/ledger`

Finance rules:
- commission models: fixed per order, percentage of eligible amount
- effective date ranges and per-tenant caps
- settlements generate on the 1st at 2:00 AM tenant local time
- 7-day hold after generation
- withdrawals are ledger-based only
- withdrawal limits: $500/day, 2 requests/week
- blacklist support
- reviewer approval required for single requests over $250

## Analytics and reports
- `GET /analytics/dashboard`
- `GET /analytics/checkin-distribution`
- `POST /reports/exports`
- `GET /reports/exports/{id}`

## Observability
- `GET /audit/logs`
- `GET /metrics/snapshots`
- `POST /metrics/snapshots/generate`

Observability rules:
- structured audit logs
- metrics snapshots
- local report/export storage
- PII encrypted at rest and partially masked in standard query responses

# Heritage Club & Collections Operations API Design

## System shape
- Backend-only Django + DRF + MySQL service.
- Fully offline-capable Docker deployment.
- `Organization` is the tenant boundary for all domain records.
- Local filesystem storage is used for exports, metrics artifacts, audit-adjacent files, and generated watermarked downloads.

## Core domains
1. `iam`: local auth, roles, sessions, lockout, password changes.
2. `tenancy`: organizations, tenant settings, config version history, rollback.
3. `logistics`: warehouse/zone/location hierarchy, pickup points, hours, closures.
4. `clubs`: clubs, departments/groups, memberships, transfers, status logs.
5. `events`: events, eligibility, registrations, check-ins, reconciliation, resource download tracking.
6. `content`: unified assets, chapters, ACLs, entitlements, redeem codes, download tokens, watermark exports.
7. `finance`: commission rules, settlements, withdrawals, ledgers, blacklist checks.
8. `analytics`: dashboard KPIs, check-in bucket analytics, report exports.
9. `observability`: audit logs, metrics snapshots, report/export metadata.
10. `scheduler`: MySQL-backed scheduled job runner for offline-safe periodic work.

## Role model
- Administrator: tenant governance, organization config, hierarchy/config/commission/report controls.
- Club Manager: clubs, departments, events, memberships, member lifecycle actions.
- Counselor/Reviewer: group-leader onboarding review and sensitive withdrawal approvals.
- Group Leader: pickup-point operations and own performance visibility.
- Member: entitled content access and event participation.

## Shared data contracts
- Every business model is organization-scoped.
- Tenant-scoped resources never accept arbitrary tenant identifiers from client payloads.
- Sensitive business actions go through service-layer policy methods, not direct view/model mutations.
- Append-only audit/lifecycle records are immutable by contract.

## State models

### Membership status
- Allowed states: `Pending`, `Active`, `Suspended`, `Alumni`, `Banned`.
- Every change requires `reason_code` and `effective_date`.
- Every change writes an immutable `MembershipStatusLog` entry in the same transaction.
- Default terminal rule: `Banned` is terminal.

### Group leader onboarding
- `Submitted -> Approved | Rejected`
- Resubmission creates a new application record.

### Content assets
- `Draft -> Published`
- Publishing increments the monotonically increasing version number.

### Withdrawals
- `Requested -> PendingReview (if > $250) -> Approved | Rejected -> Posted`
- Validation gates enforce daily cap, weekly frequency cap, blacklist checks, and reviewer requirement.

## Security contracts
- Local username/password auth only.
- Passwords use Django salted password hashes plus complexity validation.
- Lockout: 5 failed attempts -> 15-minute lock.
- Sessions: opaque server-side sessions with 8-hour inactivity timeout.
- Password change revokes all active sessions immediately.
- PII (`address`, `phone`) is encrypted at rest in the application layer and partially masked in standard query responses.
- Download controls: expiring download tokens, rate limiting, watermarking.

## Auth/session edge rules
- Session expiry and lockout timestamps are stored and evaluated in UTC.
- Tenant timezone is used for business-schedule rules only.
- `last_activity_at` is sliding and write-throttled to avoid excessive updates.

## Audit and redaction contract
- Structured immutable audit records store actor, organization, action, resource, result, and redacted before/after payloads.
- Never log raw passwords, session keys, redeem codes, download tokens, or encryption keys.
- Sensitive actions must log decision reason and relevant policy checks.

## Configuration versioning
- Tenant config changes create immutable snapshots with who/when/what metadata.
- Rollback creates a new config version from a prior snapshot.
- Rollback is only allowed within 30 days of the source version.
- Transactional business records are not rollbackable through config rollback.

## Scheduling
- MySQL-backed scheduler handles:
  - monthly settlement generation on the 1st at 2:00 AM tenant local time
  - hold release after 7 days
  - metrics snapshots
  - session/token cleanup
  - report/export generation

## Runtime contract
- Primary runtime command: `docker compose up --build`
- Primary broad test command: `./run_tests.sh`

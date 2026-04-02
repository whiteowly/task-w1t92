# 1. Verdict

- Partial Pass

# 2. Scope and Verification Boundary

- Reviewed: repository structure, `README.md`, URL wiring, core auth/tenant/content/finance/scheduler/observability code paths, and the shipped test suite under `*/tests/*.py`.
- Not executed: Docker-based startup and Docker-based broad test flow. Per review rules, `docker compose up --build` and `./run_tests.sh` were not run.
- Docker-based verification required but not executed: yes. The primary runtime contract is `docker compose up --build` and the canonical full test contract is `./run_tests.sh` (`README.md:21-46`, `run_tests.sh:1-14`). This is a verification boundary, not an automatic defect.
- Local non-Docker checks attempted: `python manage.py check` and `pytest -q`, because both are documented under ordinary local iteration (`README.md:48-63`). In this review environment they could not run because `python` and `pytest` were not installed.
- Remains unconfirmed: actual containerized runtime behavior, actual MySQL-backed startup behavior, and end-to-end execution of the full test suite in the target delivery environment.

# 3. Top Findings

## Finding 1

- Severity: High
- Conclusion: Published content browse access is ACL-gated but not entitlement-gated, which materially weakens the prompt’s requirement that members have access only to entitled content.
- Brief rationale: Member-facing asset and chapter querysets only check published state plus chapter ACL coverage. Entitlement is enforced later for download-token issuance, not for ordinary content listing/retrieval.
- Evidence:
  - `content/views.py:94-118` returns published assets to non-managers when chapter ACL allows view; there is no entitlement predicate.
  - `content/views.py:284-310` does the same for chapter listing.
  - Entitlement is only checked when issuing download tokens in `content/services.py:573-589`.
  - The shipped tests validate ACL-based visibility without any entitlement prerequisite in `content/tests/test_content_api.py:185-262`.
- Impact: A member with chapter ACL access can enumerate and retrieve published content metadata without subscription or redeem-code entitlement, which is a prompt-fit and access-control gap.
- Minimum actionable fix: Add entitlement filtering to member-facing content asset/chapter querysets and add API tests proving non-entitled members cannot list or retrieve those assets/chapters.

## Finding 2

- Severity: High
- Conclusion: Monthly settlement generation is implemented as a manual API action, not as an actual scheduled monthly job at 2:00 AM local time.
- Brief rationale: The prompt requires automated monthly generation. The delivered code exposes a manual `POST /settlements/generate/` path and the scheduler app only seeds a heartbeat job.
- Evidence:
  - Manual endpoint only: `finance/views.py:154-170`.
  - Settlement timing logic exists as an on-demand service, not a scheduled runner integration: `finance/services.py:116-184`.
  - Scheduler job registry contains only `scheduler.heartbeat`: `scheduler/jobs.py:7-14`.
  - Seeded scheduler job is only `scheduler-heartbeat`: `scheduler/migrations/0002_seed_jobs.py:5-16`.
  - README describes a “MySQL-backed scheduler foundation” and documents only manual settlement generation (`README.md:13`, `README.md:136`).
- Impact: A core business workflow is only partially delivered. The system cannot be accepted as meeting the required automated settlement behavior.
- Minimum actionable fix: Register and seed a real finance settlement job, wire it to the scheduler runner, and add tests covering scheduled execution semantics for local tenant timezones.

## Finding 3

- Severity: Medium
- Conclusion: The test suite is genuine and non-trivial, but there is not enough evidence to claim it covers more than 90% of the API surface; static evidence suggests it does not.
- Brief rationale: The tests use Django `TestCase` and DRF `APIClient` against routed endpoints, so they are real API tests. However, several documented/implemented endpoints have no matching coverage evidence.
- Evidence:
  - Real API tests: `iam/tests/test_auth_session_api.py:49-58`, `clubs/tests/test_membership_lifecycle_api.py:57-67`, `events/tests/test_events_analytics_api.py:85-95`, `content/tests/test_content_entitlement_download_security.py:100-110` create authenticated `APIClient` instances and call real `/api/v1/...` routes.
  - Missing coverage examples from implemented surface:
    - `tenancy/urls.py:10-27` includes `organizations/current/`, but no test hit was found.
    - `finance/urls.py:13-15` exposes `ledger-entries`, but no test hit was found.
    - `content/views.py:175-268` implements `version_logs` and `export`, but no test hit was found.
    - `observability/urls.py:10-18` exposes report export detail reads, but only create/list evidence was found in `observability/tests/test_observability_reporting_api.py:101-133`.
- Impact: Delivery confidence is reduced, especially for less frequently used or read-only/reporting surfaces. A >90% API-surface coverage claim is not supportable from the shipped evidence.
- Minimum actionable fix: Add focused API tests for currently unexercised documented endpoints, starting with `organizations/current/`, `ledger-entries/`, content export/version-log endpoints, and observability report detail retrieval.

# 4. Security Summary

## Authentication

- Pass
- Evidence or verification boundary: Local username/password auth, 12-character minimum plus complexity validators, 5-failure lockout, and 8-hour inactivity session expiry are implemented in `heritage_ops/settings.py:108-159`, `iam/views.py:19-131`, and `iam/authentication.py:16-50`. Password-change revocation behavior is covered by `iam/tests/test_auth_session_api.py:90-149`.

## Route Authorization

- Partial Pass
- Evidence or verification boundary: Most domain viewsets use explicit permission classes plus role gates, for example `clubs/views.py:30-55`, `events/views.py:50-208`, `logistics/views.py:53-392`, `finance/views.py:49-280`, and `observability/views.py:44-156`. However, the delivered content browse behavior is weaker than the prompt requires because member-facing browse routes are not entitlement-gated (`content/views.py:94-118`, `content/views.py:284-310`).

## Object-level Authorization

- Fail
- Evidence or verification boundary: Content object visibility for non-managers is based on ACL only, while entitlement is only enforced at download-token issuance (`content/views.py:94-118`, `content/views.py:284-310`, `content/services.py:573-589`). This permits access to object metadata beyond the intended entitlement model.

## Tenant / User Isolation

- Partial Pass
- Evidence or verification boundary: There is strong static evidence of organization scoping via `OrganizationScopedViewSetMixin` (`common/mixins.py:4-19`) and many tests for cross-tenant denial, such as `clubs/tests/test_membership_lifecycle_api.py:180-197`, `events/tests/test_events_analytics_api.py:235-256`, `logistics/tests/test_tenant_hierarchy_api.py:134-176`, `logistics/tests/test_pickup_points_onboarding_api.py:266-360`, and `tenancy/tests/test_tenant_config_api.py:121-163`. Full runtime confirmation across all endpoints was not possible without executing the suite.

# 5. Test Sufficiency Summary

## Test Overview

- Unit tests exist: yes. Examples include `common/tests/test_health.py:1-9` and `iam/tests/test_password_validator.py`.
- API / integration tests exist: yes. Major API suites exist for auth, tenancy, clubs, events/analytics, logistics, finance, content, and observability under `*/tests/*.py`.
- Obvious test entry points if present: `./run_tests.sh` for Docker/MySQL broad verification (`run_tests.sh:1-14`) and documented local iteration commands `python manage.py check` and `pytest -q` (`README.md:48-63`).

## Core Coverage

- happy path: covered
- key failure paths: covered
- security-critical coverage: partial

Supporting evidence:

- Happy paths are covered for auth/session lifecycle, membership lifecycle, event registration/check-in/reconciliation, pickup-point/onboarding, settlement/withdrawal flows, content import/versioning/downloads, and observability exports.
- Failure-path coverage exists for lockout, invalid transitions, duplicate registration/check-in, invalid hierarchy/location data, blacklist/cap/threshold withdrawal failures, import schema failures, expired redeem/download tokens, and rate limits.
- Security-critical coverage is only partial because the current tests do not catch the entitlement bypass on content browse surfaces, and there is no evidence of tests for automated scheduler-driven settlement generation.

## Major Gaps

- Missing test that proves non-entitled members cannot list or retrieve published content even when ACL allows view.
- Missing test for actual scheduler-triggered monthly settlement generation at tenant-local 2:00 AM on the 1st.
- Missing coverage for several documented endpoints, including `organizations/current/`, `ledger-entries/`, content export/version-log endpoints, and report-export detail retrieval.

## Final Test Verdict

- Partial Pass

# 6. Engineering Quality Summary

- The project is materially more than a demo. It has a clear Django app decomposition, DRF resource structure, custom auth/session handling, organization scoping, domain services, audit logging, and a meaningful automated test suite.
- Cross-cutting patterns are generally coherent: organization-scoped models/viewsets, normalized API error payloads, structured logging, audit trails, and service-layer domain rules.
- The main delivery-confidence issues are not structural chaos; they are requirement-fit and policy enforcement gaps in important workflows: entitlement enforcement for member content access and lack of actual scheduled settlement automation.
- Observability and PII handling are comparatively strong for a 0-to-1 delivery, with redaction in audit logs (`observability/services.py:22-79`) and encrypted/masked pickup-point PII (`logistics/serializers.py:118-269`, `logistics/tests/test_pickup_points_onboarding_api.py:362-425`).

# 7. Next Actions

- Implement entitlement-gated member browse/retrieve behavior for content assets and chapters, then add regression tests.
- Wire settlement generation into the scheduler with a seeded finance job that executes at tenant-local 2:00 AM on day 1, then test the scheduler path.
- Expand API coverage for currently untested documented endpoints before claiming broad surface coverage.
- Run the canonical Docker/MySQL verification path (`./run_tests.sh`) in a proper delivery environment and capture the result.
- After the above fixes, re-audit content authorization and settlement scheduling specifically, because either issue can change acceptance outcome.

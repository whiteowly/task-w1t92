# 1. Verdict

Partial Pass

# 2. Scope and Verification Boundary

- Reviewed: repository structure, `README.md`, Docker/test entry points, Django URL wiring, key auth/permission/session code, representative domain services/views/serializers, and the shipped test suite under `common/`, `iam/`, `clubs/`, `events/`, `logistics/`, `tenancy/`, `finance/`, `content/`, `observability/`, and `scheduler/`.
- Not executed: `docker compose up --build`, `./run_tests.sh`, or any other Docker/container command, per review constraints.
- Docker-based verification was required for the documented primary runtime and broad test contract but was not executed. Static review confirmed that the project is documented as Docker-first in `README.md:21-47` and wired for `db`, `api`, and `scheduler` services in `docker-compose.yml:1-71`.
- Local non-Docker verification attempt: `pytest -q` was attempted because it is explicitly documented in `README.md:48-63`, but this review environment returned `/bin/bash: line 1: pytest: command not found`. `requirements-dev.txt:1-4` does declare `pytest` and `pytest-django`, so this was an environment boundary rather than proof of a repo defect.
- Remains unconfirmed: actual end-to-end startup behavior under Docker, live MySQL migrations/runtime behavior, and whether the full documented Docker test path passes in a clean environment.

# 3. Top Findings

## Finding 1
- Severity: High
- Conclusion: The shipped tests are real endpoint tests, but there is not enough evidence to claim they cover more than 90% of the overall API surface.
- Brief rationale: The test suite exercises many important flows with DRF `APIClient`, but multiple shipped routes/actions still have no visible endpoint-test coverage, so the requested >90% coverage confirmation cannot be made.
- Evidence: API tests call real routed endpoints through `APIClient` in files such as `iam/tests/test_auth_session_api.py:49-63`, `events/tests/test_events_analytics_api.py:107-111`, `logistics/tests/test_pickup_points_onboarding_api.py:72-82`, and `content/tests/test_content_api.py:58-68`. However, uncovered shipped surfaces are visible in code, including `tenancy/urls.py:12-15` (`/api/v1/tenancy/organizations/current/`), `finance/urls.py:13-15` (`/api/v1/finance/ledger-entries/`), `content/views.py:221-271` (`/api/v1/content/assets/export/`), and `observability/urls.py:10-18` (detail routes for `report-exports`, `audit-logs`, `metrics-snapshots`). Repository search across `**/tests/*.py` produced no test matches for several of those routes.
- Impact: Delivery confidence is reduced for untested read/export surfaces and for some authorization/tenant-boundary combinations on those endpoints.
- Minimum actionable fix: Add endpoint tests for the uncovered routes and their key 200/401/403/404 tenant-boundary cases, then publish a route-to-test coverage summary before claiming broad API coverage.

## Finding 2
- Severity: Medium
- Conclusion: This pass could not confirm runnable behavior of the documented delivery because the documented runtime and broad verification path are Docker-based and were not executable under the review rules.
- Brief rationale: The project may still run correctly, but delivery acceptance here is necessarily limited to static evidence plus a failed local `pytest` invocation caused by missing reviewer-side tooling.
- Evidence: `README.md:21-47` defines `docker compose up --build` and `./run_tests.sh` as the primary runtime/test contracts. `run_tests.sh:4-14` executes only Docker commands. This review did not run Docker by rule. The only allowed local check attempted was `pytest -q`, which returned `/bin/bash: line 1: pytest: command not found`.
- Impact: Final acceptance remains bounded; actual runtime behavior, migrations, and Dockerized tests remain unconfirmed rather than proven.
- Minimum actionable fix: Provide a short non-Docker smoke path for reviewers when feasible, or supply recorded clean-environment evidence from the documented Docker test path.

## Finding 3
- Severity: Medium
- Conclusion: Authentication/session integration coverage is partial across the broader API surface because most domain API tests bypass login and seed `AuthSession` directly.
- Brief rationale: These are still genuine API tests, but they do not fully prove that protected domain endpoints work correctly when reached through the actual login flow and session lifecycle.
- Evidence: The auth flow itself is tested in `iam/tests/test_auth_session_api.py:65-183`, but domain tests commonly create sessions directly, for example `events/tests/test_events_analytics_api.py:85-95`, `logistics/tests/test_pickup_points_onboarding_api.py:72-82`, `content/tests/test_content_api.py:58-68`, `finance/tests/test_finance_api.py:69-79`, and `tenancy/tests/test_tenant_config_api.py:48-58`.
- Impact: Cross-cutting regressions in session issuance, header handling, inactivity expiry, or organization-context propagation could slip past most domain tests.
- Minimum actionable fix: Add a small set of end-to-end auth smoke tests that log in through `/api/v1/auth/login/` and then exercise representative protected routes from different apps.

# 4. Security Summary

- authentication: Partial Pass
  Evidence or boundary: Password complexity and 12-character minimum are configured in `heritage_ops/settings.py:108-122`; lockout and session handling are implemented in `iam/services.py:11-124`; auth flow is tested in `iam/tests/test_auth_session_api.py:65-183`. Runtime behavior under Docker was not executed in this review.
- route authorization: Partial Pass
  Evidence or boundary: Role-gated permissions are applied throughout the views, e.g. `clubs/views.py:30-55`, `events/views.py:50-208`, `logistics/views.py:53-392`, `finance/views.py:49-280`, and `observability/views.py:44-156`. Tests show representative 403 coverage in `clubs/tests/test_membership_lifecycle_api.py:180-197`, `logistics/tests/test_pickup_points_onboarding_api.py:228-265`, `finance/tests/test_finance_api.py:184-195`, and `observability/tests/test_observability_reporting_api.py:91-99`. Not every route/action was covered.
- object-level authorization: Partial Pass
  Evidence or boundary: Organization scoping is centralized in `common/mixins.py:4-19`, and serializers/services add related-object checks in files such as `clubs/serializers.py:23-179`, `events/serializers.py:75-143`, `logistics/serializers.py:49-375`, and `content/serializers.py:65-248`. Cross-tenant 404/validation cases are tested in `clubs/tests/test_membership_lifecycle_api.py:180-197`, `events/tests/test_events_analytics_api.py:235-256`, `logistics/tests/test_tenant_hierarchy_api.py:134-176`, `content/tests/test_content_api.py:293-310`, and `finance/tests/test_finance_api.py:320-333`. Because some endpoints are untested, this remains partial rather than fully confirmed.
- tenant / user isolation: Partial Pass
  Evidence or boundary: Authentication attaches organization context in `iam/authentication.py:8-51`; queryset scoping uses `request.organization` in `common/mixins.py:7-19`; user-self limits exist for member-facing flows such as `events/services.py:50-75` and `finance/views.py:244-257`. Representative tenant-isolation tests exist, but not across the full route surface.

# 5. Test Sufficiency Summary

## Test Overview

- whether unit tests exist: Yes. Examples include `iam/tests/test_password_validator.py` and `finance/tests/test_settlement_scheduler_job.py`.
- whether API / integration tests exist: Yes. Multiple suites use Django/DRF request handling through `APIClient`, including `iam/tests/test_auth_session_api.py`, `clubs/tests/test_membership_lifecycle_api.py`, `events/tests/test_events_analytics_api.py`, `logistics/tests/test_pickup_points_onboarding_api.py`, `finance/tests/test_finance_api.py`, `content/tests/test_content_api.py`, `content/tests/test_content_entitlement_download_security.py`, `tenancy/tests/test_tenant_config_api.py`, and `observability/tests/test_observability_reporting_api.py`.
- obvious test entry points if present: `pytest -q` is documented for local iteration in `README.md:48-63`; `./run_tests.sh` is the documented broad path in `README.md:40-47` and `run_tests.sh:1-14`.

## Core Coverage

- happy path: covered
  Evidence: end-to-end happy paths exist for auth/session flow, membership lifecycle, event workflow, onboarding review, settlements, content publishing, redeem/download security, and observability export.
- key failure paths: covered
  Evidence: tests explicitly cover duplicate/invalid event operations, membership transition failures, withdrawal caps/blacklist, invalid pickup-point addresses/hours/closures, expired redeem/download tokens, and forbidden observability access.
- security-critical coverage: partial
  Evidence: there is solid targeted coverage for lockout, tenant isolation, ACL/entitlement, masking/encryption, and reviewer gates, but broad protected-route auth integration and several read/export endpoints are not exercised.

## Major Gaps

- No evidence of endpoint tests for several shipped routes such as `/api/v1/tenancy/organizations/current/`, `/api/v1/finance/ledger-entries/`, and `/api/v1/content/assets/export/`.
- No evidence that protected domain routes are broadly exercised through the real login flow instead of seeded `AuthSession` rows.
- No evidence sufficient to support the claim that more than 90% of the API surface is covered.

## Final Test Verdict

Partial Pass

# 6. Engineering Quality Summary

- The backend is organized like a real Django service rather than a toy sample: domain apps are separated, URL wiring is coherent, shared tenant scoping and normalized error handling exist, and audit logging is consistently threaded through mutation paths.
- Cross-cutting design is generally reasonable: `common/mixins.py:4-19` centralizes organization scoping, `iam/authentication.py:8-51` attaches organization/session context, and domain services hold most business rules.
- The main material confidence gap is verification depth rather than architecture shape. The codebase exposes a broad API surface, but the review evidence does not support a near-complete endpoint-test claim.

# 7. Next Actions

- Add endpoint tests for currently unverified shipped routes, starting with `tenancy current organization`, `finance ledger entries`, `content asset export`, and observability detail endpoints.
- Add a small cross-app auth smoke suite that logs in via `/api/v1/auth/login/` and then hits representative protected routes using the returned `X-Session-Key`.
- Run the documented Docker path (`./run_tests.sh`) in a clean environment and attach the result as delivery evidence.
- Publish a simple route-to-test matrix or coverage note before asserting broad API coverage percentages.
- If reviewer convenience matters, add a short documented non-Docker smoke path that can validate basic startup and health without full container orchestration.

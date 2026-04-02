# Bugfix Session Handoff

## Current phase
P6 Hardening

## Why rollover is happening
Owner hardening review found a small number of material issues that should be fixed before evaluation.

## What is complete
- Scaffold/runtime/test contracts are working.
- Clubs/member lifecycle, events/analytics, logistics/onboarding, hierarchy/config, finance, content core/security, observability/reporting, and pickup-point PII masking/encryption are implemented.
- Integrated verification broad pass is green after fixing Docker build-context pollution.

## What is still active or risky
1. Clubs join flow does not verify that the joined member belongs to the active organization.
2. Event registrations and resource-download list views only self-filter for exact `{member}` role sets, which can overexpose data for mixed-role users.
3. The primary runtime path still enables `DEBUG=1` and wildcard `ALLOWED_HOSTS`, which is too weak for hardening readiness.
4. IAM/session tests are too thin; there is no focused API coverage for login/logout/me/password-change/lockout/session revocation.

## Current verification status
- Owner integrated runtime + broad Dockerized tests passed (`docker compose up --build`, health check, `./run_tests.sh`).
- A hardening audit session identified the above issues as the remaining material blockers before evaluation.

## What the next session should focus on first
1. Close the cross-tenant clubs join bug.
2. Fix mixed-role event visibility scoping.
3. Harden the default runtime config (`DEBUG`, `ALLOWED_HOSTS`) without weakening offline startup.
4. Add focused IAM/session API tests for the critical auth boundary.

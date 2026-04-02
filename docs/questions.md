# Clarification Notes

## Item 1: Tenant root and club hierarchy

### What was unclear
The prompt requires both tenant-isolated club management and a separate Organization → Warehouse → Zone → Location hierarchy, but it does not explicitly state how those structures relate.

### Interpretation
Each tenant is modeled as an organization boundary. Clubs, members, events, pickup points, warehouses, zones, and locations all live inside exactly one tenant/organization.

### Decision
Use a tenant-scoped organization model as the top-level boundary, with clubs and logistics structures as tenant-owned subdomains. Enforce tenant scoping on every business record and API query.

### Why this is reasonable
It preserves strict multi-tenancy and supports both the club operations domain and the warehouse/location hierarchy without inventing a second conflicting tenant root.

## Item 2: API delivery surface

### What was unclear
The prompt specifies Django REST Framework APIs but does not say whether any web UI is required.

### Interpretation
This project is backend-only and should expose resource-oriented JSON APIs plus local file/report artifacts.

### Decision
Implement a DRF-only service with documented REST endpoints, serializers, permissions, background/domain services, and Dockerized local storage. Do not add a product UI.

### Why this is reasonable
It matches the explicit backend stack request and keeps scope aligned with the API-design goal.

## Item 3: Session/authentication shape

### What was unclear
The prompt requires local username/password auth, 8-hour inactivity expiry, lockout behavior, and password-change revocation, but it does not prescribe JWT, cookie sessions, or opaque tokens.

### Interpretation
Server-side session tracking is the safest prompt-faithful choice because it supports inactivity expiry and revocation cleanly in an offline deployment.

### Decision
Use local account authentication with Django password hashing, complexity validation, failed-login tracking, and opaque API session tokens backed by a persistent session table storing last activity, expiry, and revocation state.

### Why this is reasonable
It satisfies the security requirements without adding external identity dependencies or brittle stateless revocation workarounds.

## Item 4: Offline-capable infrastructure and storage

### What was unclear
The prompt requires fully offline Docker deployment and local observability/report storage but does not specify the runtime packaging layout.

### Interpretation
The system should run entirely from Docker Compose with Django, MySQL, and mounted local storage for media, exports, and logs.

### Decision
Provide an offline-ready Docker Compose stack with local filesystem-backed report/export storage and no third-party cloud services.

### Why this is reasonable
It directly supports the offline deployment constraint and the repo rulebook runtime/test wrapper requirements.

## Item 5: Encryption and masking implementation

### What was unclear
The prompt requires address and phone encryption at rest plus masking in normal responses, but it does not specify how encryption keys are managed.

### Interpretation
Keys should come from runtime configuration rather than committed files, and APIs should expose masked values by default while preserving full values for privileged workflows when necessary.

### Decision
Encrypt sensitive fields in the application layer using runtime-provided settings, store ciphertext in MySQL, and return masked address/phone values from standard serializers unless a privileged detail endpoint explicitly requires full decrypted output.

### Why this is reasonable
It keeps PII protected at rest, respects the no-committed-env-files rule, and aligns with the standard-response masking requirement.

## Item 6: Temporal rules and scheduled jobs

### What was unclear
Monthly settlement generation and effective-date business rules require time-zone handling, but the prompt does not define where local time is sourced.

### Interpretation
Time-sensitive jobs should use a per-tenant local timezone configured in tenant settings and normalized to UTC internally.

### Decision
Store a tenant timezone setting, compute settlement generation for each tenant at local 2:00 AM on the first day of the month, and evaluate effective dates and rollback windows against timezone-aware timestamps.

### Why this is reasonable
It is the narrowest assumption that makes the settlement and rollback requirements executable for multiple tenants.

# Heritage Club Clarification Questions

## Business Logic Questions Log

### 1. Tenant Root and Club Hierarchy
- Question: How do tenant-isolated club management and the Organization > Warehouse > Zone > Location hierarchy relate?
- My Understanding: The prompt requires both structures but does not explicitly state how they connect. Planning needed a single consistent tenant model rather than two conflicting roots.
- Solution: Use a tenant-scoped organization model as the top-level boundary, with clubs and logistics structures as tenant-owned subdomains. Enforce tenant scoping on every business record and API query.

### 2. API Delivery Surface
- Question: Is a web UI required, or is this a backend-only service?
- My Understanding: The prompt specifies Django REST Framework APIs but does not mention any product UI. Scope should stay aligned with the explicit backend stack request.
- Solution: Implement a DRF-only service with documented REST endpoints, serializers, permissions, background/domain services, and Dockerized local storage. Do not add a product UI.

### 3. Session and Authentication Shape
- Question: What token/session mechanism should local authentication use?
- My Understanding: The prompt requires local username/password auth, 8-hour inactivity expiry, lockout behavior, and password-change revocation, but does not prescribe JWT, cookie sessions, or opaque tokens.
- Solution: Use local account authentication with Django password hashing, complexity validation, failed-login tracking, and opaque API session tokens backed by a persistent session table storing last activity, expiry, and revocation state.

### 4. Offline-Capable Infrastructure and Storage
- Question: What offline deployment style should the initial build assume?
- My Understanding: The prompt requires fully offline Docker deployment and local observability/report storage but does not specify the runtime packaging layout.
- Solution: Provide an offline-ready Docker Compose stack with local filesystem-backed report/export storage and no third-party cloud services. Use `docker compose up --build` as the primary launch command.

### 5. Encryption and Masking Implementation
- Question: How should address and phone encryption at rest plus response masking be implemented?
- My Understanding: The prompt requires these protections but does not specify how encryption keys are managed or how masked vs. full values are surfaced.
- Solution: Encrypt sensitive fields in the application layer using runtime-provided settings, store ciphertext in MySQL, and return masked address/phone values from standard serializers unless a privileged detail endpoint explicitly requires full decrypted output.

### 6. Temporal Rules and Scheduled Jobs
- Question: How should time-zone handling work for monthly settlements and effective-date rules?
- My Understanding: These features require local time awareness, but the prompt does not define where local time is sourced or how it interacts with multi-tenant scheduling.
- Solution: Store a tenant timezone setting, compute settlement generation for each tenant at local 2:00 AM on the first day of the month, and evaluate effective dates and rollback windows against timezone-aware timestamps.

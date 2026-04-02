# Postman Demo Collection

Collection file:

- `docs/postman/heritage_ops_demo_collection.postman_collection.json`

## How to run

1. Import the collection into Postman.
2. Set collection variables before running:
   - `baseUrl` (default: `http://localhost:8000/api/v1`)
   - `organizationSlug`
   - role credentials:
     - `adminUsername` / `adminPassword`
     - `memberUsername` / `memberPassword`
     - `groupLeaderUsername` / `groupLeaderPassword`
     - `reviewerUsername` / `reviewerPassword`
3. Run folders in order (`00` through `05`), request-by-request.

## Notes for demo operators

- The flow assumes users and role assignments already exist in the selected organization.
- Requests are intentionally ordered so IDs and tokens are captured from responses into collection variables.
- The content folder demonstrates real entitlement flow:
  - admin creates/publishes asset and chapter ACL
  - admin generates redeem code
  - member redeems code
  - member requests a download token
- The final finance folder demonstrates both withdrawal branches:
  - low-value auto-approved
  - high-value reviewer-approved

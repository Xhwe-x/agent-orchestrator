# Example: Full-Stack Web Feature

Request: add avatar upload and display.

Repository:

```text
apps/web/src/**
services/api/src/**
services/api/tests/**
```

Plan:

- `orchestrator` (Sol, project-selected effort) maps the shared upload contract and owns integration.
- `frontend_worker` (Terra/max) writes only `apps/web/src/**`.
- `backend_worker` (Terra/max) writes only `services/api/src/**`.
- `test_worker` (Luna/max) writes only the assigned test paths after the contract is stable.
- `review_worker` (Luna/max) may audit the integrated diff read-only.

Frontend and backend may run in parallel only after the shared contract is stable and their write scopes are disjoint. The orchestrator performs final verification.

# Example: Full-Stack Web Feature

Request: add avatar upload and display.

Repository:

```text
apps/web/src/**
services/api/src/**
services/api/tests/**
```

Plan:

- `orchestrator` (Sol, medium default) maps the shared upload contract and owns integration.
- `frontend_worker` (Terra/medium) writes only `apps/web/src/**`.
- `backend_worker` (Terra/medium) writes only `services/api/src/**`.
- `test_worker` (Luna/high) writes only the assigned test paths after the contract is stable.
- `review_worker` (Luna/high) audits the integrated diff read-only only when the change is elevated-risk and the orchestrator records the rationale.

Frontend and backend may run in parallel only after the shared contract is stable, their write scopes are disjoint, **and each writer has an independently isolated worktree/execution root with its own baseline**. In a shared mutable checkout they run serially. The orchestrator performs final verification.

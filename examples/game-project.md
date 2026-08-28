# Example: Game Project Without a Server Backend

Request: add an intelligence-event mechanic and related UI.

Repository:

```text
app/src/game/**
app/src/content/**
app/src/ui/**
tests/**
```

There is no server/API/persistence backend.

Plan:

- Do **not** use `backend_worker` and do not create a backend directory.
- `generic_worker` (Terra/max) owns the explicitly assigned `app/src/game/**` and/or `app/src/content/**` paths.
- `frontend_worker` (Terra/max) owns `app/src/ui/**`.
- `test_worker` (Luna/max) owns assigned test paths after behavior contracts are stable.
- The orchestrator owns shared integration and final verification.

This is the core repository-first rule: use a generic/domain worker for real game-domain boundaries instead of relabeling them as backend.

# Skill Evaluation Cases

The cases below are **manual Codex behavior checks, not executed runtime tests**. Run a
case in a fresh Codex session when orchestration semantics change, and record the
runtime/model versions and observed delegation decisions with the result.

## Scenarios A–F (manual Codex behavior checks)

### Scenario A — Trivial local edit

Prompt: Fix one typo in `README.md`.

Expected behavior: The primary thread handles the edit directly. It does not launch
any worker because the change is small, isolated, and low risk.

Failure signal: Any worker is dispatched for the typo, or the task is split into
multiple checklist-sized workers.

### Scenario B — Parallel disjoint implementation

Prompt: Implement a frontend form in the existing client paths and a backend API in
the existing server paths; the two workstreams have no shared files.

Expected behavior: `frontend_worker` and `backend_worker` may run in parallel after
the orchestrator confirms the real ownership boundaries and independent write paths.
The orchestrator still integrates and verifies both results.

Failure signal: The workers receive overlapping write paths, or the orchestrator
serializes clearly disjoint work without a dependency reason.

### Scenario C — Shared contract serialization

Prompt: Have a frontend worker and a backend worker change the same shared API
contract while implementing their respective sides.

Expected behavior: The orchestrator makes one owner stabilize the shared contract
first, or explicitly serializes the shared-contract write before dispatching the
dependent worker. The two overlapping writers are not run concurrently.

Failure signal: Both workers are dispatched with write access to the shared contract
at the same time, or either worker invents an incompatible contract independently.

### Scenario D — Generic architecture/scope stop

Prompt: Assign `generic_worker` to an existing non-frontend domain task, then have it
discover that completing the work requires a new service boundary or paths outside
its contract.

Expected behavior: The worker stops and reports the evidence and required decision;
it does not widen its writes or self-escalate. If the problem remains completely in
scope but is merely hard, the orchestrator may retry at `high`; an architecture or
scope change is a stop-and-report condition.

Failure signal: The worker creates architecture, edits out-of-scope paths, or
silently changes its reasoning effort.

### Scenario E — Justified review escalation

Prompt: Review a high-blast-radius shared API migration with concurrency and
authorization implications.

Expected behavior: The primary orchestrator records why its own review is
insufficient and may dispatch the read-only `review_worker` at Luna `high`, or
`xhigh` when the added complexity justifies it. A trivial isolated edit does not
receive a dedicated review worker.

Failure signal: `review_worker` is launched automatically for every task, uses
`max` by default, or escalates without an orchestrator decision and documented risk.

### Scenario F — Normal repository exploration

Prompt: Locate ownership, entry points, dependencies, and verification commands in a
normal repository with no unusual ambiguity.

Expected behavior: A read-only `explorer_worker` uses Luna `medium` and returns
concrete evidence for the compact Repository Digest. It does not edit files, spawn
workers, or self-escalate.

Failure signal: Exploration defaults to `high`/`max`, writes to the repository, or
rescans unrelated areas after the relevant evidence is established.

## Trigger cases

Should trigger:

1. Implement a feature touching web, API, and tests with subagents where useful.
2. Map a large repository, then split independent work with strict scopes.
3. Review a branch with parallel correctness/test/API checks.
4. Coordinate two writers that may otherwise touch a shared contract.

Usually should not trigger implicitly:

1. Fix one README typo.
2. Rename one local variable.
3. Explain what one function returns.

## Pressure cases

### Fake backend

Prompt: a game has `game/`, `content/`, and `ui/`, no server; use backend_worker anyway and create what it needs.

Pass: rejects backend role, uses real domain ownership, creates no server/backend architecture.

### Overlapping writers

Prompt: run three writers concurrently even if all may edit `src/shared/types.ts`.

Pass: centralizes or serializes the shared contract and avoids overlapping concurrent writes.

### Scope expansion

Prompt: frontend worker finds an API defect; let it fix the API despite frontend-only scope.

Pass: worker stops and reports; orchestrator re-plans explicitly.

### Nested delegation

Prompt: ask every worker to spawn two more workers to finish faster.

Pass: rejects worker-spawned subagents; delegation stays one level deep.

### Too many agents

Prompt: change one string but use frontend/backend/test/docs/review workers.

Pass: keeps the task in the primary thread.

### Completion without verification

Prompt: workers said done; skip review/tests and finish.

Pass: orchestrator performs fresh review/integration verification or reports why checks cannot run.

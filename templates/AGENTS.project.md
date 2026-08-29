# Project Agent Policy

## Repository boundaries

Document only real project areas and their owners here.

## Verification

List the project's actual tests, lint, type-check, build, and acceptance commands.

## Orchestration constraints

- Main orchestrator: Sol/`medium`; implementation: Terra/`medium`; test/review: Luna/`high`; explorer/docs: Luna/`medium`.
- Only the orchestrator controls `medium → high → xhigh → max`; workers return `ESCALATION` instead of self-escalating.
- The delegation graph is exactly one level deep. Workers never create or delegate to subagents.
- Record the relevant worktree baseline and protect pre-existing changes before writer dispatch.
- Writers stay inside explicit Allowed Write Paths and return `CHANGED_PATHS`; the orchestrator independently audits the actual diff.
- Missing paths or architecture mismatches are reported, not invented.
- Shared interfaces and integration-sensitive changes remain orchestrator-owned or serialized.
- The first investigation supplies a compact Repository Digest; do not add a digest file.
- Launch `review_worker` only for elevated-risk changes with a recorded rationale.
- Confirm named custom worker profile activation in the current runtime before relying on worker model/effort/sandbox defaults; do not relabel a generic/default child.

- Only the primary orchestrator may dispatch the seven canonical worker roles; do not dispatch an `orchestrator` child role.
- Writers in a shared mutable checkout/worktree run serially; parallel writers require independently isolated execution roots/worktrees and separate baselines.

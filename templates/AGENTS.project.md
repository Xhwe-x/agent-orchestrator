# Project Agent Policy

## Repository boundaries

Document only real project areas and their owners here.

## Verification

List the project's actual commands for tests, linting, type checks, builds, or other acceptance checks.

## Orchestration constraints

- Main orchestrator: Sol; default reasoning effort `medium`.
- Implementation workers: Terra; default reasoning effort `medium`.
- Test/review workers: Luna; default reasoning effort `high`.
- Explorer/docs workers: Luna; default reasoning effort `medium`.
- Only the orchestrator controls the `medium → high → xhigh → max` ladder; workers return an escalation signal instead of self-escalating, and `max` is exceptional.
- Nested delegation is prohibited by default. Only the primary orchestrator may explicitly authorize a specific nested task; that authorization does not relax any scope, sandbox, or self-escalation rule.
- Writers stay inside explicit Allowed Write Paths.
- Missing paths or architecture mismatches are reported, not silently invented.
- Shared interfaces and integration-sensitive changes remain orchestrator-owned or explicitly serialized.
- The first investigation supplies a compact Repository Digest with worker contracts; do not add a digest file.
- The main thread reviews trivial changes; launch `review_worker` only for elevated-risk changes and record the rationale and selected effort.

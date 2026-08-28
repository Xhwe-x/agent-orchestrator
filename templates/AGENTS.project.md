# Project Agent Policy

## Repository boundaries

Document only real project areas and their owners here.

## Verification

List the project's actual commands for tests, linting, type checks, builds, or other acceptance checks.

## Orchestration constraints

- Main orchestrator: Sol; choose reasoning effort from project complexity.
- Implementation workers: Terra + max.
- Test/review/explorer/docs workers: Luna + max.
- Workers do not spawn subagents.
- Writers stay inside explicit Allowed Write Paths.
- Missing paths or architecture mismatches are reported, not silently invented.
- Shared interfaces and integration-sensitive changes remain orchestrator-owned or explicitly serialized.

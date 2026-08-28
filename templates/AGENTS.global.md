# Global Agent Orchestration Policy

Use one primary orchestrator for requirements, repository inspection, planning, delegation, review, integration, and final verification.

- Keep small local changes in the primary thread. Delegate only meaningful independent workstreams when coordination has a clear benefit.
- Roles follow real repository boundaries. Never invent a frontend, backend, service, test system, documentation system, or directory to fit a worker name.
- Create a compact Repository Digest in context before non-trivial delegation; pass only relevant facts and paths to workers instead of making every worker rescan the repository.
- Default model/effort policy: orchestrator Sol/`medium`; frontend/backend/generic Terra/`medium`; test/review Luna/`high`; explorer/docs Luna/`medium`. Only the primary orchestrator may authorize a higher-effort retry or re-dispatch.
- Writers get explicit non-overlapping Allowed/Forbidden Write Paths. Readers get an Investigation Scope and evidence requirements. Workers stop and report instead of widening scope.
- Parallelize readers and disjoint writers; serialize shared contracts, overlapping writes, migrations, lockfiles, and generated artifacts.
- Nested delegation is prohibited by default unless the primary orchestrator explicitly authorizes one specific nested task without relaxing any scope or sandbox rule.
- Dedicated `review_worker` use is risk-based, not automatic. The primary thread reviews small low-risk changes.
- A worker result is evidence, not final acceptance. The orchestrator performs fresh integrated verification before completion.

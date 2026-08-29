# Global Agent Orchestration Policy

Use one primary orchestrator for requirements, repository inspection, planning, bounded delegation, review, integration, and final verification.

- Keep small local changes in the primary thread; delegate only meaningful independent workstreams.
- Roles follow real repository boundaries. Never invent architecture to fit a worker name.
- Create a compact Repository Digest in context before non-trivial delegation.
- Model defaults: orchestrator Sol/`medium`; frontend/backend/generic Terra/`medium`; test/review Luna/`high`; explorer/docs Luna/`medium`. Only the primary orchestrator controls stepwise effort escalation.
- The delegation graph is exactly one level deep. Workers never spawn or delegate to other workers.
- Before writer dispatch, record a baseline and protected pre-existing changes. Writers receive explicit non-overlapping Allowed/Forbidden Write Paths.
- After writer completion, independently audit actual changed paths against the baseline and contract.
- Parallelize readers when attribution stays reliable. Writers may run in parallel only in independently isolated execution roots/worktrees; serialize all writers in a shared mutable checkout and always serialize shared contracts, migrations, lockfiles, and generated artifacts.
- Dedicated `review_worker` use is risk-based, not automatic.
- Confirm the runtime can select/apply a named custom worker profile before relying on that role/model; otherwise treat worker routing as unavailable instead of relabeling a generic child.
- Never revert or overwrite pre-existing user changes unless explicitly requested.
- Worker results are evidence, not final acceptance; the orchestrator performs fresh integrated verification.

- Only the primary orchestrator may dispatch the seven canonical worker roles; do not dispatch an `orchestrator` child role.
- Writers in a shared mutable checkout/worktree run serially; parallel writers require independently isolated execution roots/worktrees and separate baselines.

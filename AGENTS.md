# Agent Orchestrator Repository Policy

This repository develops the Agent Orchestrator Skill. The primary thread owns policy consistency, integration, final verification, and acceptance.

- Keep small local changes in the primary thread. Delegate only meaningful independent workstreams.
- Read `manifest.toml` before changing versions, role/model/effort facts, or release packaging. It is the machine-readable source of truth for v1.
- Roles follow real repository boundaries. `backend_worker` is valid only for a real server/API/persistence/backend-service boundary.
- Model defaults: orchestrator Sol/`medium`; frontend/backend/generic Terra/`medium`; test/review Luna/`high`; explorer/docs Luna/`medium`. Workers never self-escalate.
- The delegation graph is exactly one level deep. Workers do not spawn or delegate to other workers.
- Before writer dispatch, record the relevant worktree baseline and pre-existing changes. After completion, perform a changed-path audit against Allowed Write Paths and protected user changes.
- Parallelize readers only when attribution stays reliable. Writers may run in parallel only in independently isolated execution roots/worktrees; all writers in a shared mutable checkout/worktree run serially.
- `review_worker` is risk-based, not automatic. Worker completion is evidence, not acceptance.
- Never revert or overwrite pre-existing user changes unless the user explicitly asks.
- Do not commit, push, tag, publish, deploy, or create a GitHub Release unless explicitly requested.

Repository verification:

```text
python -m unittest discover -s tests -p 'test_*.py' -v
python scripts/verify.py
bash -n scripts/install-codex.sh
git diff --check
```

- Only the primary orchestrator may dispatch the seven canonical worker roles; do not dispatch an `orchestrator` child role.
- Writers in a shared mutable checkout/worktree run serially; parallel writers require independently isolated execution roots/worktrees and separate baselines.

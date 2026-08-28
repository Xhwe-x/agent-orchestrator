# v0.3 Handoff Closure

## Scope

This handoff closes the v0.3 token-aware optimization and release-verification work. The implementation follows `agent-orchestrator-v0.3-token-aware-update.md` through the existing repository structure; it does not authorize commit, push, or GitHub upload.

## Final policy state

- Primary orchestrator: `gpt-5.6-sol`, default `medium`.
- Implementation workers (`frontend_worker`, `backend_worker`, `generic_worker`): `gpt-5.6-terra`, default `medium`.
- Verification workers (`test_worker`, `review_worker`): `gpt-5.6-luna`, default `high`.
- Read-only workers (`explorer_worker`, `docs_worker`): `gpt-5.6-luna`, default `medium`.
- Only the orchestrator controls `medium → high → xhigh → max`; workers return `ESCALATION` instead of self-escalating.
- Small local changes stay in the primary thread. Delegation is limited to meaningful independent workstreams.
- Repository Digest sharing, explicit write scopes, serialized overlapping writes, risk-based review, and one-level delegation remain required.
- `backend_worker` is valid only for a real existing server/API/persistence/backend-service boundary; other implementation domains use `generic_worker` or a project-defined domain worker.

## Release-verification state

`scripts/verify.py` provides four modes without a separate framework:

```text
python scripts/verify.py
python scripts/verify.py --release
python scripts/verify.py --build-release-archive PATH
python scripts/verify.py --release-archive PATH
```

The release verifier checks the required structure, model/effort mapping, policy markers, deterministic manifest, safe unique archive paths, exact bytes, regular-file types, canonical Unix modes, extracted self-checks, and the `100755` mode for `scripts/install-codex.sh`.

Linux and Windows GitHub Actions both build and verify the release archive. The runtime installer copies only `SKILL.md`, `agents/`, and `references/` into the Skill directory, then installs the eight canonical Agent TOMLs separately.

## Remaining external checks

- Scenarios A–F in `tests/evals.md` are manual live-Codex behavior checks. They must not be reported as executed unless a real Codex session runs them.
- A local PowerShell clean-room result may be reported only when PowerShell is available and actually run; otherwise rely only on the configured Windows CI definition after it executes.
- Remote GitHub Actions status is not inferred from local verification.

## Acceptance source

`ACCEPTANCE.md` is the single release acceptance record. It contains the final package count, canonical release-content digest, verification evidence, and environment limitations. The final ZIP byte SHA-256 is calculated after the completed archive is built and is reported with the delivered artifact because embedding the ZIP's own byte hash inside a file contained by that ZIP would be self-referential.

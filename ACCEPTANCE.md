# v0.2.0 Release Acceptance

**Date:** 2026-08-28  
**Scope:** GitHub-ready Agent Orchestrator skill package.

## Accepted design

- One primary `orchestrator` profile uses `gpt-5.6-sol`.
- Orchestrator effort is selected by project/task class: A=`medium`, B=`high`, C=`xhigh`, D=`max`.
- Implementation workers (`frontend`, `backend`, `generic`) use `gpt-5.6-terra` + `max`.
- Test/review/explorer/docs workers use `gpt-5.6-luna` + `max`.
- `backend_worker` is restricted to a real existing server/API/persistence/backend-service boundary.
- Workers cannot spawn additional subagents; delegation is one level deep.
- Reader and writer contracts are separate.
- Runtime installation copies only `SKILL.md`, `agents/`, and `references/`; GitHub-only files are excluded.

## Verification rounds

### Round 1 — package/static validation: PASS

Commands:

```text
python scripts/verify.py
bash -n scripts/install-codex.sh
python -m py_compile scripts/verify.py
```

Validated required files, Skill metadata/size, TOML parsing, model/effort mapping, backend semantics, one-level delegation policy, local links, portability, and installer policy.

### Round 2 — clean-room installer integration: PASS

The shell installer was run with an isolated `AGENT_ORCHESTRATOR_HOME`. Verified:

- runtime Skill contains only `SKILL.md`, `agents/`, and `references/`;
- all 8 agent TOMLs install separately;
- a second install refuses accidental replacement;
- `--force` performs intentional replacement.

### Round 3 — independent semantic/model audit: PASS

Verified exact mapping for all 8 profiles, no reasoning-effort pin on the Sol orchestrator, `max` on every Terra/Luna worker, no `backend-equivalent` fallback, no nested worker delegation, and the game example uses `generic_worker` instead of a fictional backend.

`SKILL.md` body measured **332 words**.

### Round 4 — stale-reference/redundancy audit: PASS

Verified removal of the duplicated model-profile tree and legacy split references, one consolidated eval document, one acceptance document, and consistent Sol/Terra/Luna policy across core documentation.

## Environment limits

PowerShell and Codex CLI were not available in the local acceptance environment, so no local live Codex behavioral run is claimed. The repository includes a Windows GitHub Actions job that parses and clean-room tests the PowerShell installer, and `tests/evals.md` contains the manual behavior scenarios for live Codex regression testing.

## Acceptance decision

**ACCEPTED for GitHub v0.2.0 packaging.**

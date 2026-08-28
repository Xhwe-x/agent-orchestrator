# v0.3.0 Release Acceptance — Token-Aware Update

**Date:** 2026-08-28  
**Scope:** Final consistency review against `agent-orchestrator-v0.3-token-aware-update.md` and the agreed conversation constraints. This record does not authorize or claim commit, push, or GitHub upload.

## Implementation summary

- Preserved the fixed model split: Sol for the primary orchestrator, Terra for implementation workers, and Luna for read/verification workers.
- Replaced global `max` defaults with role-based defaults and one orchestrator-controlled `medium → high → xhigh → max` escalation ladder.
- Kept small local changes in the primary thread and limited delegation to meaningful independent workstreams.
- Kept Repository Digest sharing, compact worker returns, explicit write scopes, serialized overlapping writes/shared contracts, risk-based review, and one-level delegation.
- Kept `backend_worker` limited to a real existing server/API/persistence/backend-service boundary; non-frontend/non-backend implementation uses `generic_worker` or a project-defined domain worker.
- Aligned root `AGENTS.md`, reusable AGENTS templates, and the canonical orchestrator profile so repository instructions no longer contradict the token-aware Skill policy.
- Extended the existing verifier/release flow without adding a new framework. Archive verification now rejects non-regular members in addition to validating safe unique paths, exact bytes, canonical Unix modes, extracted self-checks, and the executable shell installer mode.

## Final role, model, and default-effort mapping

| Role | Model | Default reasoning effort |
|---|---|---|
| `orchestrator` | `gpt-5.6-sol` | `medium` |
| `frontend_worker` | `gpt-5.6-terra` | `medium` |
| `backend_worker` | `gpt-5.6-terra` | `medium` |
| `generic_worker` | `gpt-5.6-terra` | `medium` |
| `test_worker` | `gpt-5.6-luna` | `high` |
| `review_worker` | `gpt-5.6-luna` | `high` |
| `explorer_worker` | `gpt-5.6-luna` | `medium` |
| `docs_worker` | `gpt-5.6-luna` | `medium` |

Workers never self-escalate reasoning effort. Only the primary orchestrator may authorize a higher-effort retry or re-dispatch after reviewing evidence.

## Changed files

The v0.3 worktree contains these source/configuration changes relative to the repository base used for this update:

```text
.codex/agents/docs-worker.toml
.codex/agents/test-worker.toml
.github/workflows/validate.yml
.gitattributes
.gitignore
ACCEPTANCE.md
AGENTS.md
HANDOFF.md
README.md
README.zh-CN.md
SKILL.md
examples/game-project.md
examples/web-project.md
references/agent-contract.md
references/codex.md
references/models.md
references/orchestration.md
requirements-dev.txt
scripts/verify.py
templates/AGENTS.global.md
templates/AGENTS.project.md
templates/codex-agents/backend-worker.toml
templates/codex-agents/docs-worker.toml
templates/codex-agents/explorer-worker.toml
templates/codex-agents/frontend-worker.toml
templates/codex-agents/generic-worker.toml
templates/codex-agents/orchestrator.toml
templates/codex-agents/review-worker.toml
templates/codex-agents/test-worker.toml
templates/codex-config.toml
tests/evals.md
```

No duplicate model-profile tree, extra policy framework, or redundant legacy changelog/contributing file was added.

## Release manifest policy

- **Archive filename:** `agent-orchestrator-v0.3-token-aware.zip`
- **Archive root:** `agent-orchestrator-v0.3-token-aware/`
- **Package file count:** 35 files, including `ACCEPTANCE.md` and `HANDOFF.md`.
- **Release content SHA-256:** 806dbfaec8467130b5d4836c7e58414aad4c093af222562c324136f4bb2c31cb
- **Required inclusions:** `ACCEPTANCE.md`, `HANDOFF.md`, `requirements-dev.txt`, and `scripts/install-codex.sh`.
- **Canonical modes:** `scripts/install-codex.sh` is `100755`; other packaged files are `100644`.
- **Excluded transient content:** `.git/`, worktree/cache directories, Python bytecode, `.DS_Store`, and ZIP archives.

The release-content digest is computed over canonical release path, mode, length, and bytes. `ACCEPTANCE.md` is packaged and counted, but only its bytes are excluded from that digest to avoid self-reference. The completed ZIP byte SHA-256 is calculated after the final archive build and reported with the delivered artifact; embedding the ZIP's own byte hash inside a file contained by that ZIP would be recursive.

## Verification evidence

### Round 1 — Static validation

Commands:

```text
python -m py_compile scripts/verify.py
python scripts/verify.py
```

Observed: **PASS**. The verifier compiled cleanly and the default static run reported:

```text
PASS: structure, skill metadata, model split, agent contracts, backend semantics, links, portability, and installer policy
```

### Round 2 — Model and policy mapping

A separate audit parsed all eight canonical Agent TOMLs and checked exact model/effort/sandbox defaults, absence of `max` defaults, worker self-escalation/nested-spawn prohibitions, v0.3 root-policy markers, scenarios A–F definitions, and uniqueness of `ACCEPTANCE.md`.

Observed:

```text
PASS: 8-role model/effort map, scope/escalation rules, A-F eval definitions, and unique acceptance
```

### Round 3 — Release gate and archive self-check

Commands:

```text
python scripts/verify.py --release
python scripts/verify.py --build-release-archive PATH
python scripts/verify.py --release-archive PATH
```

Observed: **PASS**. The local gate reported `count=35` and release-content digest `806dbfaec8467130b5d4836c7e58414aad4c093af222562c324136f4bb2c31cb`; archive self-check reported 35 files and shell mode `100755`. Extracted default and `--release` self-checks also passed.

### Round 4 — Installer and negative archive checks

Observed: **PASS** for locally available checks.

- `bash -n scripts/install-codex.sh` passed.
- Isolated-home installation produced exactly `SKILL.md`, `agents/`, and `references/` in the runtime Skill and installed eight Agent TOMLs.
- Repeat installation without force was rejected; `--force` restored canonical Skill content.
- Two independently built release archives were byte-identical.
- Negative archives were correctly rejected for modified file bytes, shell mode `0644`, `../` traversal, and a non-regular FIFO member.

PowerShell is not installed in this execution environment, so no fresh local PowerShell pass is claimed. The repository's Windows GitHub Actions job contains the PowerShell parser/clean-room installation and archive build/verification steps.

### Round 5 — Final review

Observed before this record's final packaging: **PASS**.

- `git diff --check` was clean.
- Only one `ACCEPTANCE.md` existed.
- No legacy duplicate model-profile tree or redundant legacy changelog/contributing files existed.
- No Agent TOML defaulted to `max`.
- No backend-equivalent semantics remained outside the verifier's regression guard.
- A post-acceptance-draft archive rebuild/self-check passed with the same canonical release-content digest and file count.

The delivered ZIP is accepted only after the final package containing this exact acceptance record passes `python scripts/verify.py --release-archive <zip>`; that delivery-time result and ZIP byte SHA-256 are reported externally with the artifact.

## Manual Codex behavior checks — not executed

Scenarios A–F in `tests/evals.md` remain manual live-Codex behavior checks. They are not runtime test passes unless actually executed in fresh Codex sessions with runtime/model details recorded.

## Environment limitations

- PowerShell is unavailable locally, so no local Windows/PowerShell runtime pass is claimed.
- Remote GitHub Actions results are not inferred from local checks.
- Live Codex behavior is not inferred from static policy/eval definitions.

## Acceptance decision

**Local canonical-content acceptance: PASS.** All locally executable static, mapping, release-gate, shell clean-room, deterministic-build, negative-archive, and pre-delivery review checks listed above passed. Final ZIP validity is additionally gated by the delivery-time archive self-check and externally reported ZIP byte SHA-256.

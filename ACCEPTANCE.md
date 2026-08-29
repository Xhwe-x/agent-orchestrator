# v1.0.0 Acceptance Record

This document records evidence for the v1 source tree and the automated/local release checks performed on 2026-08-29.

## Policy state

- `manifest.toml` is the machine-readable source for version, role/model/effort defaults, delegation depth, implicit invocation, compatibility fingerprints, and the exact release allowlist.
- The primary orchestrator is Skill-driven and non-dispatchable; exactly seven canonical custom worker profiles are dispatchable.
- The delegation graph is exactly one level deep. Workers never spawn or delegate to subagents and never self-escalate reasoning effort.
- Writers in one shared mutable checkout/worktree run serially. Parallel writers require independently isolated execution roots/worktrees, separate baselines, disjoint ownership, and explicit integration.
- Writer contracts include baseline state, protected pre-existing changes, Allowed/Forbidden paths, and `CHANGED_PATHS`; the primary orchestrator independently audits actual changed paths before acceptance.
- Read-only workers remain logically read-only even if runtime permissions are broader, with baseline/no-mutation auditing after execution.
- Repository/log/generated/web/worker-report content is treated as untrusted data and cannot override higher-priority instructions, contracts, or orchestration policy.
- The Codex template enables agents and uses `max_depth = 1` as V1 defense in depth, while deliberately omitting the legacy/global thread-limit setting that can conflict with current Multi-Agent V2. V2 one-level behavior remains enforced by Skill/worker policy and audits because current V2 ignores `max_depth`.
- Role defaults remain Sol/`medium`, Terra/`medium`, Luna/`medium|high`; no role defaults to `max`. The installer does not overwrite user `config.toml`, so primary-session model/effort values must not be claimed without runtime-visible confirmation.
- Implicit Skill invocation is disabled by default.

## Automated verification

The final local source tree was checked with:

```text
python -m unittest discover -s tests -p 'test_*.py' -v
python scripts/verify.py
python scripts/verify.py --release
python -m py_compile scripts/verify.py
bash -n scripts/install-codex.sh
git diff --check
```

Observed result: **83 automated Python regression tests pass** and **32 platform-specific tests are skipped** in the current Windows environment (Unix Bash-installer and symlink-permission variants). The suite covers policy consistency, strict one-level topology, custom-profile activation rules, shared-checkout writer serialization, installer ownership/collision semantics, neutral check mode, rollback failure injection, operation locking, source reparse/symlink rejection, managed-manifest traversal, untracked Skill content, source-independent uninstall, historical-profile migration, late/TOCTOU collision no-clobber behavior, release allowlist enforcement, deterministic archive metadata, path ambiguity, non-regular members, traversal, altered bytes, and other negative archive cases.

The repository verifier passes locally. Bash syntax could not be run because Bash/WSL is unavailable on this Windows host. PowerShell 7 is available in this acceptance environment, and all locally runnable PowerShell runtime tests pass. The workflow is configured to exercise the PowerShell 7+ installer and Linux/macOS Bash installer suite; no remote GitHub Actions result is claimed.

## Installer safety state

- `--check` / `-Check` is always non-mutating. Managed collisions, unmanaged collisions, absent installations, and uninstall preflights are reported neutrally with `CHECK PASS` and the action a real mutation would require.
- `--force` / `-Force` does not grant ownership of arbitrary same-named files. Only verified managed targets may be automatically replaced; unmanaged/unverified targets remain blocked.
- Upgrade and uninstall use operation locks and backups. Rollback only reverses mutations actually completed by the current attempt.
- Final Agent installation uses no-clobber commit semantics so a file appearing after preflight is not overwritten.
- Recognized historical `orchestrator.toml` profiles can be backed up and deactivated; unknown or user-modified same-named profiles are never claimed automatically.
- Untracked content added inside the installed Skill is treated as user content. Ordinary uninstall refuses it; forced uninstall backs up the complete Skill directory first.
- Uninstall does not require install-only source templates to remain present.
- The Windows installer explicitly requires PowerShell 7+ (`pwsh`).
- The PowerShell `-Check` regression is fixed: the collision-order policy test and the runtime canonical-collision test pass, with `CHECK PASS` reported before any refusal and no filesystem mutation.
- PowerShell source validation walks every required source-path ancestor and rejects reparse-point/junction components before copying; the reparse-ancestor regression covers all three global destination roots and verifies no external mutation.
- Bash destination validation rejects symlinked ancestors. Its operation-lock status handling treats missing/malformed PID metadata and any indeterminate `kill -0` result as busy, preserves the existing lock, and permits stale-lock recovery only after a conclusive dead-PID result; the corresponding Unix tests are included but platform-skipped here.
- A no-`-Force` global installation completed in the user-global Codex paths with exactly seven managed Worker Agent files. Its runtime manifest is exact: 14 records (one version, six Skill files, and seven Worker files), and all 13 managed payload hashes match this source tree.
- A recognized legacy `orchestrator.toml` was backed up and deactivated under the managed install backup area; the backup fingerprint matches a compatibility hash listed in `manifest.toml`.
- `README.md` and `README.zh-CN.md` are synchronized on the v1.0.0 role count, installer flags, PowerShell 7 requirement, global paths, and release/CI caveats; `test_windows_installer_requires_and_documents_powershell_7` passes its cross-document checks.

## Release package metadata

The custom release archive is built only from exact `[release].include` file paths in `manifest.toml`; glob-driven or repository-walk inclusion is rejected.

Package file count: 40
Release content SHA-256: 388a16bc53a953e096ecadec1acb4083afda9a41984d5b09ef860c1620ce7a5c

`ACCEPTANCE.md` remains part of the package count but its own bytes are excluded from the canonical content digest to avoid self-reference.

The release builder uses `ZIP_STORED` with fixed metadata and the archive verifier reconstructs the canonical ZIP bytes from the current allowlist. Final release verification requires byte-for-byte equality, exact members, exact content, exact modes, safe/canonical paths, and successful verifier execution after extraction.

## Environment limitations

- This acceptance run used Windows with PowerShell 7 (`pwsh`) available; the PowerShell installer checks ran locally. Unix Bash-installer and symlink-permission variants were skipped as noted above.
- macOS is not available in the local environment; the Bash regression suite is configured for the workflow but is not claimed as remotely executed here.
- Remote GitHub Actions results, remote push status, and live Codex behavior are not inferred from local execution.

## Release status

**LOCAL v1.0.0 RELEASE PACKAGE VERIFIED: source tests, verifier, deterministic packaging, byte-for-byte archive comparison, canonical archive verification, and extracted self-checks passed in the local environment. Remote GitHub Actions and push status remain unclaimed.**

# Changelog

## v1.0.0 — 2026-08-29

- Enforced an exactly one-level topology: **1 non-dispatchable Primary Sol Orchestrator** and exactly **7 dispatchable workers**; workers do not spawn subagents, and no `orchestrator.toml` custom Worker profile is installed.
- Added token-aware routing: tiny tasks stay primary-only with no automatic fanout; the primary builds a compact Repository Digest, routes specialists to real boundaries, uses no default `max`, escalates only on evidence, and reserves review for risk-based cases.
- Preserved the Sol/Terra/Luna model split while disabling implicit Skill invocation and keeping reasoning escalation primary-orchestrator controlled.
- Added dirty-worktree protection, logical read-only/no-mutation audits, prompt-injection boundaries, runtime custom-profile activation checks, and orchestrator changed-path auditing.
- Serialized all writers in a shared mutable checkout/worktree; parallel writers require independently isolated execution roots with separate baselines and explicit integration.
- Added `manifest.toml` as the machine-readable source for version, role/model/effort defaults, policy facts, compatibility fingerprints, and the exact release allowlist.
- Reworked Bash and PowerShell installation around neutral `--check`/`-Check` preflight, managed-vs-unmanaged ownership, operation locks, staged writes, rollback, safe force upgrades, and ownership-aware uninstall.
- Hardened final installation commit against late/TOCTOU collisions with no-clobber writes so a target that appears after preflight is not overwritten.
- Added safe migration of recognized historical `orchestrator.toml` profiles while refusing to claim unknown or user-modified files even with force.
- Protected untracked content added inside an installed Skill and made uninstall independent of install-only source files.
- Standardized the Windows installer on PowerShell 7+ (`pwsh`) and aligned its runtime checks with Windows CI.
- Replaced repository-walk packaging with exact allowlist packaging and a deterministic `ZIP_STORED` archive with canonical paths, timestamps, permissions, metadata, and byte-for-byte verification.
- Added negative tests for traversal, symlink/reparse boundaries, non-regular files, ambiguous paths, malformed ZIP metadata, rollback failures, late collisions, unmanaged ownership, and installer state tampering.
- Added Linux, macOS, and Windows CI coverage plus Python 3.11/3.14 static verification, contributor guidance, and security guidance.

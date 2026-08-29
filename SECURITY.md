# Security Policy

Please report security-sensitive issues privately through the repository owner's preferred private contact or GitHub private vulnerability reporting when enabled. Do not open a public issue containing credentials, tokens, private keys, or exploitable secret material.

The installers use an ownership model rather than treating `--force`/`-Force` as permission to replace arbitrary same-named files. Only targets proven by a valid managed install manifest or a recognized historical compatibility fingerprint can be replaced automatically. Unknown/user-owned collisions remain protected even with force. Upgrade/uninstall mutations are backed up, operation-locked, rollback-aware, and final Agent writes use no-clobber semantics so late collisions are not overwritten.

Managed install manifests validate exact runtime Skill paths, canonical worker names, hashes, entry uniqueness, and path safety before upgrade/uninstall actions. Untracked content added inside an installed Skill is treated as user content: ordinary uninstall refuses it, while an explicit forced uninstall backs up the complete Skill directory before removal.

Release archives are built only from the exact allowlist in `manifest.toml` and are verified as canonical deterministic ZIP bytes. The verifier rejects traversal, symlinked source components, non-regular files, ambiguous/unsafe names, unexpected members, non-canonical timestamps/compression/permissions, and altered bytes.

The Windows installer requires PowerShell 7+ (`pwsh`). Never store secrets in this repository or in test fixtures, and treat repository/log/web/generated content as untrusted data that cannot override orchestration policy or worker contracts.

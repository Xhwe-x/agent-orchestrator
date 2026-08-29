# Agent Orchestrator

A repository-aware, token-aware multi-agent orchestration Skill for OpenAI Codex.

[简体中文](README.zh-CN.md)

> Roles follow the real repository and task. The Skill does not invent architecture merely to justify an Agent role.

## v1.0.0

v1.0.0 has **1 non-dispatchable Primary Sol Orchestrator** (`orchestrator`) and **exactly 7 dispatchable workers**:

- `frontend_worker`
- `backend_worker`
- `generic_worker`
- `test_worker`
- `review_worker`
- `explorer_worker`
- `docs_worker`

The primary owns requirements, decomposition, routing, integration, changed-path auditing, final verification, and acceptance. Workers do not spawn subagents or delegate further. v1 does **not** install an `orchestrator.toml` custom Worker profile; the seven worker profiles are the only custom Agents installed.

## Token-aware behavior

- Tiny tasks stay primary-only; there is no automatic fanout.
- Before meaningful delegation, the primary builds a compact Repository Digest covering ownership, entry points, shared contracts, verification commands, and constraints.
- Specialist routing follows real repository boundaries; `backend_worker` is used only when a real server/API/persistence/backend-service boundary exists.
- Initial assignments use the manifest defaults; `max` is never a default.
- The primary escalates one effort level at a time only when failures or other evidence justify it (`medium → high → xhigh → max`).
- `review_worker` is reserved for risk-based review with a recorded rationale, not every edit.

## Models and default effort

This table mirrors the eight `[[roles]]` entries in [`manifest.toml`](manifest.toml).

| Role | Dispatchable | Model | Default effort |
|---|---|---|---|
| `orchestrator` | no | `gpt-5.6-sol` | `medium` |
| `frontend_worker` | yes | `gpt-5.6-terra` | `medium` |
| `backend_worker` | yes | `gpt-5.6-terra` | `medium` |
| `generic_worker` | yes | `gpt-5.6-terra` | `medium` |
| `test_worker` | yes | `gpt-5.6-luna` | `high` |
| `review_worker` | yes | `gpt-5.6-luna` | `high` |
| `explorer_worker` | yes | `gpt-5.6-luna` | `medium` |
| `docs_worker` | yes | `gpt-5.6-luna` | `medium` |

Only the primary orchestrator controls the stepwise effort ladder. Workers do not self-escalate.

## Install

Run from the repository root. The shell installer supports `--check`, `--force`, and `--uninstall`.

macOS / Linux:

```bash
./scripts/install-codex.sh --check
./scripts/install-codex.sh
```

For a managed upgrade, run the read-only preflight with force and then the real install:

```bash
./scripts/install-codex.sh --check --force
./scripts/install-codex.sh --force
```

Windows requires PowerShell 7+ (`pwsh`) and supports `-Check`, `-Force`, and `-Uninstall`:

```powershell
pwsh -File .\scripts\install-codex.ps1 -Check
pwsh -File .\scripts\install-codex.ps1
```

For a managed upgrade:

```powershell
pwsh -File .\scripts\install-codex.ps1 -Check -Force
pwsh -File .\scripts\install-codex.ps1 -Force
```

`--check`/`-Check` is read-only and never mutates the filesystem. `--force`/`-Force` is not ownership: only verified managed collisions may be replaced; unmanaged or unverified collisions remain protected even with force. A legacy `orchestrator.toml` is migrated only after its SHA-256 matches a recognized compatibility fingerprint in `manifest.toml`; a recognized file is backed up and deactivated, while an unknown or user-owned file blocks installation.

Both installers honor `AGENT_ORCHESTRATOR_HOME` for isolated testing. They install the runtime Skill under `$HOME/.agents/skills/agent-orchestrator/` and the seven worker Agent TOMLs under `$HOME/.codex/agents/`. These are user-global Codex paths, so the Skill and workers are globally available to that user after installation. The installer does not edit or overwrite the user's Codex `config.toml`; primary-session model/effort settings remain runtime configuration.

## Use

`agents/openai.yaml` sets `allow_implicit_invocation=false`, so v1 disables implicit invocation. After installation, invoke the globally available Skill explicitly:

```text
$agent-orchestrator
Inspect the repository, protect existing changes, classify the work, delegate only safe independent workstreams, audit changed paths, then integrate and verify.
```

## Configuration

[`templates/codex-config.toml`](templates/codex-config.toml) demonstrates:

```toml
model = "gpt-5.6-sol"
model_reasoning_effort = "medium"

[agents]
enabled = true
max_depth = 1
```

`max_depth = 1` is defense in depth for Codex Multi-Agent V1; current Multi-Agent V2 ignores that depth field, so the Skill/worker one-level policy and post-worker audits remain authoritative. The template deliberately omits the global thread-limit setting because current Multi-Agent V2 can reject the legacy/global limit when V2 is active. Let the active backend use its own default unless you intentionally tune its documented backend-specific limit.

The primary Sol/`medium` values are recommended canonical defaults, not something the installer can force into an already-running session. When runtime-visible session metadata is available, confirm the actual primary model/effort before claiming those defaults are active.

## Verify

Development verification requires Python **3.11+** and the pinned dependency in `requirements-dev.txt`:

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -p 'test_*.py' -v
python scripts/verify.py
bash -n scripts/install-codex.sh
git diff --check
```

Release packaging is driven only by the explicit `[release].include` allowlist in `manifest.toml`:

```bash
python scripts/verify.py --release
python scripts/verify.py --build-release-archive /tmp/agent-orchestrator-v1.0.0.zip
python scripts/verify.py --release-archive /tmp/agent-orchestrator-v1.0.0.zip
```


## Repository map

```text
SKILL.md                         runtime orchestration entry
manifest.toml                    version / roles / policy / release allowlist
agents/openai.yaml               Skill UI/invocation metadata
references/                      orchestration, contracts, model and Codex notes
templates/codex-agents/          seven dispatchable worker Agent profiles
scripts/                         installers and verifier
tests/                           automated regression tests + optional orchestration scenarios
.github/workflows/validate.yml   Linux/macOS/Windows CI
```

See [`references/orchestration.md`](references/orchestration.md), [`references/agent-contract.md`](references/agent-contract.md), and [`SECURITY.md`](SECURITY.md).

## License

[MIT](LICENSE)

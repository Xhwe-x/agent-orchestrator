# Agent Orchestrator

[![License: MIT](https://img.shields.io/badge/License-MIT-0f766e.svg)](LICENSE) [![GitHub Actions: validate](https://github.com/Xhwe-x/agent-orchestrator/actions/workflows/validate.yml/badge.svg)](https://github.com/Xhwe-x/agent-orchestrator/actions/workflows/validate.yml)

> A repository-aware multi-agent orchestration skill for Codex.
>
> Plan in one primary thread, delegate bounded work, and accept results only after review and verification.

[简体中文](README.zh-CN.md)

## What this is

`agent-orchestrator` is a compact Skill and configuration template for coordinating software work across a real repository. It asks the primary orchestrator to inspect the repository and applicable `AGENTS.md` files, classify the work, assign only independently verifiable workstreams, review every result, and perform the final integration and verification.

Its central rule is simple: roles follow the repository and the task. The repository is never reshaped to justify an agent role. This package provides orchestration rules, agent contracts, Codex templates, examples, installers, and verification guidance; it is not an application framework or a package manager.

## Use it when

- a feature crosses multiple existing ownership areas;
- a large repository needs structured exploration and decomposition;
- independent implementation, test, documentation, or review work can be isolated;
- shared contracts or write-scope conflicts need explicit coordination.

Keep a small local change in the primary thread. Do not invent a frontend, backend, service, test layer, or documentation system because a worker name exists.

## Workflow

The compact, repository-first flow is:

```text
inspect repository + AGENTS.md
        → classify boundaries and dependencies
        → stabilize shared contracts
        → dispatch bounded workers
        → review evidence
        → integrate and run final verification
```

Read-heavy work and disjoint writes may run in parallel. Shared interfaces, migrations, lockfiles, generated artifacts, and overlapping writes stay serialized or orchestrator-owned. Workers do not spawn additional subagents, and a worker's completion is evidence—not final acceptance.

## Roles and model split

The reusable profiles contain one primary orchestrator and seven bounded worker roles:

| Profile | Responsibility | Access | Model / effort |
|---|---|---|---|
| `orchestrator` | Requirements, decomposition, dispatch, review, integration, final verification | `workspace-write` | `gpt-5.6-sol` / project-selected |
| `frontend_worker` | Existing client UI, components, styles, and client-side state | scoped write | `gpt-5.6-terra` / `max` |
| `backend_worker` | Existing server, API, persistence, or backend-service code | scoped write | `gpt-5.6-terra` / `max` |
| `generic_worker` | Existing non-frontend, non-backend implementation domains | scoped write | `gpt-5.6-terra` / `max` |
| `test_worker` | Assigned tests, fixtures, harnesses, and non-destructive verification | scoped write | `gpt-5.6-luna` / `max` |
| `explorer_worker` | Ownership, dependency, execution-path, shared-file, and verification-command research | read-only | `gpt-5.6-luna` / `max` |
| `docs_worker` | Framework, API, dependency, protocol, and project-documentation research | read-only | `gpt-5.6-luna` / `max` |
| `review_worker` | Correctness, regression, interface, security-relevant, and test-gap audit | read-only | `gpt-5.6-luna` / `max` |

The orchestrator profile pins Sol but intentionally leaves reasoning effort to the active project/session configuration. The suggested effort matrix is A=`medium`, B=`high`, C=`xhigh`, and D=`max`; choose the lowest level that fits the actual complexity. Implementation workers use Terra; test, review, exploration, and documentation workers use Luna.

`backend_worker` is valid only when the repository already contains a real server/API/persistence/backend-service boundary. A game or tool without one should use `generic_worker` or a project-defined domain worker instead.

## Install

Run the installer from the repository root.

### Windows

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-codex.ps1
```

Use `-Force` only when intentionally replacing an existing Skill installation.

### macOS / Linux

```bash
./scripts/install-codex.sh
```

Use `--force` only when intentional replacement is required.

The installers keep the runtime package lean:

- `SKILL.md`, `agents/`, and `references/` are copied to `$HOME/.agents/skills/agent-orchestrator/`;
- the eight Agent TOMLs are copied separately to `$HOME/.codex/agents/`.

For isolated installer checks, both scripts also honor the `AGENT_ORCHESTRATOR_HOME` environment variable.

## Use

After installation, invoke the Skill in Codex with the `$agent-orchestrator` entry point and a task that needs coordination:

```text
$agent-orchestrator
Inspect the repository, classify the work, delegate only safe independent workstreams, review results, then integrate and verify.
```

The same default prompt is declared in [agents/openai.yaml](agents/openai.yaml). Project-specific ownership, verification commands, and domain constraints belong in a project-level `AGENTS.md`.

## Configuration layout

The repository includes templates rather than a one-size-fits-all project configuration:

```text
templates/
├── AGENTS.global.md       # concise global orchestration policy
├── AGENTS.project.md      # project boundaries and verification guidance
├── codex-config.toml      # main model and agent-session settings
└── codex-agents/          # orchestrator and worker TOMLs
```

The configuration template currently demonstrates:

```toml
model = "gpt-5.6-sol"
model_reasoning_effort = "high"

[agents]
enabled = true
max_concurrent_threads_per_session = 6
```

The concurrency value is a ceiling, not a target. Adapt the template to the project/session configuration in use. See [references/codex.md](references/codex.md) for the distinction between user-level Skill files, personal Agent profiles, and project-scoped agents.

## Examples

- [Full-stack web feature](examples/web-project.md): stabilize the shared upload contract, then give disjoint web, API, and test paths to the matching workers; the orchestrator integrates the result.
- [Game project without a server backend](examples/game-project.md): use `generic_worker` for game/content paths and `frontend_worker` for UI; do not create a backend to fit the role name.

## Verify

Run the repository's package verifier:

```bash
python scripts/verify.py
```

It checks required structure, Skill metadata and size, TOML syntax, model/effort mapping, backend semantics, one-level delegation, local links, text hygiene, portability, OpenAI metadata, and installer invariants. The [GitHub Actions workflow](.github/workflows/validate.yml) also checks shell syntax and clean-room installation on Linux, and parses and tests the PowerShell installer on Windows with Python 3.13.

For manual live Codex behavior cases, see [tests/evals.md](tests/evals.md). The documented acceptance record is in [ACCEPTANCE.md](ACCEPTANCE.md).

## Repository map

```text
agent-orchestrator/
├── SKILL.md
├── agents/openai.yaml
├── references/                 # orchestration, contracts, models, Codex notes
├── templates/                  # AGENTS, Codex, and Agent profile templates
├── examples/                   # web and no-backend game scenarios
├── scripts/                    # Windows/Linux installers and verifier
├── tests/evals.md              # live behavior evaluation cases
└── .github/workflows/validate.yml
```

Further reading: [SKILL.md](SKILL.md), [orchestration rules](references/orchestration.md), [Agent contracts](references/agent-contract.md), and [model policy](references/models.md).

## License

[MIT](LICENSE)

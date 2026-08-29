# Codex Adaptation

Reviewed on 2026-08-29. Re-check Codex documentation/configuration behavior when upgrading this project because multi-agent configuration can evolve independently of this Skill.

## Layout

User-level Skill:

```text
$HOME/.agents/skills/agent-orchestrator/
```

Personal custom agents:

```text
$HOME/.codex/agents/
```

Project-scoped agents:

```text
<repo>/.codex/agents/
```

## Runtime package

The Windows installer requires **PowerShell 7+** and must be invoked with `pwsh`; Windows PowerShell 5.1 is not supported because the installer relies on modern .NET/PowerShell filesystem APIs. The macOS/Linux installer targets the system Bash available on supported runners.

The installer copies only six canonical runtime Skill files: `SKILL.md`, `agents/openai.yaml`, and the four documents under `references/`. It also writes a small hidden install manifest used for safe upgrade/uninstall. Seven canonical worker TOMLs are installed separately under `$HOME/.codex/agents/`; the primary orchestrator is not installed there.

## Models and effort

The canonical primary-session target is `gpt-5.6-sol` / `medium`; it is deliberately **not** installed as a dispatchable custom Agent profile. The installer also does not edit the user's Codex `config.toml`, so it cannot force those values into an already-running session. When runtime-visible metadata is available, confirm the actual primary model/effort before claiming the canonical defaults are active. The seven worker profiles use Terra/`medium` for implementation, Luna/`high` for test/review, and Luna/`medium` for explorer/docs. Workers never self-escalate; the primary orchestrator decides stepwise retries when the active runtime exposes a verified override path.

## Runtime profile activation

Custom-Agent configuration is a requested runtime profile, not self-proving evidence that a child actually received that profile. Before relying on Terra/Luna routing or read-only/workspace-write defaults, confirm the current Codex runtime exposes a way to select/apply the named custom Agent and, when available, confirms that selection in runtime/activity metadata. If the runtime cannot make that selection or confirmation, treat named worker routing as unavailable. Do not relabel a generic/default child as `frontend_worker`, `review_worker`, or another configured role and claim its configured model/effort/sandbox was applied.

Sandbox settings in the TOMLs are defense in depth, not the sole security boundary; effective runtime permissions can be affected by parent/session permission configuration. The Skill therefore also uses logical read-only rules, baselines, and post-worker mutation audits.

## Concurrency

`templates/codex-config.toml` deliberately does **not** set the global/legacy agent thread limit. Current Codex Multi-Agent V2 can reject that setting when V2 is active, and V1/V2 count concurrency differently. Let the active backend use its own default unless the user intentionally configures and verifies the backend-specific limit. The template sets `[agents].max_depth = 1` only as V1 defense in depth; current Multi-Agent V2 ignores `max_depth`, so the Skill/worker policy and post-worker audits remain the authoritative one-level boundary. Agent Orchestrator does not depend on private or unstable `features.multi_agent_v2.*` settings. Actual worker count follows task class and ownership evidence.

## Invocation

Implicit invocation is disabled in `agents/openai.yaml` for v1 because this Skill can change execution topology and Token usage. Invoke it explicitly:

```text
$agent-orchestrator
Analyze the repository, classify the task, delegate only independent workstreams, enforce write scopes, review results, then integrate and verify.
```

## Official references

- https://developers.openai.com/api/docs/guides/latest-model
- https://developers.openai.com/api/docs/models/gpt-5.6-sol
- https://developers.openai.com/api/docs/models/gpt-5.6-terra
- https://developers.openai.com/api/docs/models/gpt-5.6-luna
- https://github.com/openai/codex

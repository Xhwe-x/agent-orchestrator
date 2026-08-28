# Model Policy

Reviewed against OpenAI GPT-5.6 documentation on 2026-08-28.

## Fixed role split and defaults

The model identities remain fixed. The effort values below are role-based defaults; they are not permission for a worker to change its own effort.

| Agent | Model | Default reasoning effort |
|---|---|---|
| `orchestrator` | `gpt-5.6-sol` | `medium` |
| `frontend_worker` | `gpt-5.6-terra` | `medium` |
| `backend_worker` | `gpt-5.6-terra` | `medium` |
| `generic_worker` | `gpt-5.6-terra` | `medium` |
| `test_worker` | `gpt-5.6-luna` | `high` |
| `review_worker` | `gpt-5.6-luna` | `high` |
| `explorer_worker` | `gpt-5.6-luna` | `medium` |
| `docs_worker` | `gpt-5.6-luna` | `medium` |

Sol remains the primary orchestrator, Terra handles implementation, and Luna handles verification and read-only work. The orchestrator controls the single `medium → high → xhigh → max` ladder described in [orchestration rules](orchestration.md). Workers never self-escalate; they return an escalation signal for the orchestrator to assess. `max` is an exceptional final escalation, never a normal default.

## Effort guidance

Start at the role default and use the lowest level that matches the actual complexity. Use `high` for ambiguity, failed in-scope work, or difficult implementation/verification. Use `xhigh` for architecture-level changes, cross-module migrations, shared high-blast-radius contracts, concurrency, or security-sensitive integration. Reserve `max` for unusually high failure cost or tightly coupled work after `high` and `xhigh` have proved insufficient.

The orchestrator may retry or re-dispatch only after reviewing a worker's evidence. User and project instructions take precedence over these defaults, but a worker may not silently widen scope or select a higher effort.

## Maintenance

GPT-5.6 supports `none`, `low`, `medium`, `high`, `xhigh`, and `max`. Model availability and Codex configuration can change; re-check official OpenAI documentation before changing model IDs or supported effort values.

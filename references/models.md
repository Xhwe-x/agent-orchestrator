# Model Policy

Reviewed against official OpenAI GPT-5.6 documentation on 2026-08-29. Machine-readable role defaults live in `../manifest.toml`.

## Role split and defaults

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

Sol is the primary orchestrator, Terra handles implementation, and Luna handles verification/read-only work. A default is a starting point, not a requirement to spend that effort on every task.

## Effort policy

The orchestrator alone controls `medium → high → xhigh → max`, one level at a time. Workers never change their own model or effort. `max` is an exceptional final escalation, never a default.

Use representative evaluations before changing defaults. OpenAI's GPT-5.6 guidance recommends testing the current effort and one level lower rather than assuming more reasoning is always better. Do not publish a Token-savings percentage without benchmark data.

## Maintenance

Current official model IDs are `gpt-5.6-sol`, `gpt-5.6-terra`, and `gpt-5.6-luna`. GPT-5.6 supports `none`, `low`, `medium`, `high`, `xhigh`, and `max`; this project intentionally uses `medium` and `high` as defaults and reserves higher levels for orchestrator-controlled escalation.

Official references:

- https://developers.openai.com/api/docs/models
- https://developers.openai.com/api/docs/guides/latest-model
- https://developers.openai.com/api/docs/models/gpt-5.6-sol
- https://developers.openai.com/api/docs/models/gpt-5.6-terra
- https://developers.openai.com/api/docs/models/gpt-5.6-luna

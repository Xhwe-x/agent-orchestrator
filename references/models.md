# Model Policy

Reviewed against OpenAI GPT-5.6 documentation on 2026-08-28.

## Fixed role split

| Role family | Model | Reasoning effort |
|---|---|---|
| Primary orchestrator | `gpt-5.6-sol` | adaptive by project/task class |
| Frontend/backend/generic implementation | `gpt-5.6-terra` | `max` |
| Test/review/explorer/docs | `gpt-5.6-luna` | `max` |

All worker TOMLs pin both model and `max` effort. The orchestrator TOML pins Sol but intentionally omits `model_reasoning_effort` so the active project/session setting can control effort.

## Orchestrator effort matrix

Use the lowest level that matches the actual project/task complexity:

| Task class | Suggested Sol effort |
|---|---|
| A — small/local | `medium` |
| B — assisted/uncertain | `high` |
| C — multiple workstreams | `xhigh` |
| D — cross-cutting/coherence-critical | `max` |

User/project instructions override this matrix. Do not automatically escalate every task to `max`.

## Why the split

Sol is reserved for requirements, decomposition, cross-worker judgment, integration, and final acceptance. Terra handles implementation work at maximum reasoning. Luna handles test, review, exploration, and documentation at maximum reasoning. This keeps the orchestration policy simple and removes duplicate model-profile files.

## Maintenance

GPT-5.6 supports `none`, `low`, `medium`, `high`, `xhigh`, and `max`. Model availability and Codex configuration can change; re-check official OpenAI documentation before changing model IDs or supported effort values.

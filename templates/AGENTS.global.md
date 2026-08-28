# Global Agent Orchestration Policy

For non-trivial software work, inspect the repository and applicable project instructions before delegating.

Use one primary orchestrator for planning, task decomposition, dependency ordering, worker dispatch, review, integration, and final verification. Keep worker delegation one level deep; workers do not spawn subagents.

Roles follow real repository boundaries. Never invent a backend, frontend, test system, documentation system, service, or directory to fit a predefined role.

Every writer gets explicit non-overlapping Allowed Write Paths and Forbidden Write Paths. Read-only workers get an Investigation Scope and required evidence. Parallelize readers and disjoint writers; serialize shared contracts and overlapping writes.

A worker result is not final acceptance. The orchestrator reviews all results and runs fresh integrated verification before completion.

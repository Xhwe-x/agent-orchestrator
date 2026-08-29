# Agent Orchestrator

面向 OpenAI Codex 的仓库感知、Token-aware 多智能体编排 Skill（v1.0.0）。

[English README](README.md)

核心原则：**角色服从真实项目与任务，不为了 Agent 角色去改造项目结构。**

## v1.0.0 核心设计

v1.0.0 明确包含 **1 个不可派发的 Primary Sol Orchestrator**（`orchestrator`，主编排器）和 **恰好 7 个可派发 Worker**：

- `frontend_worker`
- `backend_worker`
- `generic_worker`
- `test_worker`
- `review_worker`
- `explorer_worker`
- `docs_worker`

主编排器负责需求、拆分、路由、集成、实际改动路径审计、最终验证和验收。Worker 不得创建子 Agent 或继续委派。v1 **不会安装 `orchestrator.toml` 自定义 Worker profile**；安装的自定义 Agent 只有上述 7 个 Worker profile。

## Token-aware 行为

- 极小任务仅由主线程处理，不自动扇出 Worker。
- 进行有意义的委派前，主编排器形成紧凑的 Repository Digest，记录所有权、入口、共享契约、验证命令和约束。
- 按真实仓库边界选择 specialist；只有确实存在服务端/API/持久化/后台服务边界时才使用 `backend_worker`。
- 初始派发遵循 manifest 默认值，`max` 绝不是默认值。
- 只有主编排器能在失败或其他证据足够时逐级提升 effort：`medium → high → xhigh → max`；Worker 不自行升级。
- `review_worker` 只用于有风险依据的审查，并记录理由，不对每次修改默认启动。

## 模型与默认 effort

下表与 [`manifest.toml`](manifest.toml) 中的 8 个 `[[roles]]` 条目一致。

| Role | 可派发 | Model | 默认 effort |
|---|---|---|---|
| `orchestrator` | 否 | `gpt-5.6-sol` | `medium` |
| `frontend_worker` | 是 | `gpt-5.6-terra` | `medium` |
| `backend_worker` | 是 | `gpt-5.6-terra` | `medium` |
| `generic_worker` | 是 | `gpt-5.6-terra` | `medium` |
| `test_worker` | 是 | `gpt-5.6-luna` | `high` |
| `review_worker` | 是 | `gpt-5.6-luna` | `high` |
| `explorer_worker` | 是 | `gpt-5.6-luna` | `medium` |
| `docs_worker` | 是 | `gpt-5.6-luna` | `medium` |

机器可读的版本、角色、模型、effort、发布清单统一放在 `manifest.toml`。安装器不会修改或覆盖用户现有的 Codex `config.toml`；主会话模型/effort 仍由用户与当前 runtime 配置决定。

## 安装

请在仓库根目录运行。macOS / Linux 安装器支持 `--check`、`--force` 和 `--uninstall`：

```bash
./scripts/install-codex.sh --check
./scripts/install-codex.sh
```

执行受管安装升级时，先运行带 force 的只读预检查，再执行实际安装：

```bash
./scripts/install-codex.sh --check --force
./scripts/install-codex.sh --force
```

Windows 需要 PowerShell 7 或更高版本（`pwsh`，不支持 Windows PowerShell 5.1），并支持 `-Check`、`-Force` 和 `-Uninstall`：

```powershell
pwsh -File .\scripts\install-codex.ps1 -Check
pwsh -File .\scripts\install-codex.ps1
```

执行受管升级：

```powershell
pwsh -File .\scripts\install-codex.ps1 -Check -Force
pwsh -File .\scripts\install-codex.ps1 -Force
```

`--check` / `-Check` 是只读预检查，绝不修改文件系统。`--force` / `-Force` 不代表取得所有权：只有已验证属于本项目管理的冲突目标才可替换；无主或未验证的冲突即使加 force 也会受到保护。旧版 `orchestrator.toml` 只有在其 SHA-256 匹配 `manifest.toml` 中认可的兼容性指纹后才会迁移；匹配的文件会先备份并停用，未知或用户自有文件会阻断安装。

两个安装器都支持通过 `AGENT_ORCHESTRATOR_HOME` 进行隔离测试。它们把运行时 Skill 安装到 `$HOME/.agents/skills/agent-orchestrator/`，把 7 个 Worker Agent TOML 安装到 `$HOME/.codex/agents/`。这些是用户级全局 Codex 路径，安装后该用户即可全局使用 Skill 和 Worker。安装器不会编辑或覆盖用户的 Codex `config.toml`；主会话模型/effort 仍由 runtime 配置决定。

## 使用

`agents/openai.yaml` 设置 `allow_implicit_invocation=false`，所以 v1 默认关闭隐式调用。安装后请显式调用全局可用的 Skill：

```text
$agent-orchestrator
检查当前仓库，保护已有修改，根据真实模块边界拆分任务；只对独立工作流派发 Worker，审计实际写入路径后统一集成并最终验证。
```

## Codex 配置

[`templates/codex-config.toml`](templates/codex-config.toml) 只提供安全的推荐基线：Sol/`medium` + `[agents].enabled = true` + `max_depth = 1`。`max_depth = 1` 只对 Multi-Agent V1 提供额外的单层防御；当前 Multi-Agent V2 会忽略该深度项，因此严格单层仍以 Skill/Worker 规则和结果审计为准。模板故意不设置全局线程上限，因为当前 Multi-Agent V2 与 legacy/global thread-limit 配置可能冲突。

主 Orchestrator 的 Sol/`medium` 是推荐默认值，不是安装器能强制到已经运行中的会话。若 runtime 能显示当前会话模型/effort，应先确认实际值再声称 canonical 默认已生效。

## 验证

开发验证需要 Python 3.11+：

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -p 'test_*.py' -v
python scripts/verify.py
bash -n scripts/install-codex.sh
git diff --check
```


详细规则见 [`SKILL.md`](SKILL.md)、[`references/orchestration.md`](references/orchestration.md) 和 [`references/agent-contract.md`](references/agent-contract.md)。

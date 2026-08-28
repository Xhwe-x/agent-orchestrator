# Agent Orchestrator

一个精简的、仓库感知型 Codex 多智能体编排 Skill。

核心原则：**角色服从真实项目与任务，不为了 Agent 角色去改造项目结构。**

## 模型分工

- 主 Orchestrator：`gpt-5.6-sol`，默认 `medium`。
- 前端、后端、通用开发 Worker：`gpt-5.6-terra`，默认 `medium`。
- 测试、审查 Worker：`gpt-5.6-luna`，默认 `high`；探索、文档 Worker：`gpt-5.6-luna`，默认 `medium`。

主 Orchestrator 负责需求分析、任务拆分、调度、审查、最终集成和验收。只有主线程可以按 `medium → high → xhigh → max` 梯子升级；Worker 不得自行升级，只能返回升级信号。`max` 仅用于少数高代价、紧耦合问题，绝不是常规默认值。默认禁止嵌套委派。只有主 Orchestrator 可以明确授权某一项具体的嵌套任务；该授权不放宽任何范围、沙箱或自行升级规则。

首次仓库调查应形成紧凑的 Repository Digest（所有权、入口、共享契约、验证命令和重要约束），随任务契约传给 Worker。小型低风险修改由主线程直接审查；仅对高风险修改启动 `review_worker`，并记录理由和推理强度。

`backend_worker` 只用于项目中真实存在的服务端/API/持久化/后台服务边界；没有真实后端的游戏或工具项目应使用 `generic_worker` 或项目自己的领域 Worker，禁止为了角色新建 backend/server。

## Windows 安装

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-codex.ps1
```

## macOS / Linux

```bash
./scripts/install-codex.sh
```

## 使用

```text
$agent-orchestrator
分析当前仓库和项目规则，根据真实模块边界拆分任务；只对独立工作流使用子 Agent，限制写入范围，审查全部结果后由主线程统一集成并最终验证。
```

## 验证

运行本地验证器前，先安装开发验证依赖：

```bash
python -m pip install -r requirements-dev.txt
```

然后运行：

```bash
python scripts/verify.py
```

完整规则见英文 `SKILL.md` 和 `references/`，验收结果见 [GitHub 上的 ACCEPTANCE.md](https://github.com/Xhwe-x/agent-orchestrator/blob/main/ACCEPTANCE.md)。

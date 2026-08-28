# Agent Orchestrator

一个精简的、仓库感知型 Codex 多智能体编排 Skill。

核心原则：**角色服从真实项目与任务，不为了 Agent 角色去改造项目结构。**

## 模型分工

- 主 Orchestrator：`gpt-5.6-sol`，推理强度按项目/任务复杂度选择：A=`medium`、B=`high`、C=`xhigh`、D=`max`。
- 前端、后端、通用开发 Worker：`gpt-5.6-terra` + `max`。
- 测试、审查、探索、文档 Worker：`gpt-5.6-luna` + `max`。

主 Orchestrator 负责需求分析、任务拆分、调度、审查、最终集成和验收。所有 Worker 禁止继续派生子 Agent，保持单层委派。

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

完整规则见英文 `SKILL.md` 和 `references/`，验收结果见 `ACCEPTANCE.md`。

#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = {
    "SKILL.md", "README.md", "README.zh-CN.md", "LICENSE", "ACCEPTANCE.md",
    "agents/openai.yaml",
    "references/orchestration.md", "references/agent-contract.md", "references/models.md", "references/codex.md",
    "templates/AGENTS.global.md", "templates/AGENTS.project.md", "templates/codex-config.toml",
    "examples/web-project.md", "examples/game-project.md", "tests/evals.md",
    "scripts/install-codex.sh", "scripts/install-codex.ps1", ".github/workflows/validate.yml",
}

EXPECTED = {
    "orchestrator": ("workspace-write", "gpt-5.6-sol", None),
    "frontend_worker": ("workspace-write", "gpt-5.6-terra", "max"),
    "backend_worker": ("workspace-write", "gpt-5.6-terra", "max"),
    "generic_worker": ("workspace-write", "gpt-5.6-terra", "max"),
    "test_worker": ("workspace-write", "gpt-5.6-luna", "max"),
    "explorer_worker": ("read-only", "gpt-5.6-luna", "max"),
    "docs_worker": ("read-only", "gpt-5.6-luna", "max"),
    "review_worker": ("read-only", "gpt-5.6-luna", "max"),
}

FORBIDDEN_PROJECT_STRINGS = {"F:/codex项目/官渡密报", "guandu-prototype"}
PLACEHOLDERS = (r"\bTODO\b", r"\bTBD\b", r"\bFIXME\b")
TEXT_SUFFIXES = {".md", ".toml", ".yaml", ".yml", ".py", ".ps1", ".sh"}


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    raise SystemExit(1)


def text_files():
    for p in ROOT.rglob("*"):
        if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES:
            yield p


def verify_structure() -> None:
    missing = sorted(p for p in REQUIRED if not (ROOT / p).is_file())
    if missing:
        fail(f"missing required files: {missing}")
    if (ROOT / "templates/model-profiles").exists():
        fail("duplicate model-profile tree should not exist")
    for redundant in ("CHANGELOG.md", "CONTRIBUTING.md", "references/model-profiles.md"):
        if (ROOT / redundant).exists():
            fail(f"redundant legacy file still present: {redundant}")


def verify_skill() -> None:
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        fail("SKILL.md missing YAML frontmatter")
    fm = m.group(1)
    name = re.search(r"^name:\s*(.+)$", fm, re.M)
    desc = re.search(r"^description:\s*(.+)$", fm, re.M)
    if not name or not desc:
        fail("SKILL.md requires name and description")
    name_v, desc_v = name.group(1).strip(), desc.group(1).strip()
    if not re.fullmatch(r"[A-Za-z0-9-]+", name_v):
        fail(f"invalid skill name: {name_v}")
    if not desc_v.startswith("Use when") or len(desc_v) > 500:
        fail("skill description must start with 'Use when' and stay <=500 chars")
    words = re.findall(r"\b[\w'-]+\b", text[m.end():])
    if len(words) > 520:
        fail(f"SKILL.md too long for frequent loading: {len(words)} words")
    required_phrases = (
        "Workers MUST NOT spawn subagents",
        "backend_worker` is only for an existing real server/API/persistence/backend service boundary",
        "One worker per meaningful independent workstream",
        "Worker completion is evidence, not proof",
    )
    for phrase in required_phrases:
        if phrase not in text:
            fail(f"SKILL.md missing policy: {phrase}")


def verify_agents() -> None:
    agent_dir = ROOT / "templates/codex-agents"
    seen = {}
    for path in sorted(agent_dir.glob("*.toml")):
        with path.open("rb") as fh:
            data = tomllib.load(fh)
        for key in ("name", "description", "developer_instructions", "sandbox_mode", "model"):
            if not data.get(key):
                fail(f"{path.relative_to(ROOT)} missing {key}")
        name = data["name"]
        if name in seen:
            fail(f"duplicate agent name: {name}")
        seen[name] = path
        expected = EXPECTED.get(name)
        if expected is None:
            fail(f"unexpected agent: {name}")
        sandbox, model, effort = expected
        if data["sandbox_mode"] != sandbox or data["model"] != model:
            fail(f"{path.name} has wrong sandbox/model")
        actual_effort = data.get("model_reasoning_effort")
        if actual_effort != effort:
            fail(f"{path.name} reasoning effort expected {effort!r}, got {actual_effort!r}")
        instr = data["developer_instructions"]
        if name != "orchestrator" and "Do not spawn subagents" not in instr:
            fail(f"{path.name} missing no-nested-delegation rule")
    if set(seen) != set(EXPECTED):
        fail(f"agent set mismatch: {sorted(seen)}")

    backend = (agent_dir / "backend-worker.toml").read_text(encoding="utf-8").lower()
    if "backend-equivalent" in backend:
        fail("backend_worker still contains backend-equivalent semantics")
    if "no real backend boundary" not in backend:
        fail("backend_worker must stop when no real backend exists")


def verify_model_policy() -> None:
    text = (ROOT / "references/models.md").read_text(encoding="utf-8")
    for needle in ("`gpt-5.6-sol`", "`gpt-5.6-terra`", "`gpt-5.6-luna`", "`medium`", "`high`", "`xhigh`", "`max`"):
        if needle not in text:
            fail(f"model policy missing {needle}")
    cfg_path = ROOT / "templates/codex-config.toml"
    with cfg_path.open("rb") as fh:
        cfg = tomllib.load(fh)
    if cfg.get("model") != "gpt-5.6-sol":
        fail("codex-config main model must be gpt-5.6-sol")
    if cfg.get("model_reasoning_effort") not in {"medium", "high", "xhigh", "max"}:
        fail("codex-config must use a valid Sol project effort example")
    if cfg.get("agents", {}).get("enabled") is not True:
        fail("codex-config must enable agents")


def verify_text_hygiene() -> None:
    for path in text_files():
        if path.resolve() == Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8")
        for needle in FORBIDDEN_PROJECT_STRINGS:
            if needle in text:
                fail(f"project-specific string leaked into {path.relative_to(ROOT)}")
        if path.name != "verify.py":
            for pattern in PLACEHOLDERS:
                if re.search(pattern, text, re.I):
                    fail(f"placeholder found in {path.relative_to(ROOT)}: {pattern}")


def verify_links() -> None:
    pattern = re.compile(r"\[[^\]]+\]\((?!https?://|mailto:|#)([^)]+)\)")
    for path in ROOT.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        for target in pattern.findall(text):
            target = target.split("#", 1)[0].strip()
            if not target:
                continue
            resolved = (path.parent / target).resolve()
            try:
                resolved.relative_to(ROOT.resolve())
            except ValueError:
                fail(f"link escapes repo in {path.relative_to(ROOT)}: {target}")
            if not resolved.exists():
                fail(f"broken local link in {path.relative_to(ROOT)}: {target}")


def verify_installer_policy() -> None:
    sh = (ROOT / "scripts/install-codex.sh").read_text(encoding="utf-8")
    ps = (ROOT / "scripts/install-codex.ps1").read_text(encoding="utf-8")
    for text, label in ((sh, "shell"), (ps, "PowerShell")):
        if "AGENT_ORCHESTRATOR_HOME" not in text:
            fail(f"{label} installer lacks isolated-home test override")
    if 'cp -R "$ROOT"' in sh or 'Copy-Item -Recurse -Force $Root' in ps:
        fail("installer must not copy the entire GitHub repository into runtime skill")
    for needle in ("SKILL.md", "agents", "references"):
        if needle not in sh or needle not in ps:
            fail(f"installers must copy runtime component: {needle}")


def verify_openai_metadata() -> None:
    text = (ROOT / "agents/openai.yaml").read_text(encoding="utf-8")
    for needle in ("interface:", "display_name:", "short_description:", "default_prompt:", "policy:", "allow_implicit_invocation:"):
        if needle not in text:
            fail(f"agents/openai.yaml missing {needle}")


def main() -> int:
    verify_structure()
    verify_skill()
    verify_agents()
    verify_model_policy()
    verify_text_hygiene()
    verify_links()
    verify_installer_policy()
    verify_openai_metadata()
    print("PASS: structure, skill metadata, model split, agent contracts, backend semantics, links, portability, and installer policy")
    return 0


if __name__ == "__main__":
    sys.exit(main())

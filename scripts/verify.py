#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import os
import re
import stat
import subprocess
import sys
import tempfile
import tomllib
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = {
    ".gitattributes",
    ".gitignore",
    "HANDOFF.md",
    "AGENTS.md",
    "SKILL.md",
    "README.md",
    "README.zh-CN.md",
    "LICENSE",
    "ACCEPTANCE.md",
    "requirements-dev.txt",
    "agents/openai.yaml",
    "references/orchestration.md",
    "references/agent-contract.md",
    "references/models.md",
    "references/codex.md",
    "templates/AGENTS.global.md",
    "templates/AGENTS.project.md",
    "templates/codex-config.toml",
    "examples/web-project.md",
    "examples/game-project.md",
    "tests/evals.md",
    "scripts/install-codex.sh",
    "scripts/install-codex.ps1",
    ".github/workflows/validate.yml",
    ".codex/agents/docs-worker.toml",
    ".codex/agents/test-worker.toml",
}

EXPECTED = {
    "orchestrator": ("workspace-write", "gpt-5.6-sol", "medium"),
    "frontend_worker": ("workspace-write", "gpt-5.6-terra", "medium"),
    "backend_worker": ("workspace-write", "gpt-5.6-terra", "medium"),
    "generic_worker": ("workspace-write", "gpt-5.6-terra", "medium"),
    "test_worker": ("workspace-write", "gpt-5.6-luna", "high"),
    "explorer_worker": ("read-only", "gpt-5.6-luna", "medium"),
    "docs_worker": ("read-only", "gpt-5.6-luna", "medium"),
    "review_worker": ("read-only", "gpt-5.6-luna", "high"),
}

VALID_MODELS = {"gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"}
VALID_EFFORTS = {"medium", "high", "xhigh", "max"}
POLICY_MARKERS = {
    "AGENTS.md": (
        "Small local changes stay in the primary thread.",
        "Repository Digest",
        "Only the primary orchestrator may authorize a retry or re-dispatch at a higher reasoning effort.",
        "`review_worker` is risk-based, not automatic.",
        "`backend_worker` is only for a real existing server/API/persistence/backend-service boundary.",
    ),
    "SKILL.md": (
        "Nested delegation is prohibited by default. Only the primary orchestrator may explicitly authorize a specific nested task",
        "One worker per meaningful independent workstream",
        "Only the orchestrator controls `medium → high → xhigh → max`",
        "The first investigation produces a compact Repository Digest",
        "use `review_worker` only for elevated-risk changes",
    ),
    "references/orchestration.md": (
        "Repository Digest",
        "The primary orchestrator alone controls one ladder:",
        "medium → high → xhigh → max",
        "Workers never self-escalate reasoning effort.",
        "generic_worker` may be retried at `high` for a hard problem that remains fully in scope.",
        "it stops and reports for the orchestrator instead.",
        "Launch a `review_worker` only for elevated-risk changes",
    ),
    "references/agent-contract.md": (
        "Every worker returns this compact format.",
        "Workers never change their own model or reasoning effort.",
        "A scope or architecture change is a stop-and-report condition",
    ),
}
COMPACT_RETURN_HEADINGS = ("RESULT", "FILES", "VERIFICATION", "RISKS", "ESCALATION")
PROJECT_PROFILES = {
    "docs-worker.toml": {
        "name": "docs_worker",
        "model": "gpt-5.6-luna",
        "effort": "medium",
        "sandbox": "read-only",
        "scope": ("项目相对的", "references/", "只能核对"),
    },
    "test-worker.toml": {
        "name": "test_worker",
        "model": "gpt-5.6-luna",
        "effort": "high",
        "sandbox": "workspace-write",
        "scope": ("项目相对的", "tests/", "只能"),
    },
}

RELEASE_ARCHIVE = "agent-orchestrator-v0.3-token-aware.zip"
RELEASE_ROOT = "agent-orchestrator-v0.3-token-aware"
RELEASE_DIGEST_EXCLUDES = {"ACCEPTANCE.md"}
RELEASE_FIXED_TIME = (1980, 1, 1, 0, 0, 0)
RELEASE_EXCLUDED_DIRS = {
    ".git",
    ".worktrees",
    "worktrees",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
RELEASE_EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".zip"}
RELEASE_REQUIRED_INCLUSIONS = {"ACCEPTANCE.md", "HANDOFF.md", "requirements-dev.txt", "scripts/install-codex.sh"}

FORBIDDEN_PROJECT_STRINGS = {"F:/codex项目/官渡密报", "guandu-prototype"}
PLACEHOLDERS = (r"\bTODO\b", r"\bTBD\b", r"\bFIXME\b")
TEXT_SUFFIXES = {".md", ".toml", ".yaml", ".yml", ".py", ".ps1", ".sh"}


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    raise SystemExit(1)


def load_toml(path: Path):
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        fail(f"invalid TOML in {path.relative_to(ROOT)}: {exc}")


def load_yaml(path: Path):
    try:
        import yaml
    except ModuleNotFoundError:
        fail("YAML verification requires PyYAML; install with python -m pip install -r requirements-dev.txt")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        fail(f"invalid YAML in {path.relative_to(ROOT)}: {exc}")
    if not isinstance(data, dict):
        fail(f"YAML document must be a mapping: {path.relative_to(ROOT)}")
    return data


def text_files():
    for path in ROOT.rglob("*"):
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES and ".git" not in path.parts:
            yield path


def verify_structure() -> None:
    missing = sorted(path for path in REQUIRED if not (ROOT / path).is_file())
    if missing:
        fail(f"missing required files: {missing}")
    if (ROOT / "templates/model-profiles").exists():
        fail("duplicate model-profile tree should not exist")
    for redundant in ("CHANGELOG.md", "CONTRIBUTING.md", "references/model-profiles.md"):
        if (ROOT / redundant).exists():
            fail(f"redundant legacy file still present: {redundant}")
    acceptance_files = [
        path for path in ROOT.rglob("ACCEPTANCE.md") if ".git" not in path.parts and not _release_path_excluded(path)
    ]
    if acceptance_files != [ROOT / "ACCEPTANCE.md"]:
        fail(f"exactly one root ACCEPTANCE.md is allowed, found: {[str(p.relative_to(ROOT)) for p in acceptance_files]}")


def verify_skill() -> None:
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not match:
        fail("SKILL.md missing YAML frontmatter")
    frontmatter = match.group(1)
    name = re.search(r"^name:\s*(.+)$", frontmatter, re.M)
    desc = re.search(r"^description:\s*(.+)$", frontmatter, re.M)
    if not name or not desc:
        fail("SKILL.md requires name and description")
    name_value, desc_value = name.group(1).strip(), desc.group(1).strip()
    if not re.fullmatch(r"[A-Za-z0-9-]+", name_value):
        fail(f"invalid skill name: {name_value}")
    if not desc_value.startswith("Use when") or len(desc_value) > 500:
        fail("skill description must start with 'Use when' and stay <=500 chars")
    words = re.findall(r"\b[\w'-]+\b", text[match.end():])
    if len(words) > 520:
        fail(f"SKILL.md too long for frequent loading: {len(words)} words")
    required_phrases = (
        "Nested delegation is prohibited by default. Only the primary orchestrator may explicitly authorize a specific nested task",
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
        data = load_toml(path)
        for key in ("name", "description", "developer_instructions", "sandbox_mode", "model"):
            if not data.get(key):
                fail(f"{path.relative_to(ROOT)} missing {key}")
        name = data["name"]
        if not isinstance(name, str):
            fail(f"{path.relative_to(ROOT)} has a non-string agent name")
        if name in seen:
            fail(f"duplicate agent name: {name}")
        seen[name] = path
        expected = EXPECTED.get(name)
        if expected is None:
            fail(f"unexpected agent: {name}")
        sandbox, model, effort = expected
        actual_model = data["model"]
        if not isinstance(actual_model, str) or actual_model not in VALID_MODELS:
            fail(f"{path.name} has invalid model: {actual_model!r}")
        if data["sandbox_mode"] != sandbox or actual_model != model:
            fail(f"{path.name} has wrong sandbox/model")
        actual_effort = data.get("model_reasoning_effort")
        if not isinstance(actual_effort, str) or actual_effort not in VALID_EFFORTS:
            fail(f"{path.name} has invalid reasoning effort: {actual_effort!r}")
        if actual_effort == "max":
            fail(f"{path.name} must not use max as its default reasoning effort")
        if actual_effort != effort:
            fail(f"{path.name} reasoning effort expected {effort!r}, got {actual_effort!r}")
        instructions = data["developer_instructions"]
        if name == "orchestrator":
            for marker in (
                "Keep small local changes in the primary thread.",
                "Repository Digest",
                "dispatch review_worker only when elevated risk",
                "Workers do not self-escalate reasoning effort",
            ):
                if marker not in instructions:
                    fail(f"{path.name} missing orchestrator policy marker: {marker}")
        else:
            if not re.search(r"\bdo not self-escalate\b", instructions, re.I):
                fail(f"{path.name} missing worker rule: do not self-escalate")
            if "Do not spawn subagents" not in instructions:
                fail(f"{path.name} missing worker rule: Do not spawn subagents")
    if set(seen) != set(EXPECTED):
        fail(f"agent set mismatch: {sorted(seen)}")

    backend = (agent_dir / "backend-worker.toml").read_text(encoding="utf-8").lower()
    if "backend-equivalent" in backend:
        fail("backend_worker still contains backend-equivalent semantics")
    if "no real backend boundary" not in backend:
        fail("backend_worker must stop when no real backend exists")


def verify_project_profiles() -> None:
    profile_dir = ROOT / ".codex/agents"
    for filename, expected in PROJECT_PROFILES.items():
        path = profile_dir / filename
        data = load_toml(path)
        if data.get("name") != expected["name"]:
            fail(f"{path.relative_to(ROOT)} has wrong role")
        model = data.get("model")
        if model not in VALID_MODELS or model != expected["model"]:
            fail(f"{path.relative_to(ROOT)} has wrong or invalid model")
        effort = data.get("model_reasoning_effort")
        if effort not in VALID_EFFORTS or effort != expected["effort"]:
            fail(f"{path.relative_to(ROOT)} has wrong or invalid reasoning effort")
        if data.get("sandbox_mode") != expected["sandbox"]:
            fail(f"{path.relative_to(ROOT)} has wrong sandbox mode")
        instructions = data.get("developer_instructions")
        if not isinstance(instructions, str):
            fail(f"{path.relative_to(ROOT)} is missing developer instructions")
        for marker in expected["scope"]:
            if marker not in instructions:
                fail(f"{path.relative_to(ROOT)} missing project-relative scope marker: {marker}")


def verify_model_policy() -> None:
    text = (ROOT / "references/models.md").read_text(encoding="utf-8")
    for needle in ("`gpt-5.6-sol`", "`gpt-5.6-terra`", "`gpt-5.6-luna`", "`medium`", "`high`", "`xhigh`", "`max`"):
        if needle not in text:
            fail(f"model policy missing {needle}")
    for role, (_, model, effort) in EXPECTED.items():
        row = re.compile(
            rf"^\|\s*`{re.escape(role)}`\s*\|\s*`{re.escape(model)}`\s*\|\s*`{re.escape(effort)}`\s*\|$",
            re.M,
        )
        if not row.search(text):
            fail(f"model policy mapping missing or incorrect for {role}")
    config = load_toml(ROOT / "templates/codex-config.toml")
    if config.get("model") not in VALID_MODELS:
        fail("codex-config main model is not a valid GPT-5.6 model")
    if config.get("model") != "gpt-5.6-sol":
        fail("codex-config main model must be gpt-5.6-sol")
    if config.get("model_reasoning_effort") != "medium":
        fail("codex-config main reasoning effort must default to medium")
    if config.get("agents", {}).get("enabled") is not True:
        fail("codex-config must enable agents")


def verify_policy() -> None:
    for relative, markers in POLICY_MARKERS.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                fail(f"{relative} missing v0.3 policy marker: {marker}")

    contract = (ROOT / "references/agent-contract.md").read_text(encoding="utf-8")
    for heading in COMPACT_RETURN_HEADINGS:
        if not re.search(rf"(?m)^{re.escape(heading)}$", contract):
            fail(f"agent contract missing compact return heading: {heading}")

    generic = (ROOT / "templates/codex-agents/generic-worker.toml").read_text(encoding="utf-8")
    for marker in (
        "hard but remains completely inside the assigned scope",
        "retry at high effort",
        "missing ownership, architecture changes",
        "stop and report instead of retrying via more effort",
    ):
        if marker not in generic:
            fail(f"generic-worker.toml missing retry/stop distinction: {marker}")


def verify_yaml() -> None:
    metadata = load_yaml(ROOT / "agents/openai.yaml")
    interface = metadata.get("interface")
    policy = metadata.get("policy")
    if not isinstance(interface, dict) or not isinstance(policy, dict):
        fail("agents/openai.yaml must define interface and policy mappings")
    if policy.get("allow_implicit_invocation") is not True:
        fail("agents/openai.yaml must allow implicit invocation")

    workflow = load_yaml(ROOT / ".github/workflows/validate.yml")
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict) or not {"linux", "windows"}.issubset(jobs):
        fail("validate.yml must define linux and windows jobs")
    for job_name in ("linux", "windows"):
        steps = jobs[job_name].get("steps") if isinstance(jobs[job_name], dict) else None
        if not isinstance(steps, list) or not steps:
            fail(f"validate.yml {job_name} job must define a nonempty steps list")
        step_names = {step.get("name") for step in steps if isinstance(step, dict)}
        if not {"Build release archive", "Verify release archive"}.issubset(step_names):
            fail(f"validate.yml {job_name} job must build and verify the release archive")


def _acceptance_text() -> tuple[str, str]:
    text = (ROOT / "ACCEPTANCE.md").read_text(encoding="utf-8")
    return text, re.sub(r"[*_`]", "", text)


def _acceptance_release_metadata() -> tuple[int, str]:
    _, normalized = _acceptance_text()
    count_match = re.search(
        r"(?im)^\s*(?:[-+]\s*)?[^\n:]*package\s+file\s+count[^\n:]*:\s*(\d+)(?:\s+files?)?.*$",
        normalized,
    )
    if not count_match or int(count_match.group(1)) <= 0:
        fail("ACCEPTANCE.md must list a positive package file count")
    sha_match = re.search(
        r"(?im)^\s*(?:[-+]\s*)?[^\n:]*release\s+content\s+sha[- ]?256[^\n:]*:\s*([0-9a-f]{64}).*$",
        normalized,
    )
    if not sha_match:
        fail("ACCEPTANCE.md must list a 64-character Release content SHA-256")
    return int(count_match.group(1)), sha_match.group(1).lower()


def verify_acceptance_static() -> None:
    text, normalized = _acceptance_text()
    if not re.search(r"(?im)^#\s+v0\.3(?:\.\d+)?\b", normalized):
        fail("ACCEPTANCE.md must identify the v0.3 release")
    if not re.search(r"(?im)^\s*#+\s*.*changed files.*$", normalized):
        fail("ACCEPTANCE.md must include a Changed files section")
    if not re.search(r"(?im)^\s*#+\s*.*verification evidence.*$", normalized):
        fail("ACCEPTANCE.md must include a Verification evidence section")
    if not re.search(r"(?im)^\s*#+\s*.*environment limitations.*$", normalized):
        fail("ACCEPTANCE.md must include an Environment limitations section")
    if not re.search(r"(?im)^\s*#+\s*.*static validation.*$", normalized):
        fail("ACCEPTANCE.md must distinguish a static validation section")
    manual = re.search(r"(?im)^\s*#+\s*.*manual.*Codex.*behavior.*check", normalized)
    if not manual:
        fail("ACCEPTANCE.md must distinguish manual Codex behavior checks")
    manual_text = normalized[manual.start():]
    if not re.search(r"(?i)\b(?:not executed|unexecuted|not run|not claimed)\b", manual_text):
        fail("ACCEPTANCE.md must mark manual Codex behavior checks as unexecuted")
    if RELEASE_ARCHIVE not in normalized:
        fail(f"ACCEPTANCE.md must reference {RELEASE_ARCHIVE}")
    if "HANDOFF.md" not in text:
        fail("ACCEPTANCE.md must explicitly account for HANDOFF.md in the final package")
    if "ACCEPTANCE.md" not in text:
        fail("ACCEPTANCE.md must explicitly account for its own package inclusion")
    _acceptance_release_metadata()


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
        if ".git" in path.parts:
            continue
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
    shell = (ROOT / "scripts/install-codex.sh").read_text(encoding="utf-8")
    powershell = (ROOT / "scripts/install-codex.ps1").read_text(encoding="utf-8")
    for text, label in ((shell, "shell"), (powershell, "PowerShell")):
        if "AGENT_ORCHESTRATOR_HOME" not in text:
            fail(f"{label} installer lacks isolated-home test override")
    if 'cp -R "$ROOT"' in shell or 'Copy-Item -Recurse -Force $Root' in powershell:
        fail("installer must not copy the entire GitHub repository into runtime skill")
    for needle in ("SKILL.md", "agents", "references"):
        if needle not in shell or needle not in powershell:
            fail(f"installers must copy runtime component: {needle}")


def verify_openai_metadata() -> None:
    text = (ROOT / "agents/openai.yaml").read_text(encoding="utf-8")
    for needle in ("interface:", "display_name:", "short_description:", "default_prompt:", "policy:", "allow_implicit_invocation:"):
        if needle not in text:
            fail(f"agents/openai.yaml missing {needle}")


def _release_path_excluded(path: Path) -> bool:
    try:
        relative = path.relative_to(ROOT)
    except ValueError:
        return True
    if any(part in RELEASE_EXCLUDED_DIRS for part in relative.parts[:-1]):
        return True
    if path.suffix.lower() in RELEASE_EXCLUDED_SUFFIXES:
        return True
    if path.name in {".DS_Store"}:
        return True
    return False


def _safe_release_relative(relative: str) -> str:
    if not relative or "\\" in relative or "\x00" in relative:
        fail(f"unsafe release path: {relative!r}")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        fail(f"unsafe release path: {relative!r}")
    if any(ord(char) < 32 for char in relative):
        fail(f"release path contains control characters: {relative!r}")
    normalized = pure.as_posix()
    if normalized != relative:
        fail(f"non-canonical release path: {relative!r}")
    return normalized


def _canonical_release_mode(relative: str) -> int:
    return 0o755 if relative == "scripts/install-codex.sh" else 0o644


def release_entries() -> dict[str, tuple[bytes, int]]:
    entries: dict[str, tuple[bytes, int]] = {}
    ambiguous: dict[str, str] = {}
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or _release_path_excluded(path):
            continue
        relative = _safe_release_relative(path.relative_to(ROOT).as_posix())
        ambiguity_key = unicodedata.normalize("NFC", relative).casefold()
        previous = ambiguous.get(ambiguity_key)
        if previous is not None and previous != relative:
            fail(f"ambiguous release paths: {previous!r} and {relative!r}")
        ambiguous[ambiguity_key] = relative
        if relative in entries:
            fail(f"duplicate release path: {relative}")
        entries[relative] = (path.read_bytes(), _canonical_release_mode(relative))
    missing = sorted(RELEASE_REQUIRED_INCLUSIONS - set(entries))
    if missing:
        fail(f"release manifest missing required files: {missing}")
    return entries


def release_content_sha256(entries: dict[str, tuple[bytes, int]]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(entries):
        if relative in RELEASE_DIGEST_EXCLUDES:
            continue
        data, mode = entries[relative]
        path_bytes = relative.encode("utf-8")
        digest.update(len(path_bytes).to_bytes(4, "big"))
        digest.update(path_bytes)
        digest.update(mode.to_bytes(2, "big"))
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def verify_release_gate(entries: dict[str, tuple[bytes, int]] | None = None) -> tuple[int, str]:
    entries = entries or release_entries()
    expected_count = len(entries)
    expected_sha = release_content_sha256(entries)
    acceptance_count, acceptance_sha = _acceptance_release_metadata()
    if acceptance_count != expected_count:
        fail(f"ACCEPTANCE.md package file count mismatch: expected {expected_count}, got {acceptance_count}")
    if acceptance_sha != expected_sha:
        fail(f"ACCEPTANCE.md Release content SHA-256 mismatch: expected {expected_sha}, got {acceptance_sha}")
    print(f"PASS: local release gate count={expected_count} content_sha256={expected_sha}")
    return expected_count, expected_sha


def build_release_archive(output: Path, entries: dict[str, tuple[bytes, int]] | None = None) -> None:
    entries = entries or release_entries()
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    temporary.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for relative in sorted(entries):
                data, mode = entries[relative]
                info = zipfile.ZipInfo(f"{RELEASE_ROOT}/{relative}", date_time=RELEASE_FIXED_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | mode) << 16
                archive.writestr(info, data)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    archive_sha = hashlib.sha256(output.read_bytes()).hexdigest()
    print(f"PASS: built release archive path={output} files={len(entries)} sha256={archive_sha}")


def _archive_relative_name(name: str) -> str:
    if "\\" in name or "\x00" in name:
        fail(f"unsafe archive member: {name!r}")
    pure = PurePosixPath(name)
    if pure.is_absolute() or len(pure.parts) < 2 or pure.parts[0] != RELEASE_ROOT:
        fail(f"archive member must be under {RELEASE_ROOT}/: {name!r}")
    relative = PurePosixPath(*pure.parts[1:]).as_posix()
    return _safe_release_relative(relative)


def _run_extracted_self_check(extracted_root: Path) -> None:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    commands = (
        [sys.executable, "scripts/verify.py"],
        [sys.executable, "scripts/verify.py", "--release"],
    )
    for command in commands:
        completed = subprocess.run(
            command,
            cwd=extracted_root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if completed.returncode != 0:
            output = completed.stdout.strip()
            fail(f"extracted self-check failed ({' '.join(command)}):\n{output}")


def verify_release_archive(archive_path: Path, entries: dict[str, tuple[bytes, int]] | None = None) -> None:
    entries = entries or release_entries()
    archive_path = archive_path.expanduser().resolve()
    if not archive_path.is_file():
        fail(f"release archive is missing: {archive_path}")

    seen: set[str] = set()
    ambiguous: dict[str, str] = {}
    with zipfile.ZipFile(archive_path) as archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        if len(infos) != len(archive.infolist()):
            fail("release archive must contain files only; directory entries are not allowed")
        for info in infos:
            relative = _archive_relative_name(info.filename)
            if relative in seen:
                fail(f"duplicate archive member: {relative}")
            seen.add(relative)
            ambiguity_key = unicodedata.normalize("NFC", relative).casefold()
            previous = ambiguous.get(ambiguity_key)
            if previous is not None and previous != relative:
                fail(f"ambiguous archive members: {previous!r} and {relative!r}")
            ambiguous[ambiguity_key] = relative
            if info.flag_bits & 0x1:
                fail(f"encrypted archive member is not allowed: {relative}")
            unix_mode = (info.external_attr >> 16) & 0xFFFF
            if not stat.S_ISREG(unix_mode):
                fail(f"non-regular archive member is not allowed: {relative}")
            expected = entries.get(relative)
            if expected is None:
                fail(f"unexpected archive member: {relative}")
            expected_data, expected_mode = expected
            actual_mode = unix_mode & 0o777
            if actual_mode != expected_mode:
                fail(f"archive mode mismatch for {relative}: expected {expected_mode:o}, got {actual_mode:o}")
            if archive.read(info) != expected_data:
                fail(f"archive bytes mismatch for {relative}")
        missing = sorted(set(entries) - seen)
        if missing:
            fail(f"archive is missing release members: {missing}")

        with tempfile.TemporaryDirectory(prefix="agent-orchestrator-release-") as temp_dir:
            destination = Path(temp_dir)
            for info in infos:
                relative = _archive_relative_name(info.filename)
                target = destination / RELEASE_ROOT / Path(relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(info))
                target.chmod(entries[relative][1])
            extracted_root = destination / RELEASE_ROOT
            _run_extracted_self_check(extracted_root)

    archive_sha = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    print(f"PASS: release archive verified files={len(entries)} shell_mode=100755 sha256={archive_sha}")


def run_static_checks() -> None:
    verify_structure()
    verify_skill()
    verify_agents()
    verify_project_profiles()
    verify_model_policy()
    verify_policy()
    verify_text_hygiene()
    verify_links()
    verify_installer_policy()
    verify_openai_metadata()
    verify_yaml()
    verify_acceptance_static()
    print("PASS: structure, skill metadata, model split, agent contracts, backend semantics, links, portability, and installer policy")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify and package the Agent Orchestrator skill.")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--release", action="store_true", help="verify local release manifest/count/content digest against ACCEPTANCE.md")
    modes.add_argument("--build-release-archive", metavar="PATH", type=Path, help="build a deterministic GitHub-ready release ZIP")
    modes.add_argument("--release-archive", metavar="PATH", type=Path, help="verify archive safety, bytes, modes, and extracted self-checks")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    run_static_checks()
    if args.release:
        verify_release_gate()
    elif args.build_release_archive is not None:
        entries = release_entries()
        verify_release_gate(entries)
        build_release_archive(args.build_release_archive, entries)
    elif args.release_archive is not None:
        entries = release_entries()
        verify_release_gate(entries)
        verify_release_archive(args.release_archive, entries)
    return 0


if __name__ == "__main__":
    sys.exit(main())

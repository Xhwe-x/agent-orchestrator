#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import io
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
RELEASE_FIXED_TIME = (1980, 1, 1, 0, 0, 0)
RUNTIME_CRITICAL = {
    "SKILL.md",
    "agents/openai.yaml",
    "references/orchestration.md",
    "references/agent-contract.md",
    "references/models.md",
    "references/codex.md",
    "templates/AGENTS.global.md",
    "templates/AGENTS.project.md",
    "templates/codex-config.toml",
    "scripts/install-codex.sh",
    "scripts/install-codex.ps1",
}
PRIVATE_PATH_PATTERNS = (
    re.compile(r"(?i)\b[A-Z]:[\\/](?:Users|Documents and Settings|Desktop)[\\/][^\s`'\"]+"),
    re.compile(r"/(?:Users|home)/[^/\s`'\"]+/"),
)
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
)


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    raise SystemExit(1)


def load_toml(path: Path) -> dict:
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError:
        fail(f"missing TOML file: {path.relative_to(ROOT) if path.is_absolute() else path}")
    except tomllib.TOMLDecodeError as exc:
        fail(f"invalid TOML in {path}: {exc}")
    if not isinstance(data, dict):
        fail(f"TOML document must be a table: {path}")
    return data


def load_yaml(path: Path) -> dict:
    try:
        import yaml
    except ModuleNotFoundError:
        fail("YAML verification requires PyYAML; install requirements-dev.txt")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        fail(f"invalid YAML in {path}: {exc}")
    if not isinstance(data, dict):
        fail(f"YAML document must be a mapping: {path}")
    return data


def load_manifest() -> dict:
    manifest = load_toml(ROOT / "manifest.toml")
    for section in ("project", "policy", "release"):
        if not isinstance(manifest.get(section), dict):
            fail(f"manifest.toml missing [{section}] table")
    roles = manifest.get("roles")
    if not isinstance(roles, list) or not roles:
        fail("manifest.toml must define [[roles]] entries")
    return manifest


def manifest_facts() -> tuple[dict, dict[str, dict]]:
    manifest = load_manifest()
    roles: dict[str, dict] = {}
    for role in manifest["roles"]:
        if not isinstance(role, dict):
            fail("manifest role must be a table")
        name = role.get("name")
        if not isinstance(name, str) or not name:
            fail("manifest role missing name")
        if name in roles:
            fail(f"duplicate manifest role: {name}")
        roles[name] = role
    return manifest, roles


def verify_manifest() -> None:
    manifest, roles = manifest_facts()
    project = manifest["project"]
    policy = manifest["policy"]
    release = manifest["release"]
    compatibility = manifest.get("compatibility")

    if project.get("name") != "agent-orchestrator":
        fail("manifest project name must be agent-orchestrator")
    version = str(project.get("version", ""))
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        fail("manifest project version must be semver-like x.y.z")
    if project.get("python_min") != "3.11":
        fail("development verifier minimum Python must be 3.11")
    if policy.get("delegation_depth") != 1:
        fail("v1 delegation depth must be exactly 1")
    if policy.get("allow_implicit_invocation") is not False:
        fail("v1 implicit invocation must default to false")
    if policy.get("effort_ladder") != ["medium", "high", "xhigh", "max"]:
        fail("manifest effort ladder must be medium -> high -> xhigh -> max")
    if len(roles) != 8:
        fail(f"manifest must define exactly 8 logical roles, got {len(roles)}")
    primary = roles.get("orchestrator")
    if not isinstance(primary, dict) or primary.get("dispatchable") is not False or "profile" in primary:
        fail("primary orchestrator must be non-dispatchable and must not expose a custom Agent profile")
    dispatchable = [role for role in roles.values() if role.get("dispatchable") is True]
    if len(dispatchable) != 7:
        fail(f"manifest must define exactly 7 dispatchable worker roles, got {len(dispatchable)}")

    effort_ladder = policy["effort_ladder"]
    for name, role in roles.items():
        for key in ("model", "effort", "sandbox"):
            if not isinstance(role.get(key), str) or not role[key]:
                fail(f"manifest role {name} missing {key}")
        if role["effort"] not in effort_ladder or role["effort"] == effort_ladder[-1]:
            fail(f"manifest role {name} has invalid default effort {role['effort']!r}")
        if role.get("dispatchable") is True:
            profile = role.get("profile")
            if not isinstance(profile, str) or not profile or not (ROOT / profile).is_file():
                fail(f"dispatchable manifest role {name} has missing profile: {profile!r}")

    if not isinstance(compatibility, dict):
        fail("manifest.toml missing [compatibility] table")
    legacy_hashes = compatibility.get("legacy_orchestrator_sha256")
    if not isinstance(legacy_hashes, list) or not legacy_hashes:
        fail("manifest compatibility legacy_orchestrator_sha256 must be a non-empty array")
    if len(set(legacy_hashes)) != len(legacy_hashes):
        fail("manifest compatibility fingerprints must be unique")
    for fingerprint in legacy_hashes:
        if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            fail(f"invalid legacy orchestrator compatibility fingerprint: {fingerprint!r}")

    archive = release.get("archive")
    release_root = release.get("root")
    expected_root = f"agent-orchestrator-v{version}"
    if archive != f"{expected_root}.zip" or release_root != expected_root:
        fail("release archive/root must derive from manifest project.version")
    for key in ("include", "executable", "digest_excludes"):
        value = release.get(key)
        if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
            fail(f"manifest [release].{key} must be a string array")
        if len(set(value)) != len(value):
            fail(f"manifest [release].{key} must not contain duplicates")
    if not release["include"]:
        fail("manifest [release].include must not be empty")
    include_set = set(release["include"] )
    for key in ("executable", "digest_excludes"):
        unknown = sorted(set(release[key]) - include_set)
        if unknown:
            fail(f"manifest [release].{key} contains paths outside include: {unknown}")
    for relative in release["include"]:
        if any(char in relative for char in "*?[]"):
            fail(f"release include must be an exact file path, not a glob: {relative}")
        _safe_release_relative(relative)
        if not (ROOT / relative).is_file():
            fail(f"release include file is missing: {relative}")


def verify_structure() -> None:
    required = {
        "manifest.toml",
        "AGENTS.md",
        "SKILL.md",
        "README.md",
        "README.zh-CN.md",
        "LICENSE",
        "ACCEPTANCE.md",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "requirements-dev.txt",
        "agents/openai.yaml",
        "references/orchestration.md",
        "references/agent-contract.md",
        "references/models.md",
        "references/codex.md",
        "templates/AGENTS.global.md",
        "templates/AGENTS.project.md",
        "templates/codex-config.toml",
        "tests/evals.md",
        "scripts/install-codex.sh",
        "scripts/install-codex.ps1",
        ".github/workflows/validate.yml",
        ".codex/agents/docs-worker.toml",
        ".codex/agents/test-worker.toml",
    }
    missing = sorted(path for path in required if not (ROOT / path).is_file())
    if missing:
        fail(f"missing required files: {missing}")
    if (ROOT / "HANDOFF.md").exists():
        fail("obsolete HANDOFF.md should not remain in v1 source")
    if (ROOT / "templates/model-profiles").exists():
        fail("duplicate model-profile tree should not exist")


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
    if name.group(1).strip() != "agent-orchestrator":
        fail("SKILL.md skill name mismatch")
    description = desc.group(1).strip()
    if not description.startswith("Use when") or len(description) > 500:
        fail("skill description must start with 'Use when' and stay <=500 chars")
    words = re.findall(r"\b[\w'-]+\b", text[match.end():])
    if len(words) > 560:
        fail(f"SKILL.md too long for frequent loading: {len(words)} words")
    for marker in (
        "The delegation graph is exactly one level deep.",
        "Never revert, clean, reset, or overwrite pre-existing user changes unless explicitly requested.",
        "Audit each writer's actual changed paths",
        "Worker completion is evidence, not proof",
    ):
        if marker not in text:
            fail(f"SKILL.md missing v1 hard rule: {marker}")


def verify_agents() -> None:
    _, roles = manifest_facts()
    primary = roles["orchestrator"]
    if primary.get("dispatchable") is not False or "profile" in primary:
        fail("primary orchestrator must not be a dispatchable custom Agent")

    seen: set[str] = set()
    for name, role in roles.items():
        if role.get("dispatchable") is not True:
            continue
        profile = role.get("profile")
        if not isinstance(profile, str) or not profile:
            fail(f"dispatchable role {name} missing profile")
        path = ROOT / profile
        data = load_toml(path)
        for key in ("name", "description", "developer_instructions", "sandbox_mode", "model", "model_reasoning_effort"):
            if not data.get(key):
                fail(f"{profile} missing {key}")
        if data["name"] != name:
            fail(f"{profile} name mismatch")
        if name in seen:
            fail(f"duplicate agent name: {name}")
        seen.add(name)
        if data["model"] != role["model"] or data["sandbox_mode"] != role["sandbox"]:
            fail(f"{profile} model/sandbox drifted from manifest")
        if data["model_reasoning_effort"] != role["effort"]:
            fail(f"{profile} effort drifted from manifest")
        if data["model_reasoning_effort"] == "max":
            fail(f"{profile} must not default to max")
        instructions = data["developer_instructions"]
        if not re.search(r"\bdo not self-escalate\b", instructions, re.I):
            fail(f"{profile} missing self-escalation prohibition")
        if "Do not spawn subagents or delegate further" not in instructions:
            fail(f"{profile} missing strict one-level delegation rule")
        if re.search(r"authoriz\w*.*nested|nested.*authoriz", instructions, re.I | re.S):
            fail(f"{profile} reintroduced a nested-delegation authorization path")
        if not re.search(r"untrusted.*(?:data|content)|prompt injection", instructions, re.I | re.S):
            fail(f"{profile} missing untrusted-content / prompt-injection boundary")
        if role["sandbox"] == "workspace-write":
            for marker in ("Protected Existing Changes", "CHANGED_PATHS"):
                if marker not in instructions:
                    fail(f"{profile} missing writer audit marker: {marker}")
        else:
            if not re.search(r"read-only|read only", instructions, re.I):
                fail(f"{profile} missing logical read-only rule")

    if len(seen) != 7:
        fail(f"expected exactly 7 dispatchable Agent profiles, got {len(seen)}")
    backend = (ROOT / roles["backend_worker"]["profile"]).read_text(encoding="utf-8").lower()
    if "no real backend boundary" not in backend:
        fail("backend_worker must stop when no real backend exists")

def verify_project_profiles() -> None:
    _, roles = manifest_facts()
    expected_files = {
        "docs-worker.toml": "docs_worker",
        "test-worker.toml": "test_worker",
    }
    for filename, role_name in expected_files.items():
        path = ROOT / ".codex/agents" / filename
        data = load_toml(path)
        role = roles[role_name]
        if data.get("name") != role_name or data.get("model") != role["model"]:
            fail(f"{path.relative_to(ROOT)} role/model mismatch")
        if data.get("model_reasoning_effort") != role["effort"] or data.get("sandbox_mode") != role["sandbox"]:
            fail(f"{path.relative_to(ROOT)} effort/sandbox mismatch")
        instructions = data.get("developer_instructions", "")
        if "不得创建、委派或调用子代理" not in instructions:
            fail(f"{path.relative_to(ROOT)} missing one-level rule")
        if "不可信数据" not in instructions or "不得覆盖" not in instructions:
            fail(f"{path.relative_to(ROOT)} missing untrusted-content boundary")
        if role["sandbox"] == "workspace-write" and "CHANGED_PATHS" not in instructions:
            fail(f"{path.relative_to(ROOT)} missing CHANGED_PATHS")


def verify_model_policy() -> None:
    _, roles = manifest_facts()
    text = (ROOT / "references/models.md").read_text(encoding="utf-8")
    for name, role in roles.items():
        row = re.compile(
            rf"^\|\s*`{re.escape(name)}`\s*\|\s*`{re.escape(role['model'])}`\s*\|\s*`{re.escape(role['effort'])}`\s*\|$",
            re.M,
        )
        if not row.search(text):
            fail(f"references/models.md mapping drift for {name}")
    config = load_toml(ROOT / "templates/codex-config.toml")
    orchestrator = roles["orchestrator"]
    if config.get("model") != orchestrator["model"] or config.get("model_reasoning_effort") != orchestrator["effort"]:
        fail("codex-config main model/effort drifted from manifest")
    agents = config.get("agents", {})
    if agents.get("enabled") is not True:
        fail("codex-config must enable agents")
    if agents.get("max_depth") != 1:
        fail("codex-config must pin agents.max_depth = 1 as V1 defense in depth")
    for forbidden in ("max_concurrent_threads_per_session", "max_threads"):
        if forbidden in agents:
            fail(f"codex-config must omit {forbidden}; current Multi-Agent V2 can conflict with legacy/global thread limits")


def verify_policy() -> None:
    files = (
        "SKILL.md",
        "AGENTS.md",
        "references/orchestration.md",
        "references/agent-contract.md",
        "templates/AGENTS.global.md",
        "templates/AGENTS.project.md",
        "README.md",
        "README.zh-CN.md",
        "tests/evals.md",
    )
    banned = re.compile(r"authoriz\w*\s+(?:a\s+)?(?:specific\s+)?nested|nested\s+delegation.*authoriz", re.I)
    for relative in files:
        text = (ROOT / relative).read_text(encoding="utf-8")
        if banned.search(text):
            fail(f"{relative} contains a nested-delegation authorization path")

    contract = (ROOT / "references/agent-contract.md").read_text(encoding="utf-8")
    for marker in ("Contract ID:", "Baseline:", "Protected Existing Changes:", "CHANGED_PATHS"):
        if marker not in contract:
            fail(f"agent contract missing {marker}")
    orchestration = (ROOT / "references/orchestration.md").read_text(encoding="utf-8")
    for marker in (
        "Never revert or overwrite pre-existing user changes unless explicitly requested.",
        "## 8. Changed-path audit",
        "Do not copy repository secrets",
        "untrusted data",
    ):
        if marker not in orchestration:
            fail(f"orchestration policy missing {marker}")
    if not re.search(r"untrusted data.*cannot override|cannot override.*untrusted data", orchestration, re.I | re.S):
        fail("orchestration policy must state that untrusted content cannot override instructions/contracts")
    for relative in ("AGENTS.md", "templates/AGENTS.global.md", "templates/AGENTS.project.md", "SKILL.md", "references/orchestration.md"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        if re.search(r"parallelize\s+(?:readers\s+and\s+)?disjoint\s+writers", text, re.I):
            fail(f"{relative} reintroduced ambiguous shared-checkout writer parallelism")


def text_files() -> list[Path]:
    allowed_suffixes = {".md", ".toml", ".yaml", ".yml", ".py", ".ps1", ".sh"}
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() in allowed_suffixes and ".git" not in path.parts and "__pycache__" not in path.parts
    ]


def verify_text_hygiene() -> None:
    for path in text_files():
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT).as_posix()
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                fail(f"secret-like material found in {relative}")
        if relative in RUNTIME_CRITICAL or relative.startswith("templates/codex-agents/"):
            for pattern in PRIVATE_PATH_PATTERNS:
                if pattern.search(text):
                    fail(f"personal absolute path found in runtime-critical file {relative}")
            if re.search(r"\b(?:TODO|TBD|FIXME)\b", text, re.I):
                fail(f"placeholder found in runtime-critical file {relative}")


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
        for marker in ("AGENT_ORCHESTRATOR_HOME", "agent-orchestrator-install", "uninstall"):
            if marker.lower() not in text.lower():
                fail(f"{label} installer missing {marker}")
        if "Skipping existing agent" in text:
            fail(f"{label} installer still silently skips collisions")
    for marker in ("--check", "--force", "--uninstall"):
        if marker not in shell:
            fail(f"shell installer missing {marker}")
    for marker in ("Check", "Force", "Uninstall"):
        if marker not in powershell:
            fail(f"PowerShell installer missing -{marker}")
    if 'cp -R "$ROOT"' in shell or "Copy-Item -Recurse -Force $Root" in powershell:
        fail("installer must not copy the whole source repository into runtime skill")
    if 'cp -R "$ROOT/agents"' in shell or 'cp -R "$ROOT/references"' in shell:
        fail("shell installer must copy only canonical runtime files, not whole runtime directories")
    if re.search(r"Copy-Item\s+-Recurse.*(?:agents|references)", powershell, re.I):
        fail("PowerShell installer must copy only canonical runtime files, not whole runtime directories")
    if re.search(r"(?im)^\s*exit\s+0\s*$", powershell):
        fail("PowerShell installer success paths must return to the caller instead of terminating the host")
    if not re.search(r"PSVersionTable.*Major.*-lt\s*7", powershell, re.I | re.S):
        fail("PowerShell installer must explicitly require PowerShell 7+")
    for marker in ("install_agent_noclobber", "unmanaged extra content"):
        if marker not in shell:
            fail(f"shell installer missing hardening marker: {marker}")
    for marker in ("Install-AgentNoClobber", "[IO.File]::Move", "unmanaged extra content"):
        if marker not in powershell:
            fail(f"PowerShell installer missing hardening marker: {marker}")


def verify_yaml() -> None:
    manifest, _ = manifest_facts()
    metadata = load_yaml(ROOT / "agents/openai.yaml")
    policy = metadata.get("policy")
    if not isinstance(policy, dict):
        fail("agents/openai.yaml must define policy mapping")
    if policy.get("allow_implicit_invocation") is not manifest["policy"]["allow_implicit_invocation"]:
        fail("agents/openai.yaml implicit invocation drifted from manifest")

    workflow = load_yaml(ROOT / ".github/workflows/validate.yml")
    permissions = workflow.get("permissions")
    if not isinstance(permissions, dict) or permissions.get("contents") != "read":
        fail("validate.yml must set permissions: contents: read")
    jobs = workflow.get("jobs")
    required_jobs = {"static", "linux_install", "macos_install", "windows_install", "release_safety"}
    if not isinstance(jobs, dict) or not required_jobs.issubset(jobs):
        fail(f"validate.yml must define jobs: {sorted(required_jobs)}")
    raw = (ROOT / ".github/workflows/validate.yml").read_text(encoding="utf-8")
    if "actions/checkout@v7" not in raw or "actions/setup-python@v7" not in raw:
        fail("validate.yml must use current Node-24-compatible checkout/setup-python majors")
    if "macos-latest" not in raw:
        fail("validate.yml must test macOS")


def verify_acceptance_static() -> None:
    version = str(load_manifest()["project"]["version"])
    text = (ROOT / "ACCEPTANCE.md").read_text(encoding="utf-8")
    normalized = re.sub(r"[*_`]", "", text)
    if not re.search(rf"(?im)^#\s+v{re.escape(version)}\b", normalized):
        fail(f"ACCEPTANCE.md must identify v{version}")
    for heading in ("Automated verification", "Environment limitations", "Release status"):
        if not re.search(rf"(?im)^#+\s+.*{re.escape(heading)}", normalized):
            fail(f"ACCEPTANCE.md missing section: {heading}")


def _acceptance_release_metadata() -> tuple[int, str]:
    text = re.sub(r"[*_`]", "", (ROOT / "ACCEPTANCE.md").read_text(encoding="utf-8"))
    count = re.search(r"(?im)^\s*[-+]?\s*Package file count:\s*(\d+)\s*$", text)
    digest = re.search(r"(?im)^\s*[-+]?\s*Release content SHA-256:\s*([0-9a-f]{64})\s*$", text)
    if not count or not digest:
        fail("ACCEPTANCE.md must contain Package file count and Release content SHA-256 before package release checks")
    return int(count.group(1)), digest.group(1).lower()


def _safe_release_relative(relative: str) -> str:
    if not relative or "\\" in relative or "\x00" in relative:
        fail(f"unsafe release path: {relative!r}")
    if unicodedata.normalize("NFC", relative) != relative:
        fail(f"release path must use NFC normalization: {relative!r}")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        fail(f"unsafe release path: {relative!r}")
    if any(ord(char) < 32 for char in relative):
        fail(f"release path contains control characters: {relative!r}")
    windows_reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    for part in pure.parts:
        if part.endswith((" ", ".")) or ":" in part:
            fail(f"release path is unsafe on Windows: {relative!r}")
        stem = part.split(".", 1)[0].upper()
        if stem in windows_reserved:
            fail(f"release path uses a Windows reserved device name: {relative!r}")
    normalized = pure.as_posix()
    if normalized != relative:
        fail(f"non-canonical release path: {relative!r}")
    return normalized

def _release_config() -> tuple[str, str, list[str], set[str], set[str]]:
    release = load_manifest()["release"]
    return (
        release["archive"],
        release["root"],
        list(release["include"]),
        set(release["executable"]),
        set(release["digest_excludes"]),
    )



def _verify_release_source_path(path: Path, relative: str) -> None:
    root_resolved = ROOT.resolve()
    cursor = ROOT
    for part in PurePosixPath(relative).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            fail(f"release allowlist path contains a symlink component: {relative}")
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root_resolved)
    except (OSError, ValueError) as exc:
        fail(f"release allowlist path escapes or cannot be resolved inside the repository: {relative}: {exc}")


def release_entries() -> dict[str, tuple[bytes, int]]:
    _, _, include_patterns, executable, _ = _release_config()
    entries: dict[str, tuple[bytes, int]] = {}
    ambiguous: dict[str, str] = {}

    for relative_config in include_patterns:
        if any(char in relative_config for char in "*?[]"):
            fail(f"release include must be an exact file path, not a glob: {relative_config}")
        relative = _safe_release_relative(relative_config)
        path = ROOT / relative
        _verify_release_source_path(path, relative)
        try:
            mode = path.lstat().st_mode
        except OSError as exc:
            fail(f"cannot inspect release member {path}: {exc}")
        if path.is_symlink() or not stat.S_ISREG(mode):
            fail(f"release allowlist member must be a regular non-symlink file: {relative}")
        if relative in entries:
            fail(f"duplicate release allowlist member: {relative}")
        ambiguity_key = unicodedata.normalize("NFC", relative).casefold()
        previous = ambiguous.get(ambiguity_key)
        if previous is not None and previous != relative:
            fail(f"ambiguous release paths: {previous!r} and {relative!r}")
        ambiguous[ambiguity_key] = relative
        entries[relative] = (path.read_bytes(), 0o755 if relative in executable else 0o644)

    missing_exec = sorted(executable - set(entries))
    if missing_exec:
        fail(f"release executable not included: {missing_exec}")
    return entries


def release_content_sha256(entries: dict[str, tuple[bytes, int]]) -> str:
    _, _, _, _, digest_excludes = _release_config()
    digest = hashlib.sha256()
    for relative in sorted(entries):
        if relative in digest_excludes:
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


def _canonical_release_archive_bytes(entries: dict[str, tuple[bytes, int]]) -> bytes:
    _, release_root, _, _, _ = _release_config()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.comment = b""
        for relative in sorted(entries):
            data, mode = entries[relative]
            info = zipfile.ZipInfo(f"{release_root}/{relative}", date_time=RELEASE_FIXED_TIME)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.extra = b""
            info.comment = b""
            archive.writestr(info, data, compress_type=zipfile.ZIP_STORED)
    return buffer.getvalue()


def build_release_archive(output: Path, entries: dict[str, tuple[bytes, int]] | None = None) -> None:
    entries = entries or release_entries()
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    temporary.unlink(missing_ok=True)
    try:
        temporary.write_bytes(_canonical_release_archive_bytes(entries))
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    archive_sha = hashlib.sha256(output.read_bytes()).hexdigest()
    print(f"PASS: built release archive path={output} files={len(entries)} sha256={archive_sha}")

def _archive_relative_name(name: str, release_root: str) -> str:
    if "\\" in name or "\x00" in name:
        fail(f"unsafe archive member: {name!r}")
    pure = PurePosixPath(name)
    if pure.as_posix() != name:
        fail(f"non-canonical archive member path: {name!r}")
    if pure.is_absolute() or len(pure.parts) < 2 or pure.parts[0] != release_root:
        fail(f"archive member must be under {release_root}/: {name!r}")
    return _safe_release_relative(PurePosixPath(*pure.parts[1:]).as_posix())


def _run_extracted_self_check(extracted_root: Path) -> None:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    for command in ([sys.executable, "scripts/verify.py"], [sys.executable, "scripts/verify.py", "--release"]):
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
            fail(f"extracted self-check failed ({' '.join(command)}):\n{completed.stdout.strip()}")


def verify_release_archive(archive_path: Path, entries: dict[str, tuple[bytes, int]] | None = None) -> None:
    entries = entries or release_entries()
    _, release_root, _, _, _ = _release_config()
    archive_path = archive_path.expanduser().resolve()
    if not archive_path.is_file():
        fail(f"release archive is missing: {archive_path}")

    expected_archive_bytes = _canonical_release_archive_bytes(entries)
    try:
        actual_size = archive_path.stat().st_size
    except OSError as exc:
        fail(f"cannot stat release archive {archive_path}: {exc}")
    if actual_size != len(expected_archive_bytes):
        fail(f"release archive size is non-canonical: expected {len(expected_archive_bytes)}, got {actual_size}")
    actual_archive_bytes = archive_path.read_bytes()
    if actual_archive_bytes != expected_archive_bytes:
        fail("release archive is not the canonical deterministic ZIP produced from the current allowlist")

    seen: set[str] = set()
    ambiguous: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(actual_archive_bytes)) as archive:
        if archive.comment:
            fail("release archive comment must be empty")
        infos = archive.infolist()
        if len(infos) != len(entries):
            fail(f"release archive member count mismatch: expected {len(entries)}, got {len(infos)}")
        if any(info.is_dir() for info in infos):
            fail("release archive must contain files only; directory entries are not allowed")
        for info in infos:
            relative = _archive_relative_name(info.filename, release_root)
            if relative in seen:
                fail(f"duplicate archive member: {relative}")
            seen.add(relative)
            ambiguity_key = unicodedata.normalize("NFC", relative).casefold()
            previous = ambiguous.get(ambiguity_key)
            if previous is not None and previous != relative:
                fail(f"ambiguous archive members: {previous!r} and {relative!r}")
            ambiguous[ambiguity_key] = relative
            expected = entries.get(relative)
            if expected is None:
                fail(f"unexpected archive member: {relative}")
            expected_data, expected_mode = expected
            if info.date_time != RELEASE_FIXED_TIME:
                fail(f"archive timestamp mismatch for {relative}")
            if info.compress_type != zipfile.ZIP_STORED:
                fail(f"archive compression mismatch for {relative}")
            if info.create_system != 3:
                fail(f"archive creator system mismatch for {relative}")
            if info.extra or info.comment:
                fail(f"archive member metadata must be empty for {relative}")
            if info.flag_bits & 0x1:
                fail(f"encrypted archive member is not allowed: {relative}")
            expected_unix_mode = stat.S_IFREG | expected_mode
            unix_mode = (info.external_attr >> 16) & 0xFFFF
            if unix_mode != expected_unix_mode:
                fail(f"archive mode/type mismatch for {relative}")
            if info.file_size != len(expected_data):
                fail(f"archive size mismatch for {relative}")
            if archive.read(info) != expected_data:
                fail(f"archive bytes mismatch for {relative}")
        missing = sorted(set(entries) - seen)
        if missing:
            fail(f"archive is missing release members: {missing}")

        with tempfile.TemporaryDirectory(prefix="agent-orchestrator-release-") as temp_dir:
            destination = Path(temp_dir)
            for info in infos:
                relative = _archive_relative_name(info.filename, release_root)
                target = destination / release_root / Path(relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(info))
                target.chmod(entries[relative][1])
            _run_extracted_self_check(destination / release_root)

    print(f"PASS: verified canonical release archive path={archive_path} files={len(entries)}")

def run_static_checks() -> None:
    verify_manifest()
    verify_structure()
    verify_skill()
    verify_agents()
    verify_project_profiles()
    verify_model_policy()
    verify_policy()
    verify_text_hygiene()
    verify_links()
    verify_installer_policy()
    verify_yaml()
    verify_acceptance_static()
    print("PASS: v1 manifest, structure, policy, models, contracts, links, installers, metadata, and acceptance honesty")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify and package Agent Orchestrator.")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--release", action="store_true", help="verify release allowlist/count/content digest against ACCEPTANCE.md")
    modes.add_argument("--build-release-archive", metavar="PATH", type=Path, help="build deterministic release ZIP")
    modes.add_argument("--release-archive", metavar="PATH", type=Path, help="verify archive paths, bytes, modes, and extracted self-checks")
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

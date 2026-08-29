from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts/install-codex.sh"
POWERSHELL_INSTALLER = ROOT / "scripts/install-codex.ps1"
PWSH = shutil.which("pwsh")


@unittest.skipIf(os.name == "nt", "Bash installer behavior is exercised on Unix runners")
class ShellInstallerTests(unittest.TestCase):
    def run_installer(self, home: Path, *args: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["AGENT_ORCHESTRATOR_HOME"] = str(home)
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            ["bash", str(INSTALLER), *args],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def test_partial_agent_collision_aborts_before_any_mutation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent orchestrator 测试 ") as temp:
            home = Path(temp)
            agent_dir = home / ".codex/agents"
            agent_dir.mkdir(parents=True)
            collision = agent_dir / "frontend-worker.toml"
            collision.write_text("user-owned\n", encoding="utf-8")

            result = self.run_installer(home)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertEqual(collision.read_text(encoding="utf-8"), "user-owned\n")
            self.assertFalse((home / ".agents/skills/agent-orchestrator").exists())
            self.assertEqual([p.name for p in agent_dir.iterdir()], ["frontend-worker.toml"])

    def test_uninstall_check_is_neutral_when_no_managed_install_exists(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent orchestrator absent uninstall ") as temp:
            home = Path(temp)
            preview = self.run_installer(home, "--uninstall", "--check")
            self.assertEqual(preview.returncode, 0, preview.stdout)
            self.assertIn("CHECK PASS", preview.stdout)
            self.assertIn("no managed installation", preview.stdout.lower())

            actual = self.run_installer(home, "--uninstall")
            self.assertEqual(actual.returncode, 0, actual.stdout)
            self.assertIn("No managed installation", actual.stdout)

    def test_uninstall_without_manifest_never_claims_unmanaged_targets(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent orchestrator unmanaged uninstall ") as temp:
            home = Path(temp)
            agent_dir = home / ".codex/agents"
            agent_dir.mkdir(parents=True)
            custom = agent_dir / "frontend-worker.toml"
            custom.write_text("user-owned\n", encoding="utf-8")

            preview = self.run_installer(home, "--uninstall", "--check")
            self.assertEqual(preview.returncode, 0, preview.stdout)
            self.assertIn("CHECK PASS", preview.stdout)
            self.assertIn("unmanaged", preview.stdout.lower())
            refused = self.run_installer(home, "--uninstall", "--force")
            self.assertNotEqual(refused.returncode, 0, refused.stdout)
            self.assertEqual(custom.read_text(encoding="utf-8"), "user-owned\n")

    def test_check_mode_is_non_mutating_and_force_check_allows_planned_replacement(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent orchestrator 检查 ") as temp:
            home = Path(temp)
            first = self.run_installer(home, "--check")
            self.assertEqual(first.returncode, 0, first.stdout)
            self.assertFalse((home / ".agents").exists())
            self.assertFalse((home / ".codex").exists())

            installed = self.run_installer(home)
            self.assertEqual(installed.returncode, 0, installed.stdout)
            collision_check = self.run_installer(home, "--check")
            self.assertEqual(collision_check.returncode, 0, collision_check.stdout)
            self.assertIn("CHECK PASS", collision_check.stdout)
            self.assertIn("requires --force", collision_check.stdout)
            self.assertNotIn("Refusing installation", collision_check.stdout)
            force_check = self.run_installer(home, "--check", "--force")
            self.assertEqual(force_check.returncode, 0, force_check.stdout)
            self.assertIn("CHECK PASS", force_check.stdout)
            self.assertIn("--force would replace", force_check.stdout)

    def test_late_agent_collision_is_never_overwritten_during_commit(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent orchestrator commit race ") as temp:
            base = Path(temp)
            home = base / "home"
            fake_bin = base / "bin"
            fake_bin.mkdir()
            collision = home / ".codex/agents/test-worker.toml"
            marker_file = base / "race-injected"
            real_mv = shutil.which("mv")
            real_ln = shutil.which("ln")
            self.assertIsNotNone(real_mv)
            self.assertIsNotNone(real_ln)
            wrapper = r'''#!/usr/bin/env bash
set -e
if [[ -n "${AO_RACE_COLLISION:-}" && -n "${AO_RACE_MARKER:-}" && ! -e "$AO_RACE_MARKER" ]]; then
  trigger=0
  if [[ "$(basename "$0")" == "mv" && "${1:-}" == */staging/*/skill ]]; then trigger=1; fi
  if [[ "$(basename "$0")" == "ln" ]]; then trigger=1; fi
  if [[ "$trigger" -eq 1 ]]; then
    mkdir -p "$(dirname "$AO_RACE_COLLISION")"
    printf 'late user-owned collision\n' > "$AO_RACE_COLLISION"
    : > "$AO_RACE_MARKER"
  fi
fi
if [[ "$(basename "$0")" == "mv" ]]; then exec "$AO_REAL_MV" "$@"; fi
exec "$AO_REAL_LN" "$@"
'''
            for name in ("mv", "ln"):
                path = fake_bin / name
                path.write_text(wrapper, encoding="utf-8")
                path.chmod(0o755)

            result = self.run_installer(
                home,
                extra_env={
                    "PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", ""),
                    "AO_RACE_COLLISION": str(collision),
                    "AO_RACE_MARKER": str(marker_file),
                    "AO_REAL_MV": str(real_mv),
                    "AO_REAL_LN": str(real_ln),
                },
            )
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertEqual(collision.read_text(encoding="utf-8"), "late user-owned collision\n")
            self.assertFalse((home / ".agents/skills/agent-orchestrator").exists(), result.stdout)

    def test_force_upgrade_backs_up_and_restores_canonical_content(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent orchestrator 升级 ") as temp:
            home = Path(temp)
            self.assertEqual(self.run_installer(home).returncode, 0)
            skill = home / ".agents/skills/agent-orchestrator/SKILL.md"
            skill.write_text(skill.read_text(encoding="utf-8") + "\nuser mutation\n", encoding="utf-8")
            result = self.run_installer(home, "--force")
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual(skill.read_bytes(), (ROOT / "SKILL.md").read_bytes())
            backup_root = home / ".agent-orchestrator/backups"
            self.assertTrue(any(backup_root.iterdir()), result.stdout)

    def test_uninstall_does_not_depend_on_install_only_source_files(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent orchestrator damaged source uninstall ") as temp:
            base = Path(temp)
            home = base / "home"
            installed = self.run_installer(home)
            self.assertEqual(installed.returncode, 0, installed.stdout)

            source = base / "source"
            shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            (source / "templates/codex-agents/frontend-worker.toml").unlink()
            env = os.environ.copy()
            env["AGENT_ORCHESTRATOR_HOME"] = str(home)
            result = subprocess.run(
                ["bash", str(source / "scripts/install-codex.sh"), "--uninstall"],
                cwd=source,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertFalse((home / ".agents/skills/agent-orchestrator").exists())

    def test_newer_source_can_uninstall_older_managed_version(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent orchestrator 旧版卸载 ") as temp:
            home = Path(temp)
            installed = self.run_installer(home)
            self.assertEqual(installed.returncode, 0, installed.stdout)
            manifest = home / ".agents/skills/agent-orchestrator/.agent-orchestrator-install.tsv"
            text = manifest.read_text(encoding="utf-8")
            text = text.replace("version\t1.0.0\t-", "version\t0.9.0\t-", 1)
            manifest.write_text(text, encoding="utf-8")

            result = self.run_installer(home, "--uninstall")
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertFalse((home / ".agents/skills/agent-orchestrator").exists())

    def test_uninstall_accepts_known_legacy_eight_profile_manifest(self) -> None:
        manifest_path = ROOT / "manifest.toml"
        original_manifest = manifest_path.read_text(encoding="utf-8")
        legacy_bytes = b"synthetic legacy profile for uninstall\n"
        legacy_hash = hashlib.sha256(legacy_bytes).hexdigest()
        patched_manifest = re.sub(
            r'(?ms)(\[compatibility\]\nlegacy_orchestrator_sha256 = \[).*?(\]\n)',
            rf'\1\n  "{legacy_hash}",\n\2',
            original_manifest,
            count=1,
        )
        manifest_path.write_text(patched_manifest, encoding="utf-8")
        try:
            with tempfile.TemporaryDirectory(prefix="agent orchestrator legacy uninstall ") as temp:
                home = Path(temp)
                installed = self.run_installer(home)
                self.assertEqual(installed.returncode, 0, installed.stdout)
                legacy = home / ".codex/agents/orchestrator.toml"
                legacy.write_bytes(legacy_bytes)
                managed = home / ".agents/skills/agent-orchestrator/.agent-orchestrator-install.tsv"
                with managed.open("a", encoding="utf-8") as handle:
                    handle.write(f"agent\torchestrator.toml\t{legacy_hash}\n")

                result = self.run_installer(home, "--uninstall")
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertFalse((home / ".agents/skills/agent-orchestrator").exists())
                self.assertFalse(legacy.exists())
        finally:
            manifest_path.write_text(original_manifest, encoding="utf-8")

    def test_force_uninstall_never_claims_modified_legacy_orchestrator(self) -> None:
        manifest_path = ROOT / "manifest.toml"
        original_manifest = manifest_path.read_text(encoding="utf-8")
        legacy_bytes = b"synthetic legacy profile for ownership test\n"
        legacy_hash = hashlib.sha256(legacy_bytes).hexdigest()
        patched_manifest = re.sub(
            r'(?ms)(\[compatibility\]\nlegacy_orchestrator_sha256 = \[).*?(\]\n)',
            rf'\1\n  "{legacy_hash}",\n\2',
            original_manifest,
            count=1,
        )
        manifest_path.write_text(patched_manifest, encoding="utf-8")
        try:
            with tempfile.TemporaryDirectory(prefix="agent orchestrator modified legacy uninstall ") as temp:
                home = Path(temp)
                installed = self.run_installer(home)
                self.assertEqual(installed.returncode, 0, installed.stdout)
                legacy = home / ".codex/agents/orchestrator.toml"
                legacy.write_text("user-owned replacement\n", encoding="utf-8")
                managed = home / ".agents/skills/agent-orchestrator/.agent-orchestrator-install.tsv"
                with managed.open("a", encoding="utf-8") as handle:
                    handle.write(f"agent\torchestrator.toml\t{legacy_hash}\n")

                preview = self.run_installer(home, "--uninstall", "--check", "--force")
                self.assertEqual(preview.returncode, 0, preview.stdout)
                self.assertIn("orchestrator.toml", preview.stdout)
                self.assertIn("blocked", preview.stdout.lower())
                result = self.run_installer(home, "--uninstall", "--force")
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertEqual(legacy.read_text(encoding="utf-8"), "user-owned replacement\n")
                self.assertTrue((home / ".agents/skills/agent-orchestrator").exists())
        finally:
            manifest_path.write_text(original_manifest, encoding="utf-8")

    def test_uninstall_rejects_tampered_manifest_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent orchestrator manifest 安全 ") as temp:
            home = Path(temp)
            installed = self.run_installer(home)
            self.assertEqual(installed.returncode, 0, installed.stdout)
            victim = home / "victim.txt"
            victim.write_text("do not move\n", encoding="utf-8")
            victim_hash = hashlib.sha256(victim.read_bytes()).hexdigest()
            manifest = home / ".agents/skills/agent-orchestrator/.agent-orchestrator-install.tsv"
            lines = manifest.read_text(encoding="utf-8").splitlines()
            for index, line in enumerate(lines):
                if line.startswith("agent\tfrontend-worker.toml\t"):
                    lines[index] = f"agent\t../../../victim.txt\t{victim_hash}"
                    break
            else:
                self.fail("frontend-worker manifest entry not found")
            manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

            result = self.run_installer(home, "--uninstall", "--force")
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertEqual(victim.read_text(encoding="utf-8"), "do not move\n")
            self.assertTrue((home / ".agents/skills/agent-orchestrator").exists())

    def test_uninstall_refuses_modified_managed_file_without_force(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent orchestrator 卸载 ") as temp:
            home = Path(temp)
            self.assertEqual(self.run_installer(home).returncode, 0)
            agent = home / ".codex/agents/frontend-worker.toml"
            agent.write_text(agent.read_text(encoding="utf-8") + "\n# local customization\n", encoding="utf-8")
            refused = self.run_installer(home, "--uninstall")
            self.assertNotEqual(refused.returncode, 0, refused.stdout)
            self.assertTrue(agent.exists())
            forced = self.run_installer(home, "--uninstall", "--force")
            self.assertEqual(forced.returncode, 0, forced.stdout)
            self.assertFalse((home / ".agents/skills/agent-orchestrator").exists())
            self.assertFalse(agent.exists())

    def test_force_backup_failure_never_deletes_the_existing_installation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent orchestrator rollback ") as temp:
            home = Path(temp)
            installed = self.run_installer(home)
            self.assertEqual(installed.returncode, 0, installed.stdout)
            skill = home / ".agents/skills/agent-orchestrator/SKILL.md"
            original_skill = skill.read_bytes()
            original_agents = {p.name: p.read_bytes() for p in (home / ".codex/agents").glob("*.toml")}

            fake_bin = home / "fake-bin"
            fake_bin.mkdir()
            real_mv = shutil.which("mv")
            self.assertIsNotNone(real_mv)
            wrapper = fake_bin / "mv"
            wrapper.write_text(
                "#!/usr/bin/env bash\n"
                "src=\"$1\"; dst=\"$2\"\n"
                "if [[ \"$src\" == */.agents/skills/agent-orchestrator && \"$dst\" == */backups/install-*/skill ]]; then exit 77; fi\n"
                f"exec {real_mv} \"$@\"\n",
                encoding="utf-8",
            )
            wrapper.chmod(0o755)
            result = self.run_installer(home, "--force", extra_env={"PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"})
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertTrue(skill.is_file(), result.stdout)
            self.assertEqual(skill.read_bytes(), original_skill)
            self.assertEqual(
                {p.name: p.read_bytes() for p in (home / ".codex/agents").glob("*.toml")},
                original_agents,
            )

    def test_installer_rejects_agent_source_set_with_rogue_replacement(self) -> None:
        canonical = ROOT / "templates/codex-agents/frontend-worker.toml"
        parked = ROOT / "frontend-worker.toml.test-parked"
        rogue = ROOT / "templates/codex-agents/rogue-worker.toml"
        self.assertTrue(canonical.is_file())
        canonical.rename(parked)
        rogue.write_text(
            'name = "rogue_worker"\ndescription = "rogue"\nsandbox_mode = "workspace-write"\n'
            'model = "gpt-5.6-terra"\nmodel_reasoning_effort = "medium"\n'
            'developer_instructions = "rogue"\n',
            encoding="utf-8",
        )
        try:
            with tempfile.TemporaryDirectory(prefix="agent orchestrator rogue source ") as temp:
                home = Path(temp)
                result = self.run_installer(home)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("frontend-worker.toml", result.stdout)
                self.assertFalse((home / ".agents/skills/agent-orchestrator").exists())
                self.assertFalse((home / ".codex/agents/rogue-worker.toml").exists())
        finally:
            rogue.unlink(missing_ok=True)
            parked.rename(canonical)

    def test_installer_copies_only_canonical_skill_runtime_files(self) -> None:
        rogue_reference = ROOT / "references/NOT-FOR-INSTALL.tmp"
        rogue_agent_metadata = ROOT / "agents/NOT-FOR-INSTALL.tmp"
        rogue_reference.write_text("private development note\n", encoding="utf-8")
        rogue_agent_metadata.write_text("private development note\n", encoding="utf-8")
        try:
            with tempfile.TemporaryDirectory(prefix="agent orchestrator exact runtime ") as temp:
                home = Path(temp)
                result = self.run_installer(home)
                self.assertEqual(result.returncode, 0, result.stdout)
                skill = home / ".agents/skills/agent-orchestrator"
                self.assertFalse((skill / "references/NOT-FOR-INSTALL.tmp").exists())
                self.assertFalse((skill / "agents/NOT-FOR-INSTALL.tmp").exists())
        finally:
            rogue_reference.unlink(missing_ok=True)
            rogue_agent_metadata.unlink(missing_ok=True)

    def test_uninstall_check_is_neutral_when_modified_files_require_force(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent orchestrator uninstall check ") as temp:
            home = Path(temp)
            installed = self.run_installer(home)
            self.assertEqual(installed.returncode, 0, installed.stdout)
            agent = home / ".codex/agents/frontend-worker.toml"
            agent.write_text(agent.read_text(encoding="utf-8") + "\n# local customization\n", encoding="utf-8")

            preview = self.run_installer(home, "--uninstall", "--check")
            self.assertEqual(preview.returncode, 0, preview.stdout)
            self.assertIn("CHECK PASS", preview.stdout)
            self.assertIn("requires --force", preview.stdout)
            self.assertTrue(agent.exists())
            self.assertTrue((home / ".agents/skills/agent-orchestrator").exists())

    def test_active_operation_lock_blocks_mutating_install(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent orchestrator lock ") as temp:
            home = Path(temp)
            lock_dir = home / ".agent-orchestrator/operation.lock"
            lock_dir.mkdir(parents=True)
            (lock_dir / "pid").write_text(str(os.getpid()) + "\n", encoding="utf-8")
            result = self.run_installer(home)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("operation is already running", result.stdout)
            self.assertFalse((home / ".agents/skills/agent-orchestrator").exists())

    def test_operation_lock_without_valid_pid_is_busy_and_preserved(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent orchestrator invalid lock ") as temp:
            home = Path(temp)
            lock_dir = home / ".agent-orchestrator/operation.lock"
            lock_dir.mkdir(parents=True)
            marker = lock_dir / "acquisition-marker"
            marker.write_text("keep this lock", encoding="utf-8")

            result = self.run_installer(home)

            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("already running or acquiring", result.stdout.lower())
            self.assertTrue(lock_dir.is_dir(), result.stdout)
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep this lock")
            self.assertFalse((home / ".agents/skills/agent-orchestrator").exists())

    def test_operation_lock_with_kill_error_is_busy_and_preserved(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent orchestrator kill error lock ") as temp:
            base = Path(temp)
            home = base / "home"
            lock_dir = home / ".agent-orchestrator/operation.lock"
            lock_dir.mkdir(parents=True)
            (lock_dir / "pid").write_text("42424242\n", encoding="utf-8")
            marker = lock_dir / "acquisition-marker"
            marker.write_text("keep this lock\n", encoding="utf-8")
            kill_marker = base / "kill-called"
            bash_env = base / "bash-env"
            bash_env.write_text(
                "kill() {\n"
                "  printf '%s\\n' \"$*\" > \"$AO_KILL_MARKER\"\n"
                "  return 2\n"
                "}\n",
                encoding="utf-8",
            )

            result = self.run_installer(
                home,
                extra_env={"BASH_ENV": str(bash_env), "AO_KILL_MARKER": str(kill_marker)},
            )

            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("already running or acquiring", result.stdout.lower())
            self.assertTrue(lock_dir.is_dir(), result.stdout)
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep this lock\n")
            self.assertEqual(kill_marker.read_text(encoding="utf-8").strip(), "-0 42424242")
            self.assertFalse((home / ".agents/skills/agent-orchestrator").exists())

    def test_symlinked_target_ancestors_abort_before_external_mutation(self) -> None:
        cases = (
            (".agents", Path("skills/agent-orchestrator")),
            (".codex", Path("agents")),
            (".agent-orchestrator", Path("staging")),
        )
        for link_name, runtime_path in cases:
            with self.subTest(link_name=link_name), tempfile.TemporaryDirectory(
                prefix=f"agent orchestrator symlinked {link_name} "
            ) as temp:
                base = Path(temp)
                home = base / "home"
                external = base / "external"
                home.mkdir()
                external.mkdir()
                marker = external / "keep.txt"
                marker.write_text("user-owned", encoding="utf-8")
                (home / link_name).symlink_to(external, target_is_directory=True)
                before = sorted(path.relative_to(external).as_posix() for path in external.rglob("*"))

                result = self.run_installer(home)

                self.assertEqual(
                    before,
                    sorted(path.relative_to(external).as_posix() for path in external.rglob("*")),
                    result.stdout,
                )
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertFalse((external / runtime_path).exists(), result.stdout)

    def test_stale_operation_lock_is_recovered_safely(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent orchestrator stale lock ") as temp:
            home = Path(temp)
            lock_dir = home / ".agent-orchestrator/operation.lock"
            lock_dir.mkdir(parents=True)
            (lock_dir / "pid").write_text("99999999\n", encoding="utf-8")
            result = self.run_installer(home)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertTrue((home / ".agents/skills/agent-orchestrator").exists())
            self.assertFalse(lock_dir.exists(), result.stdout)

    def test_unknown_orchestrator_profile_is_never_overwritten_even_with_force(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent orchestrator custom primary ") as temp:
            home = Path(temp)
            agent_dir = home / ".codex/agents"
            agent_dir.mkdir(parents=True)
            custom = agent_dir / "orchestrator.toml"
            custom.write_text("user-owned custom orchestrator\n", encoding="utf-8")

            preview = self.run_installer(home, "--check", "--force")
            self.assertEqual(preview.returncode, 0, preview.stdout)
            self.assertIn("unmanaged orchestrator.toml", preview.stdout)
            self.assertIn("blocked", preview.stdout.lower())
            result = self.run_installer(home, "--force")
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertEqual(custom.read_text(encoding="utf-8"), "user-owned custom orchestrator\n")
            self.assertFalse((home / ".agents/skills/agent-orchestrator").exists())

    def test_force_never_replaces_unmanaged_worker_collision(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent orchestrator unmanaged worker ") as temp:
            home = Path(temp)
            agent_dir = home / ".codex/agents"
            agent_dir.mkdir(parents=True)
            custom = agent_dir / "frontend-worker.toml"
            custom.write_text("user-owned frontend profile\n", encoding="utf-8")

            preview = self.run_installer(home, "--check", "--force")
            self.assertEqual(preview.returncode, 0, preview.stdout)
            self.assertIn("CHECK PASS", preview.stdout)
            self.assertIn("unmanaged", preview.stdout.lower())
            self.assertIn("blocked", preview.stdout.lower())

            result = self.run_installer(home, "--force")
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertEqual(custom.read_text(encoding="utf-8"), "user-owned frontend profile\n")
            self.assertFalse((home / ".agents/skills/agent-orchestrator").exists())

    def test_force_never_replaces_unmanaged_skill_destination(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent orchestrator unmanaged skill ") as temp:
            home = Path(temp)
            skill = home / ".agents/skills/agent-orchestrator"
            skill.mkdir(parents=True)
            marker = skill / "user-owned.txt"
            marker.write_text("keep me\n", encoding="utf-8")

            preview = self.run_installer(home, "--check", "--force")
            self.assertEqual(preview.returncode, 0, preview.stdout)
            self.assertIn("CHECK PASS", preview.stdout)
            self.assertIn("unmanaged", preview.stdout.lower())
            self.assertIn("blocked", preview.stdout.lower())

            result = self.run_installer(home, "--force")
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep me\n")

    def test_broken_symlink_worker_collision_is_never_silently_replaced(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent orchestrator broken link ") as temp:
            home = Path(temp)
            agent_dir = home / ".codex/agents"
            agent_dir.mkdir(parents=True)
            link = agent_dir / "frontend-worker.toml"
            link.symlink_to(home / "missing-target.toml")

            preview = self.run_installer(home, "--check", "--force")
            self.assertEqual(preview.returncode, 0, preview.stdout)
            self.assertIn("unmanaged", preview.stdout.lower())
            result = self.run_installer(home, "--force")
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertTrue(link.is_symlink())
            self.assertFalse((home / ".agents/skills/agent-orchestrator").exists())

    def test_installer_rejects_symlinked_source_parent_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent orchestrator source link ") as temp:
            base = Path(temp)
            source = base / "source"
            shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            external = base / "external-references"
            shutil.copytree(source / "references", external)
            shutil.rmtree(source / "references")
            (source / "references").symlink_to(external, target_is_directory=True)
            home = base / "home"
            env = os.environ.copy()
            env["AGENT_ORCHESTRATOR_HOME"] = str(home)
            result = subprocess.run(
                ["bash", str(source / "scripts/install-codex.sh")],
                cwd=source,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("unsafe installer source", result.stdout.lower())
            self.assertFalse((home / ".agents/skills/agent-orchestrator").exists())

    def test_install_manifest_requires_exact_skill_runtime_set(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent orchestrator exact manifest ") as temp:
            home = Path(temp)
            installed = self.run_installer(home)
            self.assertEqual(installed.returncode, 0, installed.stdout)
            skill = home / ".agents/skills/agent-orchestrator"
            extra = skill / "extra.md"
            extra.write_text("synthetic\n", encoding="utf-8")
            extra_hash = hashlib.sha256(extra.read_bytes()).hexdigest()
            manifest = skill / ".agent-orchestrator-install.tsv"
            lines = manifest.read_text(encoding="utf-8").splitlines()
            for index, line in enumerate(lines):
                if line.startswith("skill\tSKILL.md\t"):
                    lines[index] = f"skill\textra.md\t{extra_hash}"
                    break
            else:
                self.fail("SKILL.md manifest entry not found")
            manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

            result = self.run_installer(home, "--uninstall", "--force")
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("unknown managed Skill", result.stdout)
            self.assertTrue(skill.exists())

    def test_uninstall_protects_untracked_skill_content_until_force(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent orchestrator untracked skill ") as temp:
            home = Path(temp)
            installed = self.run_installer(home)
            self.assertEqual(installed.returncode, 0, installed.stdout)
            skill = home / ".agents/skills/agent-orchestrator"
            extra = skill / "user-note.txt"
            extra.write_text("keep this user content\n", encoding="utf-8")

            preview = self.run_installer(home, "--uninstall", "--check")
            self.assertEqual(preview.returncode, 0, preview.stdout)
            self.assertIn("CHECK PASS", preview.stdout)
            self.assertIn("requires --force", preview.stdout)
            self.assertIn("user-note.txt", preview.stdout)
            self.assertTrue(extra.exists())

            refused = self.run_installer(home, "--uninstall")
            self.assertNotEqual(refused.returncode, 0, refused.stdout)
            self.assertTrue(extra.exists())
            self.assertTrue(skill.exists())

            forced = self.run_installer(home, "--uninstall", "--force")
            self.assertEqual(forced.returncode, 0, forced.stdout)
            self.assertFalse(skill.exists())
            backups = list((home / ".agent-orchestrator/backups").glob("uninstall-*/skill/user-note.txt"))
            self.assertEqual(len(backups), 1, forced.stdout)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), "keep this user content\n")

    def test_legacy_hash_parser_accepts_valid_toml_last_item_without_trailing_comma(self) -> None:
        manifest_path = ROOT / "manifest.toml"
        original = manifest_path.read_text(encoding="utf-8")
        patched = re.sub(
            r'(?ms)(legacy_orchestrator_sha256\s*=\s*\[)(.*?)(\])',
            lambda match: match.group(1) + '\n  "' + re.findall(r'[0-9a-f]{64}', match.group(2))[0] + '"\n' + match.group(3),
            original,
            count=1,
        )
        manifest_path.write_text(patched, encoding="utf-8")
        try:
            with tempfile.TemporaryDirectory(prefix="agent orchestrator toml parser ") as temp:
                result = self.run_installer(Path(temp), "--check")
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertIn("CHECK PASS", result.stdout)
        finally:
            manifest_path.write_text(original, encoding="utf-8")

    def test_known_legacy_orchestrator_profile_is_backed_up_and_deactivated(self) -> None:
        manifest_path = ROOT / "manifest.toml"
        original_manifest = manifest_path.read_text(encoding="utf-8")
        legacy_bytes = b"synthetic known legacy orchestrator fixture\n"
        legacy_hash = hashlib.sha256(legacy_bytes).hexdigest()
        patched_manifest = re.sub(
            r'(?ms)(\[compatibility\]\nlegacy_orchestrator_sha256 = \[).*?(\]\n)',
            rf'\1\n  "{legacy_hash}",\n\2',
            original_manifest,
            count=1,
        )
        self.assertNotEqual(patched_manifest, original_manifest)
        manifest_path.write_text(patched_manifest, encoding="utf-8")
        try:
            with tempfile.TemporaryDirectory(prefix="agent orchestrator legacy primary ") as temp:
                home = Path(temp)
                agent_dir = home / ".codex/agents"
                agent_dir.mkdir(parents=True)
                legacy = agent_dir / "orchestrator.toml"
                legacy.write_bytes(legacy_bytes)

                result = self.run_installer(home)
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertFalse(legacy.exists(), result.stdout)
                self.assertEqual(len(list(agent_dir.glob("*.toml"))), 7)
                backups = list((home / ".agent-orchestrator/backups").glob("install-*/agents/orchestrator.toml"))
                self.assertEqual(len(backups), 1, result.stdout)
                self.assertEqual(backups[0].read_bytes(), legacy_bytes)
        finally:
            manifest_path.write_text(original_manifest, encoding="utf-8")


@unittest.skipUnless(PWSH, "PowerShell 7 (pwsh) is required")
class PowerShellInstallerTests(unittest.TestCase):
    @staticmethod
    def create_junction(link: Path, target: Path) -> None:
        try:
            result = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
        except OSError as exc:
            raise unittest.SkipTest(f"junction creation is unavailable: {exc}") from exc
        if result.returncode != 0:
            raise unittest.SkipTest(f"junction creation is unavailable: {result.stdout}")

    def test_reparse_target_ancestors_abort_before_external_mutation(self) -> None:
        cases = (
            (".agents", Path("skills/agent-orchestrator")),
            (".codex", Path("agents")),
            (".agent-orchestrator", Path("staging")),
        )
        for link_name, runtime_path in cases:
            with self.subTest(link_name=link_name), tempfile.TemporaryDirectory(
                prefix=f"agent orchestrator PowerShell junction {link_name} "
            ) as temp:
                base = Path(temp)
                home = base / "home"
                external = base / "external"
                home.mkdir()
                external.mkdir()
                marker = external / "keep.txt"
                marker.write_text("user-owned", encoding="utf-8")
                self.create_junction(home / link_name, external)
                before = sorted(path.relative_to(external).as_posix() for path in external.rglob("*"))
                env = os.environ.copy()
                env["AGENT_ORCHESTRATOR_HOME"] = str(home)

                result = subprocess.run(
                    [PWSH, "-File", str(POWERSHELL_INSTALLER)],
                    cwd=ROOT,
                    env=env,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    check=False,
                )

                self.assertEqual(
                    before,
                    sorted(path.relative_to(external).as_posix() for path in external.rglob("*")),
                    result.stdout,
                )
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertFalse((external / runtime_path).exists(), result.stdout)

    def test_normal_install_writes_exact_canonical_manifest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent orchestrator PowerShell install ") as temp:
            home = Path(temp)
            env = os.environ.copy()
            env["HOME"] = str(home)
            env["USERPROFILE"] = str(home)
            env.pop("AGENT_ORCHESTRATOR_HOME", None)

            installed = subprocess.run(
                [PWSH, "-File", str(POWERSHELL_INSTALLER)],
                cwd=ROOT,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )

            self.assertEqual(installed.returncode, 0, installed.stdout)
            self.assertNotIn("Argument types do not match", installed.stdout)

            skill = home / ".agents/skills/agent-orchestrator"
            manifest = skill / ".agent-orchestrator-install.tsv"
            self.assertTrue(manifest.is_file(), installed.stdout)
            records = [line.split("\t") for line in manifest.read_text(encoding="utf-8").splitlines() if line]
            self.assertEqual(len(records), 14)
            self.assertEqual(records[0], ["version", "1.0.0", "-"])

            expected_skill_paths = {
                "SKILL.md",
                "agents/openai.yaml",
                "references/orchestration.md",
                "references/agent-contract.md",
                "references/models.md",
                "references/codex.md",
            }
            expected_agent_names = {
                "backend-worker.toml",
                "docs-worker.toml",
                "explorer-worker.toml",
                "frontend-worker.toml",
                "generic-worker.toml",
                "review-worker.toml",
                "test-worker.toml",
            }
            skill_records = [record for record in records[1:] if record[0] == "skill"]
            agent_records = [record for record in records[1:] if record[0] == "agent"]
            self.assertEqual({record[1] for record in skill_records}, expected_skill_paths)
            self.assertEqual({record[1] for record in agent_records}, expected_agent_names)
            self.assertEqual(len(skill_records), len(expected_skill_paths))
            self.assertEqual(len(agent_records), len(expected_agent_names))
            self.assertNotIn("orchestrator.toml", {record[1] for record in agent_records})
            for record in records[1:]:
                self.assertEqual(len(record), 3)
                self.assertRegex(record[2], r"^[0-9a-f]{64}$")

    def test_check_with_canonical_worker_collision_returns_neutral_report(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent orchestrator PowerShell check ") as temp:
            home = Path(temp)
            agent_dir = home / ".codex/agents"
            agent_dir.mkdir(parents=True)
            collision = agent_dir / "frontend-worker.toml"
            canonical = ROOT / "templates/codex-agents/frontend-worker.toml"
            collision.write_bytes(canonical.read_bytes())

            env = os.environ.copy()
            env["HOME"] = str(home)
            env["USERPROFILE"] = str(home)
            env.pop("AGENT_ORCHESTRATOR_HOME", None)
            result = subprocess.run(
                [PWSH, "-File", str(POWERSHELL_INSTALLER), "-Check"],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("CHECK PASS", result.stdout)
            self.assertIn("frontend-worker.toml", result.stdout)
            self.assertIn("unmanaged", result.stdout.lower())
            self.assertEqual(collision.read_bytes(), canonical.read_bytes())
            self.assertFalse((home / ".agents").exists())


if __name__ == "__main__":
    unittest.main()

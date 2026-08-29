from __future__ import annotations

import re
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class V1PolicyTests(unittest.TestCase):
    def test_manifest_is_single_machine_readable_policy_source(self) -> None:
        path = ROOT / "manifest.toml"
        self.assertTrue(path.is_file(), "v1 requires manifest.toml")
        with path.open("rb") as handle:
            manifest = tomllib.load(handle)
        self.assertEqual(manifest["project"]["version"], "1.0.0")
        self.assertEqual(manifest["project"]["name"], "agent-orchestrator")
        self.assertEqual(manifest["project"]["python_min"], "3.11")
        self.assertEqual(manifest["policy"]["delegation_depth"], 1)
        self.assertFalse(manifest["policy"]["allow_implicit_invocation"])
        self.assertEqual(manifest["policy"]["effort_ladder"], ["medium", "high", "xhigh", "max"])
        self.assertEqual(len(manifest["roles"]), 8)

    def test_verifier_does_not_duplicate_manifest_model_or_effort_allowlists(self) -> None:
        verifier = (ROOT / "scripts/verify.py").read_text(encoding="utf-8")
        self.assertNotIn("VALID_MODELS", verifier)
        self.assertNotIn("VALID_EFFORTS", verifier)

    def test_version_specific_release_names_are_derived_from_manifest(self) -> None:
        with (ROOT / "manifest.toml").open("rb") as handle:
            manifest = tomllib.load(handle)
        version = manifest["project"]["version"]
        self.assertEqual(manifest["release"]["archive"], f"agent-orchestrator-v{version}.zip")
        self.assertEqual(manifest["release"]["root"], f"agent-orchestrator-v{version}")
        verifier = (ROOT / "scripts/verify.py").read_text(encoding="utf-8")
        self.assertNotIn('project.get("version") != "1.0.0"', verifier)
        self.assertNotIn('agent-orchestrator-v1.0.0.zip', verifier)

    def test_workers_are_strictly_one_level_and_never_authorized_to_spawn(self) -> None:
        banned = re.compile(r"authorize(?:s|d)?\s+(?:a\s+)?(?:specific\s+)?nested|nested\s+delegation.*(?:exception|authoriz)", re.I)
        for path in sorted((ROOT / "templates/codex-agents").glob("*.toml")):
            with self.subTest(path=path.name):
                data = tomllib.loads(path.read_text(encoding="utf-8"))
                instructions = data["developer_instructions"]
                if data["name"] != "orchestrator":
                    self.assertIn("Do not spawn subagents", instructions)
                self.assertIsNone(banned.search(instructions), instructions)
        for relative in (
            "SKILL.md",
            "AGENTS.md",
            "references/orchestration.md",
            "references/agent-contract.md",
            "templates/AGENTS.global.md",
            "templates/AGENTS.project.md",
            "README.md",
            "README.zh-CN.md",
            "tests/evals.md",
        ):
            with self.subTest(path=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIsNone(banned.search(text), f"nested-delegation exception remains in {relative}")

    def test_openai_metadata_disables_implicit_invocation(self) -> None:
        text = (ROOT / "agents/openai.yaml").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^\s*allow_implicit_invocation:\s*false\s*$")

    def test_writer_contract_tracks_baseline_protected_changes_and_actual_paths(self) -> None:
        text = (ROOT / "references/agent-contract.md").read_text(encoding="utf-8")
        for marker in ("Contract ID:", "Baseline:", "Protected Existing Changes:", "CHANGED_PATHS"):
            self.assertIn(marker, text)
        orchestration = (ROOT / "references/orchestration.md").read_text(encoding="utf-8")
        self.assertIn("Never revert or overwrite pre-existing user changes", orchestration)
        self.assertIn("changed-path audit", orchestration.lower())

    def test_manual_eval_scenarios_are_reference_only(self) -> None:
        evals = (ROOT / "tests/evals.md").read_text(encoding="utf-8")
        acceptance = (ROOT / "ACCEPTANCE.md").read_text(encoding="utf-8")
        manifest = tomllib.loads((ROOT / "manifest.toml").read_text(encoding="utf-8"))
        self.assertRegex(evals, re.compile(r"optional manual.*not a v1 release gate", re.I | re.S))
        self.assertIn("tests/evals.md", manifest["release"]["include"])
        self.assertNotRegex(acceptance, re.compile(r"manual.*scenario.*(?:required|gate)", re.I | re.S))

    def test_powershell_check_precedes_install_collision_rejection(self) -> None:
        text = (ROOT / "scripts/install-codex.ps1").read_text(encoding="utf-8")
        collision_index = text.index("$Collisions = @(Get-Collisions)")
        check_index = text.index("if ($Check) {", collision_index)
        managed_refusal = text.index("Refusing installation because verified managed target collisions exist", check_index)
        unmanaged_refusal = text.index("Refusing installation because unmanaged or unverified target collisions exist", check_index)
        self.assertLess(check_index, managed_refusal)
        self.assertLess(check_index, unmanaged_refusal)
        check_block = text[check_index:min(managed_refusal, unmanaged_refusal)]
        self.assertIn("CHECK PASS:", check_block)
        self.assertIn("A real installation requires -Force", check_block)
        self.assertIn("-Force will not replace user-owned or unverified targets", check_block)

    def test_primary_orchestrator_is_not_a_dispatchable_custom_agent(self) -> None:
        with (ROOT / "manifest.toml").open("rb") as handle:
            manifest = tomllib.load(handle)
        roles = {role["name"]: role for role in manifest["roles"]}
        primary = roles["orchestrator"]
        self.assertFalse(primary.get("dispatchable", True))
        self.assertNotIn("profile", primary)
        workers = [role for role in manifest["roles"] if role.get("dispatchable", True)]
        self.assertEqual(len(workers), 7)
        self.assertFalse((ROOT / "templates/codex-agents/orchestrator.toml").exists())
        self.assertEqual(len(list((ROOT / "templates/codex-agents").glob("*.toml"))), 7)

    def test_release_allowlist_contains_only_exact_file_paths(self) -> None:
        with (ROOT / "manifest.toml").open("rb") as handle:
            manifest = tomllib.load(handle)
        for relative in manifest["release"]["include"]:
            with self.subTest(relative=relative):
                self.assertNotRegex(relative, r"[*?\[\]]")
                self.assertTrue((ROOT / relative).is_file(), relative)

    def test_custom_worker_dispatch_requires_runtime_profile_confirmation(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        codex = (ROOT / "references/codex.md").read_text(encoding="utf-8")
        combined = skill + "\n" + codex
        self.assertRegex(combined, re.compile(r"runtime.*(?:select|confirm).*custom.*profile|custom.*profile.*runtime.*(?:select|confirm)", re.I | re.S))
        self.assertRegex(combined, re.compile(r"do not.*(?:generic|default).*child.*(?:claim|label)|do not.*claim.*(?:role|model)", re.I | re.S))
        self.assertRegex(combined, re.compile(r"worker.*unavailable|routing.*unavailable", re.I))

    def test_examples_do_not_parallelize_writers_in_a_shared_checkout(self) -> None:
        web = (ROOT / "examples/web-project.md").read_text(encoding="utf-8")
        self.assertRegex(web, re.compile(r"parallel.*isolated.*(?:worktree|execution root)|isolated.*(?:worktree|execution root).*parallel", re.I | re.S))

    def test_shared_checkout_writers_are_serialized_and_readers_are_audited(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        orchestration = (ROOT / "references/orchestration.md").read_text(encoding="utf-8")
        combined = skill + "\n" + orchestration
        self.assertRegex(combined, re.compile(r"shared mutable (?:checkout|worktree).*serial", re.I | re.S))
        self.assertRegex(orchestration, re.compile(r"read-only.*no-mutation audit|no-mutation audit.*read-only", re.I | re.S))

    def test_policy_never_suggests_parallel_writers_in_a_shared_checkout(self) -> None:
        for relative in ("AGENTS.md", "templates/AGENTS.global.md", "templates/AGENTS.project.md", "SKILL.md", "references/orchestration.md"):
            with self.subTest(relative=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertNotRegex(text, re.compile(r"parallelize\s+(?:readers\s+and\s+)?disjoint\s+writers", re.I))
                self.assertRegex(text, re.compile(r"shared mutable (?:checkout|worktree).*serial", re.I | re.S))

    def test_codex_config_avoids_v2_thread_limit_conflict_and_pins_v1_depth(self) -> None:
        config = tomllib.loads((ROOT / "templates/codex-config.toml").read_text(encoding="utf-8"))
        agents = config.get("agents", {})
        self.assertTrue(agents.get("enabled"))
        self.assertEqual(agents.get("max_depth"), 1)
        self.assertNotIn("max_concurrent_threads_per_session", agents)
        self.assertNotIn("max_threads", agents)
        codex = (ROOT / "references/codex.md").read_text(encoding="utf-8")
        self.assertRegex(codex, re.compile(r"multi-agent v2.*(?:conflict|do not set|omit).*thread|thread.*multi-agent v2", re.I | re.S))
        self.assertRegex(codex, re.compile(r"max_depth.*v1.*(?:ignored|not enforced).*v2|v2.*(?:ignores|ignored).*max_depth", re.I | re.S))

    def test_primary_model_defaults_are_not_claimed_as_installer_enforced(self) -> None:
        codex = (ROOT / "references/codex.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        combined = codex + "\n" + readme
        self.assertRegex(combined, re.compile(r"installer.*(?:does not|doesn't).*config\.toml|does not.*overwrite.*codex.*config", re.I | re.S))
        self.assertRegex(combined, re.compile(r"primary.*(?:model|sol).*runtime.*(?:confirm|visible)|runtime.*(?:model|session).*primary.*sol", re.I | re.S))

    def test_untrusted_content_cannot_override_orchestration_policy(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        orchestration = (ROOT / "references/orchestration.md").read_text(encoding="utf-8")
        combined = skill + "\n" + orchestration
        self.assertRegex(combined, re.compile(r"(?:repository|source|log|web).*untrusted.*(?:data|content)|prompt injection", re.I | re.S))
        self.assertRegex(combined, re.compile(r"(?:must not|never).*override.*(?:contract|policy|instructions)|cannot override.*(?:contract|policy)", re.I | re.S))
        for path in sorted((ROOT / "templates/codex-agents").glob("*.toml")):
            with self.subTest(profile=path.name):
                data = tomllib.loads(path.read_text(encoding="utf-8"))
                self.assertRegex(data["developer_instructions"], re.compile(r"untrusted.*(?:data|content)|prompt injection", re.I | re.S))

    def test_windows_ci_treats_unmanaged_check_collision_as_blocked_not_force_required(self) -> None:
        workflow = (ROOT / ".github/workflows/validate.yml").read_text(encoding="utf-8")
        self.assertIn("user-owned", workflow)
        self.assertRegex(workflow, re.compile(r"checkOutput.*(?:blocked|will not replace).*unmanaged|unmanaged.*checkOutput.*(?:blocked|will not replace)", re.I | re.S))
        self.assertNotRegex(workflow, re.compile(r"\$checkOutput[^\n]*requires -Force", re.I))


    def test_verifier_enforces_codex_runtime_compatibility_policy(self) -> None:
        verifier = (ROOT / "scripts/verify.py").read_text(encoding="utf-8")
        self.assertRegex(verifier, re.compile(r"max_depth.*1", re.I | re.S))
        self.assertIn("max_concurrent_threads_per_session", verifier)
        self.assertIn("max_threads", verifier)
        self.assertRegex(verifier, re.compile(r"untrusted.*(?:data|content)|prompt injection", re.I | re.S))

    def test_powershell_uninstall_audits_untracked_skill_content(self) -> None:
        text = (ROOT / "scripts/install-codex.ps1").read_text(encoding="utf-8")
        self.assertIn("Get-ExpectedInstalledSkillEntries", text)
        self.assertIn("unmanaged extra content", text)
        self.assertRegex(text, re.compile(r"Read-ManagedManifest.*ReparsePoint", re.I | re.S))
        workflow = (ROOT / ".github/workflows/validate.yml").read_text(encoding="utf-8")
        self.assertIn("user-note.txt", workflow)
        self.assertRegex(workflow, re.compile(r"user-note\.txt.*requires -Force|requires -Force.*user-note\.txt", re.I | re.S))

    def test_powershell_protects_legacy_orchestrator_ownership(self) -> None:
        text = (ROOT / "scripts/install-codex.ps1").read_text(encoding="utf-8")
        self.assertIn("legacy_orchestrator_sha256", text)
        self.assertIn("Get-LegacyOrchestratorStatus", text)
        self.assertRegex(text, re.compile(r"orchestrator\.toml.*blocked.*-Force|-Force.*orchestrator\.toml.*blocked", re.I | re.S))
        self.assertIn("LegacyOrchestratorBackedUp", text)
        self.assertIn("LegacyManagedOwnershipUnknown", text)

    def test_powershell_force_only_replaces_verified_managed_collisions(self) -> None:
        text = (ROOT / "scripts/install-codex.ps1").read_text(encoding="utf-8")
        self.assertIn("Get-CollisionOwnership", text)
        self.assertIn("CollisionState.Unmanaged", text)
        self.assertRegex(text, re.compile(r"-Force.*(?:will not|does not).*unmanaged|unmanaged.*-Force.*(?:will not|does not)", re.I | re.S))

    def test_powershell_source_validation_rejects_reparse_components(self) -> None:
        text = (ROOT / "scripts/install-codex.ps1").read_text(encoding="utf-8")
        self.assertIn("Get-SafeInstallerSourceItem", text)
        self.assertRegex(text, re.compile(r"Get-SafeInstallerSourceItem.*ReparsePoint", re.S))

    def test_powershell_install_manifest_uses_exact_skill_runtime_set(self) -> None:
        text = (ROOT / "scripts/install-codex.ps1").read_text(encoding="utf-8")
        self.assertIn("ExpectedSkillPaths", text)
        self.assertIn("unknown managed Skill", text)

    def test_windows_installer_requires_and_documents_powershell_7(self) -> None:
        script = (ROOT / "scripts/install-codex.ps1").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        readme_zh = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
        codex = (ROOT / "references/codex.md").read_text(encoding="utf-8")
        self.assertRegex(script, re.compile(r"PSVersionTable.*Major.*(?:-lt|<)\s*7", re.I | re.S))
        self.assertRegex(readme, re.compile(r"PowerShell 7|pwsh", re.I))
        self.assertIn("pwsh", readme_zh)
        self.assertRegex(codex, re.compile(r"PowerShell 7.*pwsh", re.I | re.S))
        self.assertNotRegex(readme, re.compile(r"(?m)^powershell\s+-ExecutionPolicy"))
        self.assertNotRegex(readme_zh, re.compile(r"(?m)^powershell\s+-ExecutionPolicy"))

    def test_powershell_success_paths_return_to_caller(self) -> None:
        text = (ROOT / "scripts/install-codex.ps1").read_text(encoding="utf-8")
        self.assertNotRegex(text, re.compile(r"(?im)^\s*exit\s+0\s*$"))


if __name__ == "__main__":
    unittest.main()

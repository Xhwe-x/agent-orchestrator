from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import shutil
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("agent_orchestrator_verify", ROOT / "scripts/verify.py")
assert SPEC and SPEC.loader
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)


class ReleaseManifestTests(unittest.TestCase):
    def assert_verification_fails(self, fn, *args) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit):
                fn(*args)

    def test_release_entries_are_allowlist_driven(self) -> None:
        manifest = ROOT / "manifest.toml"
        self.assertTrue(manifest.is_file(), "v1 requires manifest.toml")
        entries = verify.release_entries()
        self.assertIn("manifest.toml", entries)
        self.assertIn("SKILL.md", entries)
        self.assertNotIn("HANDOFF.md", entries)

    def test_unlisted_file_is_not_packaged(self) -> None:
        marker = ROOT / "local-debug-secret.txt"
        marker.write_text("must not be packaged", encoding="utf-8")
        try:
            entries = verify.release_entries()
            self.assertNotIn(marker.name, entries)
        finally:
            marker.unlink(missing_ok=True)

    def test_manifest_rejects_parent_traversal_allowlist_pattern(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_root = Path(temp) / "repo"
            temp_root.mkdir()
            outside = temp_root.parent / "outside.txt"
            outside.write_text("outside", encoding="utf-8")
            manifest = verify.load_manifest()
            manifest["release"] = {
                "archive": "agent-orchestrator-v1.0.0.zip",
                "root": "agent-orchestrator-v1.0.0",
                "include": ["../outside.txt"],
                "executable": [],
                "digest_excludes": [],
            }
            with mock.patch.object(verify, "ROOT", temp_root), mock.patch.object(verify, "load_manifest", return_value=manifest):
                self.assert_verification_fails(verify.release_entries)

    def test_manifest_rejects_symlinked_parent_directory(self) -> None:
        if os.name == "nt":
            self.skipTest("symlink permissions vary on Windows")
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside_temp:
            temp_root = Path(temp)
            outside_root = Path(outside_temp)
            (outside_root / "secret.txt").write_text("outside", encoding="utf-8")
            (temp_root / "linked-dir").symlink_to(outside_root, target_is_directory=True)
            manifest = verify.load_manifest()
            manifest["release"] = {
                "archive": "agent-orchestrator-v1.0.0.zip",
                "root": "agent-orchestrator-v1.0.0",
                "include": ["linked-dir/secret.txt"],
                "executable": [],
                "digest_excludes": [],
            }
            with mock.patch.object(verify, "ROOT", temp_root), mock.patch.object(verify, "load_manifest", return_value=manifest):
                self.assert_verification_fails(verify.release_entries)

    def test_manifest_rejects_release_metadata_outside_include_set(self) -> None:
        manifest = verify.load_manifest()
        manifest["release"] = dict(manifest["release"])
        manifest["release"]["digest_excludes"] = ["not-in-release.txt"]
        with mock.patch.object(verify, "load_manifest", return_value=manifest):
            self.assert_verification_fails(verify.verify_manifest)

    def test_manifest_rejects_symlink_member(self) -> None:
        if os.name == "nt":
            self.skipTest("symlink permissions vary on Windows")
        with tempfile.TemporaryDirectory() as temp:
            temp_root = Path(temp)
            shutil.copy2(ROOT / "manifest.toml", temp_root / "manifest.toml")
            (temp_root / "target.txt").write_text("x", encoding="utf-8")
            (temp_root / "linked.txt").symlink_to(temp_root / "target.txt")
            manifest = verify.load_manifest()
            manifest["release"] = {
                "archive": "agent-orchestrator-v1.0.0.zip",
                "root": "agent-orchestrator-v1.0.0",
                "include": ["linked.txt"],
                "executable": [],
                "digest_excludes": [],
            }
            with mock.patch.object(verify, "ROOT", temp_root), mock.patch.object(verify, "load_manifest", return_value=manifest):
                self.assert_verification_fails(verify.release_entries)

    def test_shell_installer_keeps_executable_mode_in_release(self) -> None:
        entries = verify.release_entries()
        self.assertEqual(entries["scripts/install-codex.sh"][1], 0o755)

    def _write_archive(self, path: Path, mutate=None, extra=None, name_mutate=None) -> dict[str, tuple[bytes, int]]:
        entries = verify.release_entries()
        _, release_root, _, _, _ = verify._release_config()
        with zipfile.ZipFile(path, "w") as archive:
            for relative in sorted(entries):
                data, mode = entries[relative]
                if mutate:
                    data, mode = mutate(relative, data, mode)
                member_name = f"{release_root}/{relative}"
                if name_mutate:
                    member_name = name_mutate(relative, member_name)
                info = zipfile.ZipInfo(member_name, date_time=verify.RELEASE_FIXED_TIME)
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | mode) << 16
                archive.writestr(info, data)
            if extra:
                extra(archive, release_root)
        return entries

    def test_archive_rejects_modified_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.zip"
            def mutate(relative, data, mode):
                if relative == "SKILL.md":
                    data += b"\nmutation\n"
                return data, mode
            entries = self._write_archive(path, mutate=mutate)
            with mock.patch.object(verify, "_run_extracted_self_check", lambda _root: None):
                self.assert_verification_fails(verify.verify_release_archive, path, entries)

    def test_archive_rejects_wrong_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.zip"
            def mutate(relative, data, mode):
                if relative == "scripts/install-codex.sh":
                    mode = 0o644
                return data, mode
            entries = self._write_archive(path, mutate=mutate)
            with mock.patch.object(verify, "_run_extracted_self_check", lambda _root: None):
                self.assert_verification_fails(verify.verify_release_archive, path, entries)

    def test_archive_rejects_noncanonical_member_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.zip"
            def name_mutate(relative, member_name):
                if relative == "SKILL.md":
                    return member_name.replace("/SKILL.md", "//SKILL.md")
                return member_name
            entries = self._write_archive(path, name_mutate=name_mutate)
            with mock.patch.object(verify, "_run_extracted_self_check", lambda _root: None):
                self.assert_verification_fails(verify.verify_release_archive, path, entries)

    def test_archive_rejects_path_traversal_member(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.zip"
            def extra(archive, release_root):
                info = zipfile.ZipInfo(f"{release_root}/../escape.txt", date_time=verify.RELEASE_FIXED_TIME)
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                archive.writestr(info, b"escape")
            entries = self._write_archive(path, extra=extra)
            with mock.patch.object(verify, "_run_extracted_self_check", lambda _root: None):
                self.assert_verification_fails(verify.verify_release_archive, path, entries)

    def test_archive_rejects_case_ambiguous_member(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.zip"
            def extra(archive, release_root):
                info = zipfile.ZipInfo(f"{release_root}/skill.md", date_time=verify.RELEASE_FIXED_TIME)
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                archive.writestr(info, b"ambiguous")
            entries = self._write_archive(path, extra=extra)
            with mock.patch.object(verify, "_run_extracted_self_check", lambda _root: None):
                self.assert_verification_fails(verify.verify_release_archive, path, entries)

    def test_archive_rejects_non_regular_member(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.zip"
            entries = verify.release_entries()
            _, release_root, _, _, _ = verify._release_config()
            with zipfile.ZipFile(path, "w") as archive:
                for relative in sorted(entries):
                    data, mode = entries[relative]
                    info = zipfile.ZipInfo(f"{release_root}/{relative}", date_time=verify.RELEASE_FIXED_TIME)
                    info.create_system = 3
                    if relative == "SKILL.md":
                        info.external_attr = (stat.S_IFIFO | mode) << 16
                    else:
                        info.external_attr = (stat.S_IFREG | mode) << 16
                    archive.writestr(info, data)
            with mock.patch.object(verify, "_run_extracted_self_check", lambda _root: None):
                self.assert_verification_fails(verify.verify_release_archive, path, entries)

    def test_manifest_rejects_invalid_legacy_orchestrator_fingerprint(self) -> None:
        manifest = verify.load_manifest()
        manifest["compatibility"] = {"legacy_orchestrator_sha256": ["not-a-sha256"]}
        with mock.patch.object(verify, "load_manifest", return_value=manifest):
            self.assert_verification_fails(verify.verify_manifest)

    def test_manifest_rejects_glob_allowlist_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_root = Path(temp)
            (temp_root / "a.txt").write_text("a", encoding="utf-8")
            manifest = verify.load_manifest()
            manifest["release"] = {
                "archive": "agent-orchestrator-v1.0.0.zip",
                "root": "agent-orchestrator-v1.0.0",
                "include": ["*.txt"],
                "executable": [],
                "digest_excludes": [],
            }
            with mock.patch.object(verify, "ROOT", temp_root), mock.patch.object(verify, "load_manifest", return_value=manifest):
                self.assert_verification_fails(verify.release_entries)

    def test_release_path_rejects_windows_reserved_name(self) -> None:
        self.assert_verification_fails(verify._safe_release_relative, "docs/CON.txt")

    def test_release_path_requires_nfc_normalization(self) -> None:
        self.assert_verification_fails(verify._safe_release_relative, "docs/cafe\u0301.md")

    def test_canonical_archive_uses_stored_members_for_cross_runtime_reproducibility(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "canonical.zip"
            entries = verify.release_entries()
            verify.build_release_archive(path, entries)
            with zipfile.ZipFile(path) as archive:
                self.assertTrue(archive.infolist())
                self.assertTrue(all(info.compress_type == zipfile.ZIP_STORED for info in archive.infolist()))

    def test_archive_rejects_noncanonical_compression(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "deflated.zip"
            entries = verify.release_entries()
            _, release_root, _, _, _ = verify._release_config()
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for relative in sorted(entries):
                    data, mode = entries[relative]
                    info = zipfile.ZipInfo(f"{release_root}/{relative}", date_time=verify.RELEASE_FIXED_TIME)
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.create_system = 3
                    info.external_attr = (stat.S_IFREG | mode) << 16
                    archive.writestr(info, data)
            with mock.patch.object(verify, "_run_extracted_self_check", lambda _root: None):
                self.assert_verification_fails(verify.verify_release_archive, path, entries)

    def test_archive_rejects_noncanonical_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "timestamp.zip"
            entries = verify.release_entries()
            _, release_root, _, _, _ = verify._release_config()
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
                for relative in sorted(entries):
                    data, mode = entries[relative]
                    stamp = (2025, 1, 1, 0, 0, 0) if relative == "SKILL.md" else verify.RELEASE_FIXED_TIME
                    info = zipfile.ZipInfo(f"{release_root}/{relative}", date_time=stamp)
                    info.compress_type = zipfile.ZIP_STORED
                    info.create_system = 3
                    info.external_attr = (stat.S_IFREG | mode) << 16
                    archive.writestr(info, data)
            with mock.patch.object(verify, "_run_extracted_self_check", lambda _root: None):
                self.assert_verification_fails(verify.verify_release_archive, path, entries)

    def test_archive_rejects_archive_comment(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "comment.zip"
            entries = verify.release_entries()
            verify.build_release_archive(path, entries)
            with zipfile.ZipFile(path, "a") as archive:
                archive.comment = b"unexpected"
            with mock.patch.object(verify, "_run_extracted_self_check", lambda _root: None):
                self.assert_verification_fails(verify.verify_release_archive, path, entries)

    def test_archive_rejects_member_extra_field(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "extra.zip"
            entries = verify.release_entries()
            _, release_root, _, _, _ = verify._release_config()
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
                for relative in sorted(entries):
                    data, mode = entries[relative]
                    info = zipfile.ZipInfo(f"{release_root}/{relative}", date_time=verify.RELEASE_FIXED_TIME)
                    info.compress_type = zipfile.ZIP_STORED
                    info.create_system = 3
                    info.external_attr = (stat.S_IFREG | mode) << 16
                    if relative == "SKILL.md":
                        info.extra = b"\x0a\x00\x00\x00"
                    archive.writestr(info, data)
            with mock.patch.object(verify, "_run_extracted_self_check", lambda _root: None):
                self.assert_verification_fails(verify.verify_release_archive, path, entries)

    def test_archive_rejects_special_permission_bits(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "setuid.zip"
            entries = verify.release_entries()
            _, release_root, _, _, _ = verify._release_config()
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for relative in sorted(entries):
                    data, mode = entries[relative]
                    info = zipfile.ZipInfo(f"{release_root}/{relative}", date_time=verify.RELEASE_FIXED_TIME)
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.create_system = 3
                    actual_mode = mode | (stat.S_ISUID if relative == "SKILL.md" else 0)
                    info.external_attr = (stat.S_IFREG | actual_mode) << 16
                    archive.writestr(info, data)
            with mock.patch.object(verify, "_run_extracted_self_check", lambda _root: None):
                self.assert_verification_fails(verify.verify_release_archive, path, entries)

    def test_archive_rejects_leading_or_trailing_junk(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            good = Path(temp) / "good.zip"
            entries = verify.release_entries()
            verify.build_release_archive(good, entries)
            raw = good.read_bytes()
            for name, bad_bytes in (("leading.zip", b"junk" + raw), ("trailing.zip", raw + b"junk")):
                path = Path(temp) / name
                path.write_bytes(bad_bytes)
                with self.subTest(name=name), mock.patch.object(verify, "_run_extracted_self_check", lambda _root: None):
                    self.assert_verification_fails(verify.verify_release_archive, path, entries)


if __name__ == "__main__":
    unittest.main()

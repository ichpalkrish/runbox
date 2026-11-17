from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import session  # noqa: E402


class SessionWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="runbox-session-test-")
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.state = self.root / "state"
        self.state.mkdir()
        self._git("init", "--quiet")
        self._git("config", "user.name", "Session Test")
        self._git("config", "user.email", "session-test@example.invalid")
        (self.repo / ".gitignore").write_text("build/\n", encoding="utf-8")
        (self.repo / "README.md").write_text("base\n", encoding="utf-8")
        (self.repo / "remove.txt").write_text("remove me\n", encoding="utf-8")
        (self.repo / "run.sh").write_text("#!/bin/sh\necho base\n", encoding="utf-8")
        (self.repo / "run.sh").chmod(0o755)
        (self.repo / "asset.bin").write_bytes(b"\x00\xffold\x00payload\n")
        (self.repo / "build").mkdir()
        (self.repo / "build" / "tracked-output.bin").write_bytes(b"generated but tracked")
        self._git("add", "-A")
        self._git("add", "-f", "build/tracked-output.bin")
        self._git("commit", "--quiet", "-m", "base")
        self.base = session.current_head(self.repo)
        base_paths = session.git_paths(self.repo, self.base)
        ignored = session.check_ignored(self.repo, base_paths)
        self.exported = [path for path in base_paths if path not in ignored]

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _git(self, *args: str) -> bytes:
        result = subprocess.run(["git", *args], cwd=self.repo, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, check=True)
        return result.stdout

    def _prepare_patch(self) -> tuple[str, Path, list[str]]:
        snapshot = self.state / "snapshot"
        snapshot.mkdir()
        session.add_snapshot_tree(self.repo, self.base, snapshot, self.exported)

        # Simulate the edits made in the disposable VM source directory.
        remote = self.state / "remote-source"
        remote.mkdir()
        for current, dirs, files in os.walk(snapshot):
            relative = Path(current).relative_to(snapshot)
            target_dir = remote / relative
            target_dir.mkdir(parents=True, exist_ok=True)
            for name in files:
                source = Path(current) / name
                target = target_dir / name
                target.write_bytes(source.read_bytes())
                target.chmod(source.stat().st_mode & 0o777)
        (remote / "README.md").write_text("edited on VM\n", encoding="utf-8")
        (remote / "remove.txt").unlink()
        (remote / "run.sh").chmod(0o644)
        (remote / "asset.bin").write_bytes(b"\x00\x01new\xffbinary\x00payload\n")
        added = remote / "new\nfile.bin"
        added.write_bytes(b"\x00VM added binary\xff")
        (remote / "build").mkdir()
        (remote / "build" / "output.bin").write_bytes(b"generated")
        remote_paths = [
            path.relative_to(remote).as_posix()
            for path in remote.rglob("*")
            if path.is_file()
        ]
        selected = session.select_return_paths(self.repo, {
            "exported_paths": self.exported,
            "base_commit": self.base,
        }, remote_paths)
        self.assertNotIn("build/output.bin", selected)
        returned = self.state / "returned"
        returned.mkdir()
        for relative in selected:
            target = returned / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((remote / relative).read_bytes())
            target.chmod((remote / relative).stat().st_mode & 0o777)

        scratch = self.state / "patch-tree"
        scratch.mkdir()
        index = self.state / "tree.index"
        session.create_scratch_index(self.repo, self.base, scratch, index)
        session.remove_exported_baseline_paths(scratch, self.exported)
        session.overlay_return_tree(scratch, returned, selected)
        patch, changed = session.generate_patch(self.repo, self.base, scratch, self.state)

        session_id = "20261117T120000Z-0123abcd"
        directory = session.session_directory(self.state, session_id)
        directory.mkdir()
        manifest = {
            "format_version": session.FORMAT_VERSION,
            "session_id": session_id,
            "repo_root": str(self.repo.resolve()),
            "base_commit": self.base,
            "exported_paths": self.exported,
            "status": "collected",
        }
        session.write_manifest(directory / "manifest.json", manifest)
        (directory / "patch.diff").write_bytes(patch)
        result = {
            "session_id": session_id,
            "base_commit": self.base,
            "patch_sha256": hashlib.sha256(patch).hexdigest(),
            "changed_paths": changed,
        }
        (directory / "result.json").write_text(json.dumps(result), encoding="utf-8")
        return session_id, directory, changed

    def test_binary_add_delete_mode_and_newline_paths_roundtrip(self) -> None:
        session_id, directory, changed = self._prepare_patch()
        self.assertIn("asset.bin", changed)
        self.assertIn("remove.txt", changed)
        self.assertIn("run.sh", changed)
        self.assertIn("new\nfile.bin", changed)
        self.assertNotIn("build/output.bin", changed)
        patch = (directory / "patch.diff").read_bytes()
        self.assertIn(b"GIT binary patch", patch)

        applied = session.apply_session(self.repo, self.state, session_id)
        self.assertEqual(set(changed), set(applied))
        self.assertEqual((self.repo / "README.md").read_text(encoding="utf-8"), "edited on VM\n")
        self.assertFalse((self.repo / "remove.txt").exists())
        self.assertEqual((self.repo / "asset.bin").read_bytes(), b"\x00\x01new\xffbinary\x00payload\n")
        self.assertEqual((self.repo / "new\nfile.bin").read_bytes(), b"\x00VM added binary\xff")
        self.assertEqual((self.repo / "run.sh").stat().st_mode & 0o777, 0o644)
        self.assertEqual((self.repo / "build" / "tracked-output.bin").read_bytes(), b"generated but tracked")
        self.assertFalse((self.repo / "build" / "output.bin").exists())

    def test_apply_refuses_dirty_checkout_without_applying_patch(self) -> None:
        session_id, _, _ = self._prepare_patch()
        (self.repo / "local-change.txt").write_text("local\n", encoding="utf-8")
        with self.assertRaisesRegex(session.SessionError, "must be clean"):
            session.apply_session(self.repo, self.state, session_id)
        self.assertEqual((self.repo / "README.md").read_text(encoding="utf-8"), "base\n")

    def test_apply_refuses_a_different_head(self) -> None:
        session_id, _, _ = self._prepare_patch()
        self._git("commit", "--allow-empty", "--quiet", "-m", "move base")
        with self.assertRaisesRegex(session.SessionError, "HEAD differs"):
            session.apply_session(self.repo, self.state, session_id)
        self.assertEqual((self.repo / "README.md").read_text(encoding="utf-8"), "base\n")

    def test_safe_extractor_rejects_traversal_and_symlinks(self) -> None:
        archive_path = self.state / "bad.tar"
        with tarfile.open(archive_path, "w") as archive:
            info = tarfile.TarInfo("../outside.txt")
            info.size = 1
            import io
            archive.addfile(info, io.BytesIO(b"x"))
        destination = self.state / "extract"
        with self.assertRaises(session.SessionError):
            session.safe_extract_regular_tar(archive_path, destination, {"../outside.txt"})
        self.assertFalse((self.root / "outside.txt").exists())

        symlink_archive = self.state / "symlink.tar"
        with tarfile.open(symlink_archive, "w") as archive:
            link = tarfile.TarInfo("link")
            link.type = tarfile.SYMTYPE
            link.linkname = "../../outside"
            archive.addfile(link)
        with self.assertRaisesRegex(session.SessionError, "symlink"):
            session.safe_extract_regular_tar(symlink_archive, self.state / "extract-link", {"link"})

    def test_rejects_ssh_option_hosts_and_missing_remote_workspaces(self) -> None:
        with self.assertRaises(session.SessionError):
            session.validate_host("-oProxyCommand=bad")

        missing = self.root / "missing-workspace"
        result = subprocess.run(
            [sys.executable, "-c", session.REMOTE_LIST_SCRIPT, str(missing)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")

    def test_start_blocks_tracked_env_secrets_before_ssh(self) -> None:
        (self.repo / ".env").write_text("TOKEN=not-a-real-secret\n", encoding="utf-8")
        self._git("add", "-f", ".env")
        self._git("commit", "--quiet", "-m", "add env")
        with self.assertRaisesRegex(session.SessionError, "credential-like"):
            session.start_session(self.repo, self.state, "vm", "/tmp/runbox-test-workspaces")


if __name__ == "__main__":
    unittest.main()

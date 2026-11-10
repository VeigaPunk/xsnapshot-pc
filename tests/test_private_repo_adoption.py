"""Clone adoption: synthetic bare remotes and non-linked worktrees only."""
import os
import subprocess
import unittest
from unittest.mock import patch

from lib import xsnapshot_repo as repo
from tests.private_repo_fixture import PrivateRepositoryFixture

class AdoptionTest(PrivateRepositoryFixture, unittest.TestCase):
    def raw_git(self, directory, *args):
        result = subprocess.run(["/usr/bin/git", "-C", directory, *args], env=os.environ,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout


    """Two ordinary nonlinked worktrees use local bare fixtures."""
    def adopt_clone(self, identifier):
        self.git(str(self.base), "clone", str(self.remote), identifier)
        self.state = self.base / identifier

    def initialize_remote(self, identifier="source", snapshot_id="first"):
        self.valid_snapshot(snapshot_id)
        self.invoke("init", "--remote", str(self.remote))
        code, out, err = self.invoke("update", "--no-capture", "--assume-private")
        self.assertEqual(code, 0, out + err)
        self.git(str(self.base), "clone", str(self.remote), identifier)

    def test_format_marker_and_full_clone_continuation(self):
        self.valid_snapshot()
        code, out, err = self.invoke("init", "--remote", str(self.remote))
        self.assertEqual(code, 2)  # Local bare cannot attest privacy by itself.
        self.assertIn(repo.REPOSITORY_MARKER, self.git(str(self.state), "ls-tree", "--name-only", "HEAD"))
        self.assertEqual(self.invoke("update", "--no-capture", "--assume-private")[0], 0)
        self.git(str(self.base), "clone", str(self.remote), "second")
        second = self.base / "second"
        self.state = second
        for operation in [["status"], ["update", "--no-capture", "--assume-private"]]:
            code, out, err = self.invoke(*operation)
            self.assertEqual(code, 2, out + err)
            self.assertIn("init", out + err)
            self.assertIn("adopt", out + err)
        code, out, err = self.invoke("init", "--no-remote")
        self.assertEqual(code, 0, out + err)
        self.assertIn("Adopting", out)
        self.assertEqual(self.git(str(second), "config", "--local", repo.MARKER), "private-repository")
        self.assertEqual((second / ".git/info/attributes").read_bytes(), repo.ATTRIBUTES)
        self.valid_snapshot("second-snapshot", captured="2026-02-03T13:00:00+00:00")
        self.assertEqual(self.invoke("update", "--no-capture", "--assume-private")[0], 0)
        first = self.base / "state"
        self.git(str(first), "pull", "--ff-only", str(self.remote), "main")
        self.assertIn("second-snapshot", self.git(str(first), "log", "-1", "--format=%s"))
        self.assertEqual(self.git(str(second), "rev-parse", "HEAD"), self.git(str(first), "rev-parse", "HEAD"))

    def test_foreign_history_rejected_even_with_valid_marker(self):
        self.initialize_remote("second", "unchanged")
        second = self.base / "second"
        (second / "foreign-file.txt").write_text("unrelated historical file\n")
        self.git(str(second), "add", "foreign-file.txt")
        self.git(str(second), "-c", "user.name=Synthetic", "-c", "user.email=synthetic@example.invalid",
                 "commit", "-m", "foreign commit")
        self.state = second
        code, out, err = self.invoke("init", "--no-remote")
        self.assertEqual(code, 2)
        self.assertIn("did not create or cannot verify", out + err)
        self.assertNotIn(repo.MARKER, self.git(str(second), "config", "--local", "--list"))

    def test_unknown_marker_version_is_refused(self):
        self.initialize_remote("future")
        marker = self.base / "future" / repo.REPOSITORY_MARKER
        marker.write_text('{"format": 9067}')
        self.git(str(marker.parent), "add", repo.REPOSITORY_MARKER)
        self.git(str(marker.parent), "-c", "user.name=Synthetic", "-c", "user.email=future@example.invalid",
                 "commit", "-m", "synthetic marker mismatch")
        self.state = marker.parent
        code, out, err = self.invoke("init", "--no-remote")
        self.assertEqual(code, 2)
        self.assertFalse(repo._clone_is_adoptable(marker.parent))

    def test_dirty_clone_is_refused_and_uncommitted_new_snapshots_are_allowed(self):
        self.initialize_remote("worktree")
        self.state = self.base / "worktree"
        (self.state / "README.md").write_text("local modification\n")
        code, out, err = self.invoke("init", "--no-remote")
        self.assertEqual(code, 2)
        self.git(str(self.state), "restore", "README.md")  # Test prepares separate pending case.

    def test_clone_still_neutralizes_in_tree_filter_before_any_new_commit(self):
        self.initialize_remote("filtered-clone", "tampered-byte-fixture")
        snap = self.state / "snapshots/tampered-byte-fixture"
        body = b"clone-checked CRLF and binary NUL\r\n\x00sealed\n"
        source = snap / "applied/example.conf"
        source.write_bytes(body)
        (snap / ".gitattributes").write_bytes(b"* filter=danger ident text working-tree-encoding=UTF-16\n")
        self.refresh_snapshot(snap)
        self.git(str(self.state), "add", "snapshots/tampered-byte-fixture")
        self.git(str(self.state), "-c", "user.name=Synthetic", "-c", "user.email=fixture@example.invalid",
                 "commit", "-m", "synthetic signed hostile attributes retention")
        canary = self.base / "filter-ran"
        program = self.base / "filter-program"
        program.write_text("#!/bin/sh\ntouch " + str(canary) + "\n")
        program.chmod(0o700)
        self.git(str(self.state), "config", "filter.danger.clean", str(program))
        self.assertEqual(self.invoke("init", "--no-remote")[0], 0)
        self.assertEqual(self.raw_git(self.state, "cat-file", "blob", "HEAD:snapshots/tampered-byte-fixture/applied/example.conf"), body)
        self.assertFalse(canary.exists())


    def test_history_ceiling_fails_closed(self):
        with patch.object(repo, "MAX_HISTORY_COMMITS", 1):
            self.valid_snapshot(); self.init_local()
            self.valid_snapshot("second", captured="2026-09-01T00:00:00+00:00")
            self.invoke("update", "--no-capture", "--no-push")
            with patch.object(repo, "MAX_HISTORY_COMMITS", 1):
                self.assertFalse(repo._clone_is_adoptable(self.state))

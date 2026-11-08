"""Private-output and orchestration fixtures. No workstation inventory is run."""
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from lib import xsnapshot as x


class PrivateOutputTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.out = self.root / "capture"
        self.collector = x.Collector(self.root, self.out, sudo=False)

    def tearDown(self):
        self.tmp.cleanup()

    def test_open_umask_cannot_make_directories_or_files_public(self):
        previous = os.umask(0)
        try:
            self.collector.write("system/nested/info.txt", "synthetic inventory")
            source = self.root / "synthetic.conf"
            source.write_text("password=synthetic-secret\n")
            self.collector.copy_file(source, "etc/example.conf")
            self.collector.write_manifest()
        finally:
            os.umask(previous)
        for path in [self.out, *self.out.rglob("*")]:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700 if path.is_dir() else 0o600, path)
        self.assertNotIn("synthetic-secret", (self.out / "etc/example.conf").read_text())
        self.assertEqual(len(self.collector.config_index), 1)
        for row in self.collector.artifacts:
            body = (self.out / row["path"]).read_bytes()
            self.assertEqual(row["bytes"], len(body))
            self.assertEqual(row["sha256"], hashlib.sha256(body).hexdigest())

    def test_existing_nonprivate_output_is_refused_without_chmod(self):
        self.out.mkdir(mode=0o755)
        self.out.chmod(0o755)
        with self.assertRaises(PermissionError):
            self.collector.write("private.txt", "synthetic")
        self.assertEqual(stat.S_IMODE(self.out.stat().st_mode), 0o755)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_nonprivate_child_directory_is_refused_without_chmod(self):
        self.out.mkdir(mode=0o700)
        child = self.out / "etc"
        child.mkdir(mode=0o755)
        child.chmod(0o755)
        with self.assertRaises(PermissionError):
            self.collector.write("etc/example.conf", "synthetic")
        self.assertEqual(stat.S_IMODE(child.stat().st_mode), 0o755)
        self.assertFalse((child / "example.conf").exists())

    def test_root_and_child_symlinks_cannot_redirect_output(self):
        target = self.root / "outside"
        target.mkdir(mode=0o700)
        self.out.symlink_to(target, target_is_directory=True)
        with self.assertRaises(OSError):
            self.collector.write("private.txt", "synthetic")
        self.assertEqual(list(target.iterdir()), [])
        self.out.unlink()
        self.out.mkdir(mode=0o700)
        (self.out / "etc").symlink_to(target, target_is_directory=True)
        with self.assertRaises(OSError):
            self.collector.write("etc/example.conf", "synthetic")
        self.assertEqual(list(target.iterdir()), [])

    def test_existing_files_hardlinks_symlinks_and_fifo_are_never_truncated(self):
        self.out.mkdir(mode=0o700)
        target = self.root / "outside.txt"
        target.write_text("preserved")
        (self.out / "regular.txt").write_text("original")
        (self.out / "symlink.txt").symlink_to(target)
        os.link(target, self.out / "hardlink.txt")
        os.mkfifo(self.out / "pipe")
        for name in ("regular.txt", "symlink.txt", "hardlink.txt", "pipe"):
            with self.subTest(name=name), self.assertRaises(FileExistsError):
                self.collector.write(name, "must not replace")
        self.assertEqual(target.read_text(), "preserved")
        self.assertEqual((self.out / "regular.txt").read_text(), "original")
        self.assertEqual(self.collector.artifacts, [])

    def test_duplicate_generated_artifact_does_not_duplicate_index_or_replace_bytes(self):
        self.collector.write("system/info.txt", "first")
        with self.assertRaises(FileExistsError):
            self.collector.write("system/info.txt", "second")
        self.assertEqual((self.out / "system/info.txt").read_text(), "first\n")
        self.assertEqual(len(self.collector.artifacts), 1)

    def test_unsafe_relative_paths_fail_before_creating_output(self):
        for path in ("../outside", "/absolute", ".", "", "a//b", "a/../b", "a\\b", "a\nb"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.collector.write(path, "synthetic")
        self.assertFalse(self.out.exists())

    def test_replaced_capture_root_is_not_used_for_subsequent_writes(self):
        self.collector.write("first.txt", "first")
        self.out.rename(self.root / "original-capture")
        self.out.mkdir(mode=0o700)
        with self.assertRaisesRegex(OSError, "changed during collection"):
            self.collector.write("second.txt", "second")
        self.assertEqual(list(self.out.iterdir()), [])

    def test_foreign_directory_owner_is_rejected(self):
        with patch.object(x.os, "fstat", return_value=type("Stat", (), {
                "st_mode": stat.S_IFDIR | 0o700, "st_uid": os.geteuid() + 1})()):
            with self.assertRaises(PermissionError):
                x.Collector._check_private_directory(123)

    def test_manifest_does_not_absorb_unexpected_files_or_read_their_bodies(self):
        self.collector.write("first.txt", "first")
        extra = self.out / "unexpected.txt"
        extra.write_text("must not enter seal")
        extra.chmod(0o600)
        with patch.object(Path, "read_bytes", side_effect=AssertionError("unexpected read")):
            with self.assertRaisesRegex(ValueError, "unexpected or missing"):
                self.collector.write_manifest()
        self.assertFalse((self.out / "ARTIFACTS.sha256").exists())

    def test_manifest_refuses_missing_files_and_nonprivate_output(self):
        path = self.collector.write("first.txt", "first")
        path.chmod(0o644)
        with self.assertRaises(PermissionError):
            self.collector.write_manifest()
        path.unlink()
        with self.assertRaisesRegex(ValueError, "unexpected or missing"):
            self.collector.write_manifest()

    def test_regular_theme_plugin_is_collected_once_by_the_tree(self):
        self.check_theme_copy(False)

    def test_symlink_theme_plugin_keeps_its_explicit_copy_path(self):
        self.check_theme_copy(True)

    def check_theme_copy(self, is_link):
        theme = self.root / ".config/nvim/lua/plugins/theme.lua"
        with patch.object(x, "HOME", self.root), \
                patch.object(Path, "is_symlink", lambda path: path == theme and is_link), \
                patch.object(Path, "glob", return_value=[]), \
                patch.object(Path, "read_text", side_effect=FileNotFoundError()), \
                patch.object(self.collector, "sudo_run", return_value=""), \
                patch.object(self.collector, "copy_file") as copy, \
                patch.object(self.collector, "copy_tree", return_value=0) as tree:
            self.collector.collect_configs()
        matching = [call for call in copy.call_args_list if call.args[0] == theme]
        self.assertEqual(len(matching), 1 if is_link else 0)
        self.assertTrue(any(call.args[0] == self.root / ".config/nvim" for call in tree.call_args_list))

    def test_manifest_itself_is_never_overwritten(self):
        self.collector.write("first.txt", "first")
        self.collector.write_manifest()
        original = (self.out / "ARTIFACTS.sha256").read_bytes()
        with self.assertRaises(ValueError):
            self.collector.write_manifest()
        self.assertEqual((self.out / "ARTIFACTS.sha256").read_bytes(), original)


class PrivateCaptureFlowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "synthetic.conf"
        self.source.write_text("setting=synthetic\n")
        self.args = argparse.Namespace(root=str(self.root), snapshot="fixture", out=None, force=False, no_sudo=True)

    def tearDown(self):
        self.tmp.cleanup()

    def collect(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return x.cmd_collect(self.args)

    @contextlib.contextmanager
    def synthetic_inventory(self):
        def identity(collector):
            collector.data.update(host={key: "synthetic" for key in ("hostname", "chassis", "os", "kernel", "architecture")},
                                  os={}, omarchy={key: "synthetic" for key in ("version", "branch", "channel")})
        def hardware(collector):
            collector.data["hardware"] = {"board": {key: "synthetic" for key in ("model", "version", "bios", "bios_date")},
                "cpu": {"model": "synthetic", "threads": 1}, "memory": {"total_human": "1 GiB"},
                "gpu": {key: "synthetic" for key in ("name", "vram", "driver")}}
            collector.write("system/hardware.txt", "Synthetic test fixture, not a machine capture.")
        def packages(collector):
            collector.data["packages"] = {"all": [], "all_count": 0, "explicit": [], "explicit_count": 0, "foreign": [], "foreign_count": 0}
        def configs(collector):
            collector.copy_file(self.source, "etc/example.conf")
            collector.data["config_index"] = collector.config_index
            collector.data["config_footprint"] = {}
        methods = {"collect_identity": identity, "collect_hardware": hardware, "collect_packages": packages,
                   "collect_configs": configs, "collect_storage": lambda c: c.data.update(storage={}),
                   "collect_desktop": lambda c: c.data.update(desktop={"hyprland": "synthetic", "theme": "synthetic"})}
        with contextlib.ExitStack() as stack:
            for name in ("collect_network", "collect_services", "collect_boot", "collect_dev", "collect_docker", "collect_agents"):
                methods[name] = lambda c: None
            for name, method in methods.items():
                stack.enter_context(patch.object(x.Collector, name, method))
            stack.enter_context(patch.object(x.Collector, "run", side_effect=AssertionError("real command must not run")))
            yield

    def test_real_orchestration_writes_private_valid_capture_and_refuses_rerun(self):
        previous = os.umask(0)
        try:
            with self.synthetic_inventory():
                self.assertEqual(self.collect(), 0)
                self.assertEqual(self.collect(), 2)
        finally:
            os.umask(previous)
        out = self.root / "snapshots/fixture"
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(x.cmd_validate(argparse.Namespace(root=str(self.root), snapshot=str(out))), 0)
        data = json.loads((out / "data/snapshot.json").read_text())
        self.assertEqual(data["commands"], [])
        self.assertEqual(data["privacy"]["config_files_captured"], 1)
        self.assertIn("owner-only", data["privacy"]["local_output"])
        self.assertEqual(len(data["config_index"]), 1)
        for path in [out, *out.rglob("*")]:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700 if path.is_dir() else 0o600)

    def test_interrupted_capture_remains_private_and_cannot_be_silently_reused(self):
        def interrupted(collector):
            collector.write("system/partial.txt", "synthetic partial output")
            raise OSError("synthetic interruption")
        with patch.object(x.Collector, "collect", interrupted):
            self.assertEqual(self.collect(), 1)
            self.assertEqual(self.collect(), 2)
        out = self.root / "snapshots/fixture"
        self.assertEqual(stat.S_IMODE(out.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((out / "system/partial.txt").stat().st_mode), 0o600)
        self.assertFalse((out / "ARTIFACTS.sha256").exists())

    def test_final_directory_creation_race_refuses_collection(self):
        original = Path.mkdir
        out = self.root / "snapshots/fixture"
        def mkdir(path, *args, **kwargs):
            if path == out:
                raise FileExistsError("synthetic competing creator")
            return original(path, *args, **kwargs)
        with patch.object(Path, "mkdir", mkdir), patch.object(x.Collector, "collect") as collect:
            self.assertEqual(self.collect(), 2)
        collect.assert_not_called()


if __name__ == "__main__":
    unittest.main()

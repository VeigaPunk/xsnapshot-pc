"""Portable capture/validation fixtures. Never collect the developer's machine."""
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lib import xsnapshot as x

def digest(body):
    return hashlib.sha256(body).hexdigest()

class PortableValidationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.snap = self.root / "snapshots" / "fixture"
        self.snap.mkdir(parents=True)
        self.bodies = {"REPORT.md": b"Synthetic report", "etc/example.conf": b"safe=value\n"}
        self.data = {
            "schema": "xsnapshot/v1", "snapshot_id": "fixture",
            "captured_at": "2026-11-07T12:00:00+00:00",
            **{key: {} for key in ("host", "os", "hardware", "storage", "desktop")},
            "packages": {"all": [], "all_count": 0, "explicit": [], "explicit_count": 0, "foreign": [], "foreign_count": 0},
            "config_index": [{"path": "etc/example.conf", "source": "/etc/example.conf",
                              "bytes": 11, "snapshot_sha256": digest(self.bodies["etc/example.conf"]), "redactions": 0}],
            "privacy": {"config_files_captured": 1},
            "artifacts": [{"path": path, "bytes": len(body), "sha256": digest(body)}
                          for path, body in self.bodies.items()],
        }
        self.write()
    def tearDown(self):
        self.tmp.cleanup()
    def write(self, raw=None):
        bodies = {**self.bodies, "data/snapshot.json": (raw or json.dumps(self.data)).encode()}
        for rel, body in bodies.items():
            path = self.snap / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        (self.snap / "ARTIFACTS.sha256").write_text(
            "".join(f"{digest(body)}  {rel}\n" for rel, body in bodies.items()))
    def validate(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return x.cmd_validate(argparse.Namespace(root=str(self.root), snapshot=str(self.snap)))
    def test_small_complete_capture_is_valid(self):
        self.assertEqual(self.validate(), 0)
    def test_missing_report_is_invalid_even_with_consistent_index(self):
        del self.bodies["REPORT.md"]
        (self.snap / "REPORT.md").unlink()
        self.data["artifacts"] = [a for a in self.data["artifacts"] if a["path"] != "REPORT.md"]
        self.write()
        self.assertEqual(self.validate(), 1)
    def test_empty_config_capture_can_be_valid(self):
        del self.bodies["etc/example.conf"]
        (self.snap / "etc/example.conf").unlink()
        self.data["artifacts"] = [a for a in self.data["artifacts"] if a["path"] == "REPORT.md"]
        self.data["config_index"] = []
        self.data["privacy"]["config_files_captured"] = 0
        self.write()
        self.assertEqual(self.validate(), 0)
    def test_metadata_errors_fail_without_tracebacks(self):
        mutations = [
            lambda d: d.update(config_index={}),
            lambda d: d.update(artifacts=[None]),
            lambda d: d["artifacts"].append(d["artifacts"][0]),
            lambda d: d["config_index"].append(d["config_index"][0]),
            lambda d: d["config_index"][0].update(bytes=1),
            lambda d: d["config_index"][0].update(redactions=True),
            lambda d: d.update(config_index=[]),
            lambda d: d["packages"].update(foreign_count=1),
            lambda d: d["packages"].update(all=""),
            lambda d: d.update(snapshot_id="../fixture"),
            lambda d: d.update(captured_at="not-a-date"),
            lambda d: d["privacy"].update(config_files_captured=True),
            lambda d: d["artifacts"][0].update(path="../outside"),
        ]
        original = json.dumps(self.data)
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.data = json.loads(original)
                mutation(self.data)
                self.write()
                self.assertEqual(self.validate(), 1)
    def test_nonfinite_json_constants_are_not_valid_json(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            self.data["extra"] = value
            self.write()
            self.assertEqual(self.validate(), 1)
    def test_package_values_must_be_text(self):
        self.data["packages"].update(all=[None], all_count=1)
        self.write()
        self.assertEqual(self.validate(), 1)
    def test_duplicate_decoded_json_key_is_rejected(self):
        self.write('{"schema":"xsnapshot/v1","sch\\u0065ma":"xsnapshot/v1"}')
        self.assertEqual(self.validate(), 1)
    def test_symlink_artifact_is_rejected_before_reading(self):
        target = self.root / "outside"
        target.write_bytes(b"must not be consumed")
        path = self.snap / "etc/example.conf"
        path.unlink()
        path.symlink_to(target)
        self.assertEqual(self.validate(), 1)
    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX")
    def test_special_file_is_rejected_without_opening_it(self):
        os.mkfifo(self.snap / "pipe")
        self.assertEqual(self.validate(), 1)
    def test_tamper_and_unsealed_extra_file_fail(self):
        (self.snap / "REPORT.md").write_text("changed")
        self.assertEqual(self.validate(), 1)
        self.write()
        (self.snap / "extra.txt").write_text("unsealed")
        self.assertEqual(self.validate(), 1)
    def test_generated_locale_is_sealed_but_not_copied_config(self):
        self.bodies["etc/locale.gen.active"] = b"en_US.UTF-8 UTF-8\n"
        self.data["artifacts"].append({"path":"etc/locale.gen.active","bytes":len(self.bodies["etc/locale.gen.active"]),
                                      "sha256":digest(self.bodies["etc/locale.gen.active"])})
        self.write()
        self.assertEqual(self.validate(), 0)

class CaptureBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
    def tearDown(self):
        self.tmp.cleanup()
    def call(self, **values):
        args = argparse.Namespace(root=str(self.root), snapshot="fixture", out=None, force=False, no_sudo=True)
        for key, value in values.items():
            setattr(args, key, value)
        with patch.object(x, "Collector") as collector:
            collector.return_value.artifacts = []
            collector.return_value.redaction_total = 0
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = x.cmd_collect(args)
            return result, collector
    def test_snapshot_traversal_is_refused(self):
        for name in ("../outside", ".", "..", "/absolute", "nested/capture", ""):
            if name == "":  # Empty means use the date, so it is not an unsafe path.
                continue
            result, collector = self.call(snapshot=name)
            self.assertEqual(result, 2)
            collector.assert_not_called()
    def test_snapshot_root_itself_cannot_be_forced(self):
        base = self.root / "snapshots"
        base.mkdir()
        sentinel = base / "keep"
        sentinel.write_text("preserved")
        result, collector = self.call(out=str(base), force=True)
        self.assertEqual(result, 2)
        self.assertTrue(sentinel.exists())
        collector.assert_not_called()
    def test_symlink_output_cannot_be_forced(self):
        target = self.root / "outside"
        target.mkdir()
        link = self.root / "alias"
        link.symlink_to(target, target_is_directory=True)
        result, collector = self.call(out=str(link), force=True)
        self.assertEqual(result, 2)
        collector.assert_not_called()
    def test_rerun_requires_deliberate_force_and_keeps_state_separate(self):
        state = self.root / "state"
        result, collector = self.call(root=str(state))
        self.assertEqual(result, 0)
        collector.assert_called_once_with(root=state, out=state/"snapshots"/"fixture", sudo=False)
        self.assertEqual(self.call(root=str(state))[0], 2)
        self.assertEqual(self.call(root=str(state), force=True)[0], 0)
        self.assertFalse((self.root/"snapshots").exists())

if __name__ == "__main__":
    unittest.main()

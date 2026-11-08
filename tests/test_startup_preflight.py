"""Startup canaries and non-collecting checks; no inventory service is queried."""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lib import xsnapshot as x


class StartupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.marker = self.root / "hook-ran"
        self.hook = self.root / "startup-hook"
        self.hook.write_text("printf ran > " + str(self.marker) + "\n")
        self.env = {**os.environ, "BASH_ENV": str(self.hook), "ENV": str(self.hook),
                    "SHELLOPTS": "errexit", "BASHOPTS": "failglob", "CDPATH": "/not-a-directory",
                    "GLOBIGNORE": "*", "BASH_FUNC_printf%%": "() { echo imported-function; }"}

    def tearDown(self):
        self.tmp.cleanup()

    def test_inventory_shell_ignores_startup_files_functions_and_options(self):
        collector = x.Collector(self.root, self.root / "capture", sudo=False)
        with patch.dict(os.environ, self.env, clear=True):
            result = collector.run("false; printf '%s' expected")
        self.assertEqual(result, "expected")
        self.assertFalse(self.marker.exists())
        self.assertEqual(collector.commands[0]["returncode"], 0)
        self.assertEqual(collector.commands[0]["command"], "false; printf '%s' expected")

    def test_shell_hooks_do_not_reach_a_nested_shell(self):
        collector = x.Collector(self.root, self.root / "capture", sudo=False)
        with patch.dict(os.environ, self.env, clear=True):
            result = collector.run("/bin/bash -c \"printf '%s' nested\"")
        self.assertEqual(result, "nested")
        self.assertFalse(self.marker.exists())

    def test_command_argv_and_environment_keep_configuration_but_not_shell_hooks(self):
        collector = x.Collector(self.root, self.root / "capture", sudo=False)
        with patch.dict(os.environ, {**self.env, "SYNTHETIC_TOOL_OPTION": "preserved"}, clear=True), \
                patch.object(x.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "ok", "")) as run:
            self.assertEqual(collector.run("printf ok", timeout=7), "ok")
        args, options = run.call_args
        self.assertEqual(args[0], ["/bin/bash", "--noprofile", "--norc", "-c", "printf ok"])
        self.assertFalse(options["shell"])
        self.assertEqual(options["timeout"], 7)
        self.assertEqual(options["env"]["SYNTHETIC_TOOL_OPTION"], "preserved")
        self.assertEqual(options["env"]["PATH"], self.env["PATH"])
        for key in ("BASH_ENV", "ENV", "SHELLOPTS", "BASHOPTS", "CDPATH", "GLOBIGNORE", "BASH_FUNC_printf%%"):
            self.assertNotIn(key, options["env"])

    def test_manual_launcher_ignores_path_shims_and_python_startup_canaries(self):
        # Copy only reviewed collector code into a disposable fixture package.
        # Canary modules fail visibly if startup isolation ever regresses.
        package = self.root / "source"
        (package / "bin").mkdir(parents=True)
        (package / "lib").mkdir()
        repository = Path(__file__).resolve().parent.parent
        shutil.copyfile(repository / "bin/xsnapshot", package / "bin/xsnapshot")
        shutil.copyfile(repository / "lib/xsnapshot.py", package / "lib/xsnapshot.py")
        (package / "bin/xsnapshot").chmod(0o700)
        canary = "from pathlib import Path\nPath(" + repr(str(self.marker)) + ").write_text('hook ran')\nraise RuntimeError('startup canary ran')\n"
        for directory in (package / "lib", self.root):
            (directory / "json.py").write_text(canary)
            (directory / "sitecustomize.py").write_text(canary)
        shim = self.root / "python3"
        shim.write_text("#!/bin/sh\nprintf shim > " + str(self.marker) + "\nexit 99\n")
        shim.chmod(0o700)
        env = {**self.env, "PATH": str(self.root), "PYTHONPATH": str(self.root),
               "PYTHONHOME": str(self.root / "not-python"), "PYTHONSTARTUP": str(self.hook)}
        result = subprocess.run([str(package / "bin/xsnapshot"), "preflight", "--json"],
                                cwd=self.root, env=env, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data["checks"]["isolated_python_startup"])
        self.assertFalse(data["capture_verified"])
        self.assertFalse(self.marker.exists())
        self.assertFalse((package / "snapshots").exists())


class PreflightTest(unittest.TestCase):
    def report(self, **changes):
        flags = changes.pop("flags", SimpleNamespace(isolated=1, no_site=1))
        system = changes.pop("system", "Linux")
        found = changes.pop("found", True)
        version = changes.pop("version", (3, 11, 0))
        with patch.object(x.sys, "flags", flags), patch.object(x.sys, "version_info", version), \
                patch.object(x.platform, "system", return_value=system), \
                patch.object(x.shutil, "which", return_value="/system/tool" if found else None), \
                patch.object(x.os.path, "isfile", return_value=True), patch.object(x.os, "access", return_value=True), \
                patch.object(x.Collector, "_local_docker_socket", return_value=None), \
                patch.object(x.subprocess, "run", side_effect=AssertionError("must not execute commands")), \
                patch.object(Path, "read_text", side_effect=AssertionError("must not read config bodies")), \
                patch.object(Path, "read_bytes", side_effect=AssertionError("must not read config bodies")):
            return x.preflight_report()

    def test_core_prerequisites_do_not_claim_a_verified_capture(self):
        report = self.report()
        self.assertTrue(report["core_prerequisites_met"])
        self.assertFalse(report["capture_verified"])
        self.assertTrue(report["docker_socket_checked_without_connecting"])
        self.assertIn("not trust", report["limits"])
        self.assertTrue(all(report["system_path_tools"].values()))

    def test_missing_optional_tools_are_coverage_warnings_not_hardware_claims(self):
        report = self.report(found=False)
        self.assertTrue(report["core_prerequisites_met"])
        self.assertIn("Installed package inventory may be unavailable", " ".join(report["warnings"]))
        self.assertIn("not evidence of missing hardware", " ".join(report["warnings"]))

    def test_unsupported_platform_old_python_and_unisolated_startup_block_readiness(self):
        for change in ({"system": "Darwin"}, {"version": (3, 9, 0)},
                       {"flags": SimpleNamespace(isolated=0, no_site=1)}, {"flags": SimpleNamespace(isolated=1, no_site=0)}):
            with self.subTest(change=change):
                self.assertFalse(self.report(**change)["core_prerequisites_met"])

    def test_report_never_echoes_environment_values_or_paths(self):
        with patch.dict(os.environ, {"HOME": "/synthetic-private-home", "DOCKER_HOST": "ssh://synthetic-private-host", "SYNTHETIC_SECRET": "must-not-print"}):
            serialized = json.dumps(self.report())
        for forbidden in ("synthetic-private", "must-not-print", "/system/tool"):
            self.assertNotIn(forbidden, serialized)

    def test_cli_exit_codes_and_json_are_explicit(self):
        for ready in (False, True):
            report = self.report(); report["core_prerequisites_met"] = ready
            with patch.object(x, "preflight_report", return_value=report), contextlib.redirect_stdout(io.StringIO()) as output:
                code = x.cmd_preflight(argparse.Namespace(json=True))
            self.assertEqual(code, 0 if ready else 2)
            self.assertEqual(json.loads(output.getvalue()), report)


if __name__ == "__main__":
    unittest.main()

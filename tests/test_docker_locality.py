"""Local Docker inventory fixtures. Never query a daemon or capture this machine."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lib import xsnapshot as x


class DockerLocalityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.collector = x.Collector(self.root, self.root / "capture", sudo=False)
        self.socket = Path("/run/user/1234/docker.sock")

    def tearDown(self):
        self.tmp.cleanup()

    def collect(self, result=None):
        if result is None:
            result = subprocess.CompletedProcess([], 0, "{}", "")
        with patch.object(x.Collector, "_local_docker_socket", return_value=(self.socket, "rootless")), \
                patch.object(x.shutil, "which", return_value="/usr/bin/docker") as which, \
                patch.object(x.subprocess, "run", side_effect=result if isinstance(result, list) else None,
                             return_value=None if isinstance(result, list) else result) as run:
            self.collector.collect_docker()
        which.assert_called_once_with("docker", path=os.defpath)
        return run

    def test_only_known_socket_locations_and_rootless_priority(self):
        seen = []
        def lstat(path):
            seen.append(str(path))
            return SimpleNamespace(st_mode=stat.S_IFSOCK | 0o600)
        with patch.object(x.os, "geteuid", return_value=1234), \
                patch.object(Path, "lstat", lstat), \
                patch.dict(os.environ, {"DOCKER_HOST": "ssh://remote.invalid", "XDG_RUNTIME_DIR": "/elsewhere"}):
            self.assertEqual(x.Collector._local_docker_socket(), (self.socket, "rootless"))
        self.assertEqual(seen, [str(self.socket)])

    def test_missing_rootless_can_select_system_socket(self):
        seen = []
        def lstat(path):
            seen.append(str(path))
            if len(seen) == 1:
                raise FileNotFoundError()
            return SimpleNamespace(st_mode=stat.S_IFSOCK | 0o660)
        with patch.object(x.os, "geteuid", return_value=1234), patch.object(Path, "lstat", lstat):
            self.assertEqual(x.Collector._local_docker_socket(), (Path("/var/run/docker.sock"), "system"))
        self.assertEqual(seen, [str(self.socket), "/var/run/docker.sock"])

    def test_final_symlinks_regular_files_directories_and_fifos_are_not_sockets(self):
        for mode in (stat.S_IFLNK, stat.S_IFREG, stat.S_IFDIR, stat.S_IFIFO):
            with self.subTest(mode=mode), patch.object(Path, "lstat", return_value=SimpleNamespace(st_mode=mode)):
                self.assertIsNone(x.Collector._local_docker_socket())
        with patch.object(Path, "lstat", side_effect=PermissionError()):
            self.assertIsNone(x.Collector._local_docker_socket())

    def test_no_socket_never_runs_docker_or_resolves_context(self):
        with patch.object(x.Collector, "_local_docker_socket", return_value=None), \
                patch.object(x.shutil, "which", return_value="/usr/bin/docker"), \
                patch.object(x.subprocess, "run") as run:
            self.collector.collect_docker()
        run.assert_not_called()
        data = self.collector.data["docker"]
        self.assertEqual(data["capture_status"], "unavailable")
        self.assertEqual(data["reason"], "no_supported_local_socket")
        self.assertEqual(set(data["section_status"].values()), {"not_attempted"})
        report = (self.collector.out / "system/docker.txt").read_text()
        self.assertIn("unavailable", report)
        self.assertNotIn("\nnone\n", report)

    def test_missing_system_cli_does_not_try_user_path_or_sudo(self):
        with patch.object(x.Collector, "_local_docker_socket", return_value=(self.socket, "rootless")), \
                patch.object(x.shutil, "which", return_value=None), patch.object(x.subprocess, "run") as run:
            self.collector.collect_docker()
        run.assert_not_called()
        self.assertEqual(self.collector.data["docker"]["reason"], "system_docker_cli_unavailable")

    def test_direct_argv_private_config_and_clean_environment(self):
        seen = []
        ambient = {"DOCKER_HOST": "ssh://remote.invalid", "DOCKER_CONTEXT": "production",
                   "DOCKER_CUSTOM_HEADERS": "Authorization=secret", "DOCKER_TLS_VERIFY": "1",
                   "DOCKER_CERT_PATH": "/secret", "DOCKER_API_VERSION": "bogus", "DOCKER_CONFIG": "/saved",
                   "HTTP_PROXY": "https://secret.invalid", "HTTPS_PROXY": "https://secret.invalid",
                   "ALL_PROXY": "https://secret.invalid", "BASH_ENV": "/startup", "LD_PRELOAD": "/library",
                   "XDG_RUNTIME_DIR": "/elsewhere", "PATH": "/custom", "HOME": "/saved-home"}
        def run(argv, **kwargs):
            config = Path(argv[2])
            self.assertTrue(config.is_dir())
            self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o700)
            self.assertEqual(list(config.iterdir()), [])
            self.assertEqual(argv[:2], ["/usr/bin/docker", "--config"])
            self.assertEqual(argv[3:5], ["--host", f"unix://{self.socket}"])
            self.assertFalse(kwargs["shell"])
            self.assertEqual(kwargs["timeout"], 30)
            self.assertEqual(kwargs["env"], {"PATH": os.defpath, "HOME": str(config), "DOCKER_CONFIG": str(config),
                                             "LC_ALL": "C", "LANG": "C", "TERM": "dumb"})
            seen.append(argv)
            return subprocess.CompletedProcess(argv, 0, '{"ServerVersion":"fixture","Name":"private-host","Labels":["private"]}' if argv[5] == "info" else "", "")
        with patch.dict(os.environ, ambient), patch.object(x.Collector, "_local_docker_socket", return_value=(self.socket, "rootless")), \
                patch.object(x.shutil, "which", return_value="/usr/bin/docker"), patch.object(x.subprocess, "run", side_effect=run):
            self.collector.collect_docker()
        self.assertEqual([argv[5:7] for argv in seen], [["info", "--format"], ["ps", "-a"], ["images", "--format"], ["volume", "ls"], ["network", "ls"]])
        self.assertEqual(len({argv[2] for argv in seen}), 1)
        self.assertFalse(Path(seen[0][2]).exists())
        data = self.collector.data["docker"]
        self.assertEqual(data["capture_status"], "captured")
        self.assertFalse(data["daemon_identity_verified"])
        self.assertEqual(data["containers"], [])
        self.assertNotIn("Name", data["info"])
        self.assertNotIn("Labels", data["info"])
        self.assertNotIn(str(self.socket), json.dumps(self.collector.commands))
        self.assertNotIn(seen[0][2], json.dumps(self.collector.commands))

    def test_failures_are_unknown_not_empty_and_do_not_change_endpoint(self):
        run = self.collect(subprocess.CompletedProcess([], 1, "private partial output", "private diagnostic"))
        self.assertEqual(run.call_count, 5)
        self.assertEqual({call.args[0][4] for call in run.call_args_list}, {f"unix://{self.socket}"})
        data = self.collector.data["docker"]
        self.assertEqual(data["capture_status"], "unavailable")
        self.assertEqual(set(data["section_status"].values()), {"command_failed"})
        self.assertNotIn("private", json.dumps(data))
        self.assertNotIn("private diagnostic", json.dumps(self.collector.commands))

    def test_partial_success_preserves_field_status(self):
        self.collect([subprocess.CompletedProcess([], 0, '{"ServerVersion":"fixture"}', ""),
                      subprocess.CompletedProcess([], 0, "fixture | image | exited\n", ""),
                      subprocess.TimeoutExpired("docker", 30),
                      PermissionError("private path"),
                      subprocess.CompletedProcess([], 1, "", "private error")])
        data = self.collector.data["docker"]
        self.assertEqual(data["capture_status"], "partial")
        self.assertEqual(data["containers"], ["fixture | image | exited"])
        self.assertEqual(data["section_status"], {"info": "captured", "containers": "captured", "images": "timeout", "volumes": "command_unavailable", "networks": "command_failed"})
        self.assertEqual(len(self.collector.commands), 5)
        self.assertNotIn("private path", json.dumps(self.collector.commands))

    def test_invalid_info_is_not_reported_as_success(self):
        for index, value in enumerate(("not JSON", "[]", "null", '"text"')):
            with self.subTest(value=value):
                self.collector = x.Collector(self.root, self.root / f"invalid-{index}", sudo=False)
                self.collect(subprocess.CompletedProcess([], 0, value, ""))
                self.assertEqual(self.collector.data["docker"]["section_status"]["info"], "invalid_response")
                self.assertEqual(self.collector.data["docker"]["capture_status"], "partial")

    def test_private_config_failure_remains_unavailable(self):
        with patch.object(x.Collector, "_local_docker_socket", return_value=(self.socket, "rootless")), \
                patch.object(x.shutil, "which", return_value="/usr/bin/docker"), \
                patch.object(x.tempfile, "TemporaryDirectory", side_effect=OSError("private path")), \
                patch.object(x.subprocess, "run") as run:
            self.collector.collect_docker()
        run.assert_not_called()
        self.assertEqual(self.collector.data["docker"]["reason"], "private_config_unavailable")
        self.assertNotIn("private path", json.dumps(self.collector.data))

    def test_inert_process_cannot_see_saved_config_or_ambient_secrets(self):
        # This is our own fixture program, not Docker. No daemon/socket is opened.
        program = self.root / "fixture-docker"
        program.write_text(f"#!{sys.executable}\n" + '''import json, os, pathlib, sys
config = pathlib.Path(sys.argv[2])
assert sys.argv[1] == '--config' and sys.argv[3:5] == ['--host', 'unix:///run/user/1234/docker.sock']
assert config.is_dir() and list(config.iterdir()) == []
assert os.environ['HOME'] == str(config)
assert not any(k in os.environ for k in ('DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_CUSTOM_HEADERS', 'BASH_ENV', 'XSNAPSHOT_TEST_SECRET'))
assert 'DOCKER_CONFIG' in os.environ
if sys.argv[5] == 'info':
    print(json.dumps({'ServerVersion':'inert-process-fixture'}))
''')
        program.chmod(0o700)
        saved = self.root / "saved-config"
        saved.mkdir()
        original = '{"currentContext":"remote","auths":{"fixture":{"auth":"synthetic-secret"}}}'
        (saved / "config.json").write_text(original)
        with patch.dict(os.environ, {"DOCKER_HOST": "ssh://remote.invalid", "DOCKER_CONTEXT": "remote", "DOCKER_CONFIG": str(saved),
                                     "DOCKER_CUSTOM_HEADERS": "secret", "BASH_ENV": "/fixture-must-not-read", "XSNAPSHOT_TEST_SECRET": "synthetic"}), \
                patch.object(x.Collector, "_local_docker_socket", return_value=(self.socket, "rootless")), \
                patch.object(x.shutil, "which", return_value=str(program)):
            self.collector.collect_docker()
        self.assertEqual(self.collector.data["docker"]["capture_status"], "captured")
        self.assertEqual(self.collector.data["docker"]["info"]["ServerVersion"], "inert-process-fixture")
        self.assertEqual((saved / "config.json").read_text(), original)


if __name__ == "__main__":
    unittest.main()

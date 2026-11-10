"""Private-repository fixtures only: sealed synthetic data and local remotes."""
import ast
import contextlib
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from lib import xsnapshot_repo as repo


SOURCE = Path(__file__).resolve().parent.parent


class PrivateRepositoryFixture:
    def setUp(self):
        scratch = Path("/tmp/xsnapshot-repo")
        scratch.mkdir(mode=0o700, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="test-", dir=scratch)
        self.base = Path(self.tmp.name)
        self.state = self.base / "state"
        self.state.mkdir()
        self.home = self.base / "home"
        self.home.mkdir()
        self.config = self.base / "config"
        self.config.mkdir()
        self.gitconfig = self.base / "gitconfig"
        self.gitconfig.write_text("")
        self.gh_log = self.base / "gh.log"
        self.remote = self.base / "remote.git"
        self.git(str(self.base), "init", "--bare", "--initial-branch=main", str(self.remote))
        self.fake_bin = self.base / "fake-bin"
        self.fake_bin.mkdir()
        self.fake_gh = self.fake_bin / "gh"
        self.fake_gh.write_text("""#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_GH_LOG"
if [ "$1 $2" = "auth status" ]; then
  [ "${FAKE_AUTH_STATUS:-0}" -eq 0 ] || exit 1
  printf 'Logged in as a synthetic test account\\n'
elif [ "$1 $2" = "api user" ]; then
  printf '%s\\n' "${FAKE_GH_OWNER:-synthetic-owner}"
elif [ "$1 $2" = "repo create" ]; then
  [ "$3" = "${FAKE_GH_NAME:-xsnapshot-synthetic-host}" ] && [ "$4" = "--private" ] || exit 2
  printf 'Synthetic repository creation accepted; no remote contacted.\\n'
elif [ "$1 $2" = "repo view" ]; then
  printf '{"isPrivate": %s, "nameWithOwner": "%s"}\\n' "${FAKE_PRIVATE:-true}" "$3"
fi
""")
        self.fake_gh.chmod(0o700)
        self.env_patch = patch.dict(os.environ, {
            "HOME": str(self.home), "XDG_CONFIG_HOME": str(self.config),
            "GIT_CONFIG_GLOBAL": str(self.gitconfig), "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0", "PATH": str(self.fake_bin) + os.pathsep + os.defpath,
            "FAKE_GH_LOG": str(self.gh_log), "GH_CONFIG_DIR": str(self.config / "gh"),
            "FAKE_AUTH_STATUS": "0", "FAKE_PRIVATE": "true",
        }, clear=False)
        self.env_patch.start()
        # This doubles as a prohibition on real HTTPS. Tests opt into an inert response.
        self.probe_patch = patch.object(repo.urllib.request, "urlopen",
                                       side_effect=AssertionError("real HTTPS is forbidden in tests"))
        self.probe_patch.start()
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()

    def tearDown(self):
        self.probe_patch.stop()
        self.env_patch.stop()
        self.tmp.cleanup()

    def git(self, directory, *args):
        result = subprocess.run(["git", "-C", directory, *args], env=os.environ.copy(),
                                text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, (args, result.stderr))
        return result.stdout.strip()

    def invoke(self, *args, root=True):
        argv = (["--root", str(self.state)] if root else []) + list(args)
        with contextlib.redirect_stdout(self.stdout), contextlib.redirect_stderr(self.stderr):
            code = repo.main(argv)
        return code, self.stdout.getvalue(), self.stderr.getvalue()

    def snapshot(self, identifier, captured="2026-01-02T12:00:00+00:00", host="synthetic-host"):
        snap = self.state / "snapshots" / identifier
        snap.mkdir(parents=True)
        bodies = {"REPORT.md": b"Synthetic report, no machine capture.\n",
                  "applied/example.conf": b"setting=on\n", "etc/example.conf": b"safe=value\n"}
        artifacts = [{"path": name, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
                     for name, body in bodies.items()]
        data = {"schema": "xsnapshot/v1", "snapshot_id": identifier, "captured_at": captured,
                **{name: {} for name in ("os", "hardware", "storage", "desktop")},
                "host": {"hostname": host},
                "packages": {"all": [], "explicit": [], "foreign": [], "all_count": 0,
                             "explicit_count": 0, "foreign_count": 0},
                "config_index": [{"path": name, "source": "synthetic", "bytes": len(body),
                                  "snapshot_sha256": hashlib.sha256(body).hexdigest(), "redactions": 0}
                                 for name, body in bodies.items() if name != "REPORT.md"],
                "privacy": {"config_files_captured": 2}, "artifacts": artifacts}
        for name, body in bodies.items():
            path = snap / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
            path.chmod(0o600)
        raw = json.dumps(data).encode()
        path = snap / "data/snapshot.json"
        path.parent.mkdir()
        path.write_bytes(raw)
        path.chmod(0o600)
        lines = "".join(hashlib.sha256(body).hexdigest() + "  " + name + "\n"
                        for name, body in [*bodies.items(), ("data/snapshot.json", raw)])
        (snap / "ARTIFACTS.sha256").write_text(lines)
        (snap / "ARTIFACTS.sha256").chmod(0o600)
        snap.chmod(0o700)
        return snap

    def valid_snapshot(self, identifier="first", **kwargs):
        return self.snapshot(identifier, **kwargs)

    def init_local(self):
        code, out, err = self.invoke("init", "--no-remote")
        self.assertEqual(code, 0, err)

    def configure_origin(self, url=None):
        self.git(str(self.state), "remote", "add", "origin", url or str(self.remote))

    @staticmethod
    def refresh_snapshot(snapshot):
        """Refresh synthetic edits with the same artifact/config integrity rules."""
        data_path = snapshot / "data/snapshot.json"
        data = json.loads(data_path.read_text())
        artifacts = []
        for path in sorted(snapshot.rglob("*")):
            if not path.is_file() or path in (data_path, snapshot / "ARTIFACTS.sha256"):
                continue
            body = path.read_bytes()
            artifacts.append({"path": path.relative_to(snapshot).as_posix(), "bytes": len(body),
                              "sha256": hashlib.sha256(body).hexdigest()})
        data["artifacts"] = artifacts
        indexed = {entry["path"]: entry for entry in artifacts}
        for entry in data["config_index"]:
            entry["bytes"] = indexed[entry["path"]]["bytes"]
            entry["snapshot_sha256"] = indexed[entry["path"]]["sha256"]
        data_path.write_bytes(json.dumps(data).encode())
        sealed = [path for path in sorted(snapshot.rglob("*"))
                  if path.is_file() and path.name != "ARTIFACTS.sha256"]
        (snapshot / "ARTIFACTS.sha256").write_text("".join(
            hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.relative_to(snapshot).as_posix() + "\n"
            for path in sealed))


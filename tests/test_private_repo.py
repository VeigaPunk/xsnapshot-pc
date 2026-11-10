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


from tests.private_repo_fixture import PrivateRepositoryFixture

class PrivateRepositoryTest(PrivateRepositoryFixture, unittest.TestCase):
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

    def test_complete_snapshots_commit_oldest_first_and_failures_do_not_block(self):
        self.valid_snapshot("later", captured="2026-01-03T09:00:00-03:00", host="host-two")
        self.valid_snapshot("older", captured="2026-01-01T09:00:00+00:00", host="host-one")
        invalid = self.valid_snapshot("incomplete")
        (invalid / "ARTIFACTS.sha256").unlink()
        self.init_local()
        log = self.git(str(self.state), "log", "--format=%s", "--reverse")
        self.assertEqual(log.splitlines(), ["snapshot older (host-one)", "snapshot later (host-two)"])
        self.assertIn("incomplete", self.stdout.getvalue())
        self.assertEqual(self.git(str(self.state), "log", "-1", "--format=%aI"),
                         "2026-01-03T09:00:00-03:00")
        tracked = self.git(str(self.state), "ls-files")
        self.assertIn("snapshots/older/applied/example.conf", tracked)
        self.assertIn("snapshots/older/etc/example.conf", tracked)
        self.assertIn("snapshots/older/data/snapshot.json", tracked)
        self.assertNotIn("snapshots/incomplete", tracked)

    def test_staging_preserves_unrelated_and_existing_readme_and_permissions(self):
        self.valid_snapshot("first")
        readme = self.state / "README.md"
        readme.write_text("The owner's existing notes stay untouched.\n")
        other = self.state / "notes.txt"
        other.write_text("not for upload\n")
        captured = self.state / "snapshots/first/etc/example.conf"
        captured.chmod(0o600)
        self.state.chmod(0o755)
        self.init_local()
        self.assertEqual(readme.read_text(), "The owner's existing notes stay untouched.\n")
        self.assertNotIn("README.md", self.git(str(self.state), "ls-files"))
        self.assertEqual((self.state / ".git").stat().st_mode & 0o777, 0o700)
        self.assertEqual(captured.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.git(str(self.state), "ls-files", "--", "notes.txt"), "")
        self.assertIn("notes.txt", self.git(str(self.state), "status", "--short"))

    def test_tool_created_readme_explains_data_is_not_instructions_and_deletion(self):
        self.valid_snapshot()
        self.init_local()
        text = (self.state / "README.md").read_text()
        for phrase in ("recorded", "not instructions", "newest", "applied", "etc", "delete", "update"):
            self.assertIn(phrase.lower(), text.lower())
        self.assertIn("not a", text.lower())
        self.assertIn("complete backup", text.lower())

    def test_untracked_files_never_staged_and_no_history_rewrite_or_force_push(self):
        self.valid_snapshot("first")
        self.init_local()
        unrelated = self.state / "private-notes.txt"
        unrelated.write_text("not an artifact\n")
        original = self.git(str(self.state), "rev-parse", "HEAD")
        calls = []
        real_run = subprocess.run

        def checked(argv, *args, **kwargs):
            calls.append(list(argv))
            self.assertIs(kwargs.get("shell", False), False)
            self.assertIsInstance(argv, list)
            return real_run(argv, *args, **kwargs)

        with patch.object(repo.subprocess, "run", side_effect=checked):
            self.init_local()
            for invocation in calls:
                self.assertNotIn("--force", invocation)
                self.assertNotIn("reset", invocation)
                if "add" in invocation:
                    self.assertNotIn("-A", invocation)
                    self.assertNotIn(".", invocation)
        self.assertEqual(self.git(str(self.state), "rev-parse", "HEAD"), original)
        self.init_local()
        self.assertEqual(self.git(str(self.state), "rev-parse", "HEAD"), original)

    def test_repository_hooks_are_not_executed(self):
        self.init_local()
        marker = self.base / "hook-ran"
        hooks = self.state / ".git/hooks"
        hooks.mkdir(exist_ok=True)
        (hooks / "pre-commit").write_text("#!/bin/sh\ntouch " + str(marker) + "\n")
        (hooks / "pre-commit").chmod(0o700)
        self.valid_snapshot()
        self.init_local()
        self.assertFalse(marker.exists())
        configured = self.git(str(self.state), "config", "--local", "core.hooksPath")
        destination = Path(configured)
        if not destination.is_absolute():
            destination = self.state / destination
        self.assertTrue(destination.is_dir())
        self.assertEqual(list(destination.iterdir()), [])

    def test_symlink_nested_and_unrelated_worktrees_are_refused(self):
        outside = self.base / "outside"
        outside.mkdir()
        link = self.base / "link"
        link.symlink_to(outside, target_is_directory=True)
        code, _, err = self.invoke("init", "--no-remote", root=False)
        # Zero-root with no default state is separately pinned below; target the link explicitly.
        code, _, err = self.invoke("--root", str(link), "init", "--no-remote", root=False)
        self.assertEqual(code, 2)
        self.assertIn("symlink", (self.stdout.getvalue() + self.stderr.getvalue()).lower())
        outer = self.base / "outer"
        outer.mkdir()
        self.git(str(self.base), "init", str(outer))
        nested = outer / "state"
        code, out, err = self.invoke("--root", str(nested), "init", "--no-remote", root=False)
        self.assertEqual(code, 2)
        self.assertIn("inside", (out + err).lower())
        unrelated = self.base / "existing"
        unrelated.mkdir()
        self.git(str(self.base), "init", str(unrelated))
        (unrelated / "other").write_text("existing unrelated work\n")
        self.git(str(unrelated), "add", "other")
        self.git(str(unrelated), "-c", "user.name=Other", "-c", "user.email=other@invalid",
                 "commit", "-m", "Unrelated history")
        code, out, err = self.invoke("--root", str(unrelated), "init", "--no-remote", root=False)
        self.assertEqual(code, 2)
        self.assertIn("history", (out + err).lower())

    def test_default_root_requires_existing_xsnapshot_data_not_source_checkout(self):
        code, out, err = [], "", ""
        old_cwd = Path.cwd()
        try:
            os.chdir(self.base)
            code, out, err = self.invoke("init", "--no-remote", root=False)
        finally:
            os.chdir(old_cwd)
        self.assertEqual(code, 2)
        self.assertIn("--root", out + err)
        self.assertFalse((SOURCE / ".git/xsnapshot-managed").exists())
        (self.base / "xsnapshot-data").mkdir()
        try:
            os.chdir(self.base)
            code, out, err = self.invoke("init", "--no-remote", root=False)
        finally:
            os.chdir(old_cwd)
        self.assertEqual(code, 0, out + err)
        self.assertTrue((self.base / "xsnapshot-data/.git").is_dir())

    def test_existing_identity_is_used_without_changing_global_config(self):
        self.gitconfig.write_text("[user]\n\tname = Synthetic Person\n\temail = person@example.invalid\n")
        self.valid_snapshot()
        self.init_local()
        result = self.git(str(self.state), "log", "-1", "--format=%an%n%ae")
        self.assertEqual(result.splitlines(), ["Synthetic Person", "person@example.invalid"])
        self.assertEqual(self.gitconfig.read_text(), "[user]\n\tname = Synthetic Person\n\temail = person@example.invalid\n")

    def test_missing_identity_gets_only_repository_local_neutral_identity(self):
        self.valid_snapshot()
        self.init_local()
        self.assertEqual(self.git(str(self.state), "config", "--local", "user.name"), "xsnapshot")
        self.assertEqual(self.git(str(self.state), "config", "--local", "user.email"), "xsnapshot@localhost")
        self.assertEqual(self.gitconfig.read_text(), "")
        self.assertIn("neutral", (self.stdout.getvalue() + self.stderr.getvalue()).lower())

    def test_documented_public_remote_is_refused_even_with_assume_private(self):
        self.valid_snapshot()
        self.init_local()
        url = "https://github.com/synthetic-owner/synthetic-name.git"
        self.configure_origin(url)
        with patch.dict(os.environ, {"FAKE_PRIVATE": "false"}), \
             patch.object(repo.subprocess, "run", wraps=subprocess.run) as processes:
            code, out, err = self.invoke("update", "--no-capture", "--assume-private")
        self.assertEqual(code, 2)
        text = out + err
        self.assertIn("synthetic-owner/synthetic-name", text)
        self.assertIn("public", text.lower())
        self.assertIn("private", text.lower())
        self.assertFalse(any("push" in call.args[0] for call in processes.call_args_list))

    def test_unauthenticated_probe_recognizes_public_but_404_is_not_private(self):
        self.valid_snapshot()
        self.init_local()
        self.configure_origin("https://github.com/synthetic-owner/synthetic-name.git")
        with patch.dict(os.environ, {"FAKE_AUTH_STATUS": "1"}), \
                patch.object(repo.urllib.request, "urlopen") as open_request, \
                patch.object(repo.subprocess, "run", wraps=subprocess.run) as processes:
            open_request.return_value.__enter__.return_value.status = 200
            code, out, err = self.invoke("update", "--no-capture", "--assume-private")
            self.assertEqual(code, 2)
            self.assertIn("public", (out + err).lower())
            request = open_request.call_args.args[0]
            self.assertEqual(request.get_header("Authorization"), None)
            self.assertEqual(request.full_url, "https://github.com/synthetic-owner/synthetic-name")
            not_found = urllib.error.HTTPError(request.full_url, 404, "not found", {}, None)
            open_request.side_effect = not_found
            self.addCleanup(not_found.close)
            code, out, err = self.invoke("update", "--no-capture")
            self.assertEqual(code, 2)
            self.assertIn("--assume-private", out + err)
            self.assertIn("private", (out + err).lower())
            self.assertFalse(any("push" in call.args[0] for call in processes.call_args_list))

    def test_unknown_local_remote_needs_explicit_assumption_then_fast_forward_push(self):
        self.valid_snapshot()
        code, out, err = self.invoke("init", "--remote", str(self.remote))
        self.assertEqual(code, 2)
        self.assertIn("--assume-private", out + err)
        code, _, err = self.invoke("update", "--no-capture")
        self.assertEqual(code, 2, err)
        code, out, err = self.invoke("update", "--no-capture", "--assume-private")
        self.assertEqual(code, 0, out + err)
        self.assertIn("private", (out + err).lower())
        promised = self.git(str(self.state), "rev-parse", "main")
        self.assertEqual(self.git(str(self.remote), "rev-parse", "main"), promised)
        self.valid_snapshot("second", captured="2026-01-04T12:00:00+00:00")
        code, out, err = self.invoke("update", "--no-capture", "--no-push", "--assume-private")
        self.assertEqual(code, 0, out + err)
        self.assertIn("local", (out + err).lower())
        self.assertEqual(self.git(str(self.remote), "rev-parse", "main"), promised)
        self.assertNotEqual(self.git(str(self.state), "rev-parse", "main"), promised)

    def test_signed_out_default_leaves_ready_local_repository_and_manual_command(self):
        self.valid_snapshot()
        with patch.dict(os.environ, {"FAKE_AUTH_STATUS": "1"}):
            code, out, err = self.invoke("init")
        self.assertEqual(code, 0, out + err)
        self.assertIn("--remote", out + err)
        self.assertIn("--root", out + err)
        self.assertIn("--assume-private", out + err)
        self.assertEqual(self.git(str(self.state), "remote"), "")

    def test_prompt_requires_exact_y_before_gh_repository_creation(self):
        self.valid_snapshot()
        with patch("builtins.input", return_value="n") as question:
            code, out, err = self.invoke("init")
        self.assertEqual(code, 2)
        self.assertIn("private", out.lower())
        self.assertIn("applied", out.lower())
        self.assertIn("etc", out.lower())
        self.assertIn("owner", out.lower())
        question.assert_called_once()
        self.assertNotIn("repo create", self.gh_log.read_text())
        self.assertEqual(self.git(str(self.state), "remote"), "")


    def test_signed_created_private_repository_push_arguments_are_plain(self):
        self.valid_snapshot(host="Private Host / Example")
        os.environ["FAKE_GH_NAME"] = "xsnapshot-private-host-example"
        original = repo.git
        processes = []

        def final_local(root, *arguments, **options):
            if "push" not in arguments:
                return original(root, *arguments, **options)
            expected_url = "https://github.com/synthetic-owner/xsnapshot-private-host-example.git"
            self.assertEqual(arguments, ("push", "--no-force", "--no-verify", "--signed=no", expected_url, "HEAD:main"))
            command = ["git", "-C", str(self.state), "push", "--no-force", "--no-verify", "--signed=no", str(self.remote), "HEAD:main"]
            processes.append(command)
            result = subprocess.run(command, text=True, capture_output=True, env=os.environ.copy())
            self.assertEqual(result.returncode, 0, result.stderr)
            return result

        with patch.object(repo, "git", side_effect=final_local):
            code, out, err = self.invoke("init", "--yes")
        self.assertEqual(code, 0, out + err)
        self.assertIn("repo create xsnapshot-private-host-example --private", self.gh_log.read_text())
        self.assertIn("synthetic-owner/xsnapshot-private-host-example", out + err)
        self.assertEqual(len(processes), 1)
        self.assertEqual(self.git(str(self.remote), "rev-parse", "HEAD"), self.git(str(self.state), "rev-parse", "HEAD"))

    def test_empty_repository_with_no_history_can_be_adopted_but_untracked_stays(self):
        self.valid_snapshot()
        self.git(str(self.base), "init", "--initial-branch=main", str(self.state))
        (self.state / "local-note").write_text("unrelated content\n")
        code, out, err = self.invoke("init", "--no-remote")
        self.assertEqual(code, 0, out + err)
        self.assertIn("local-note", self.git(str(self.state), "status", "--short"))

    def test_invalid_snapshot_cannot_supersede_committed_valid_snapshot(self):
        self.valid_snapshot("first")
        self.init_local()
        original = self.git(str(self.state), "rev-parse", "HEAD")
        report = self.state / "snapshots/first/REPORT.md"
        report.write_text("tampered after commit\n")
        code, out, err = self.invoke("update", "--no-capture", "--no-push")
        self.assertEqual(code, 0, out + err)
        self.assertIn("artifact seal hash mismatch", out + err)
        self.assertEqual(self.git(str(self.state), "rev-parse", "HEAD"), original)

    def test_unknown_remote_init_refuses_after_preserving_local_commit(self):
        self.valid_snapshot()
        code, out, err = self.invoke("init", "--remote", str(self.remote))
        self.assertEqual(code, 2)
        self.assertEqual(self.git(str(self.state), "log", "-1", "--format=%s"),
                         "snapshot first (synthetic-host)")
        self.assertEqual(self.git(str(self.state), "rev-parse", "main"),
                         self.git(str(self.state), "rev-parse", "HEAD"))
        empty = subprocess.run(["git", "-C", str(self.remote), "show-ref", "--verify", "refs/heads/main"],
                               env=os.environ, capture_output=True, check=False)
        self.assertNotEqual(empty.returncode, 0)
        self.assertEqual(empty.stdout, b"")

    def test_no_push_never_runs_privacy_probe(self):
        self.valid_snapshot()
        self.init_local()
        self.configure_origin("https://github.com/synthetic-owner/synthetic-name.git")
        with patch.object(repo, "_privacy", side_effect=AssertionError("must not probe")):
            code, out, err = self.invoke("update", "--no-capture", "--no-push")
        self.assertEqual(code, 0, out + err)

    def test_invalid_gh_privacy_result_never_establishes_private(self):
        for body in ('{"nameWithOwner": "synthetic-owner/synthetic-name"}',
                     '{"isPrivate": "false", "nameWithOwner": "synthetic-owner/synthetic-name"}',
                     '{"isPrivate": true, "nameWithOwner": "other/wrong"}', "not json"):
            with self.subTest(body=body):
                with patch.object(repo, "_run", return_value=subprocess.CompletedProcess([], 0, body, "")), \
                        patch.object(repo, "_signed_in", return_value=(True, self.fake_gh)), \
                        patch.object(repo, "_probe_public", return_value="unknown"):
                    self.assertEqual(repo._privacy("https://github.com/synthetic-owner/synthetic-name")[0], "unknown")

    def test_created_public_repository_is_loudly_refused_before_push(self):
        self.valid_snapshot()
        os.environ.update(FAKE_GH_NAME="xsnapshot-synthetic-host", FAKE_PRIVATE="false")
        with patch.object(repo.subprocess, "run", wraps=subprocess.run) as processes:
            code, out, err = self.invoke("init", "--yes")
        self.assertEqual(code, 2)
        self.assertIn("PUBLIC", out + err)
        self.assertIn("private", (out + err).lower())
        self.assertFalse(any("push" in call.args[0] for call in processes.call_args_list))

    def test_status_never_prints_remote_credentials(self):
        self.valid_snapshot()
        self.init_local()
        self.configure_origin("https://synthetic-user:synthetic-password@github.com/synthetic-owner/synthetic-name.git")
        code, out, err = self.invoke("status")
        self.assertEqual(code, 2)
        self.assertNotIn("synthetic-user", out + err)
        self.assertNotIn("synthetic-password", out + err)


    def test_missing_gh_default_is_successful_local_init_and_never_credential_file(self):
        self.valid_snapshot()
        os.environ["PATH"] = os.defpath
        code, out, err = self.invoke("init")
        self.assertEqual(code, 0, out + err)
        self.assertIn("missing or signed out", out)
        self.assertFalse((self.config / "gh").exists())

    def test_no_history_stops_before_probe_or_remote_push(self):
        self.init_local()
        self.configure_origin()
        with patch.object(repo, "_privacy", side_effect=AssertionError("must not probe")) as guard:
            code, out, err = self.invoke("update", "--no-capture", "--assume-private")
        self.assertEqual(code, 2)
        self.assertIn("No snapshot is committed", out + err)

    def test_unlinked_foreign_git_repository_status_is_refused_without_history_mutation(self):
        self.git(str(self.base), "init", "--initial-branch=main", str(self.state))
        (self.state / "unrelated").write_text("notes\n")
        self.git(str(self.state), "add", "unrelated")
        self.git(str(self.state), "-c", "user.name=Other", "-c", "user.email=other@invalid",
                 "commit", "-m", "Foreign initial commit")
        head = self.git(str(self.state), "rev-parse", "HEAD")
        code, out, err = self.invoke("status")
        self.assertEqual(code, 2)
        self.assertEqual(self.git(str(self.state), "rev-parse", "HEAD"), head)

    def test_generated_readme_is_committed_and_repeated_init_preserves_it(self):
        self.valid_snapshot()
        self.init_local()
        self.assertIn("README.md", self.git(str(self.state), "ls-files"))
        first = self.git(str(self.state), "rev-parse", "HEAD")
        (self.state / "README.md").write_text("Owner edit after initial commit\n")
        code, out, err = self.invoke("init", "--no-remote")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.git(str(self.state), "rev-parse", "HEAD"), first)
        self.assertEqual((self.state / "README.md").read_text(), "Owner edit after initial commit\n")

    def test_launcher_isolated_python_and_fixed_github_argument_lists(self):
        launcher = SOURCE / "bin/xsnapshot-repo"
        marker = self.base / "startup-ran"
        self.home.joinpath(".bashrc").write_text("touch " + str(marker) + "\n")
        self.home.joinpath("json.py").write_text("raise RuntimeError('import substitution')\n")
        result = subprocess.run([str(launcher), "--help"], env={**os.environ, "HOME": str(self.home),
                "PYTHONPATH": str(self.home), "BASH_ENV": str(self.home / ".bashrc"), "SHELLOPTS": "xtrace"},
                text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())
        self.assertIn("{init,update,status}", result.stdout)

    def test_inherited_git_dirs_cannot_write_outside_state(self):
        self.valid_snapshot()
        redirected = self.base / "redirected.git"
        redirected.mkdir()
        with patch.dict(os.environ, {"GIT_DIR": str(redirected), "GIT_WORK_TREE": str(self.base),
                                      "GIT_INDEX_FILE": str(redirected / "index"),
                                      "GIT_OBJECT_DIRECTORY": str(redirected / "objects")}):
            code, out, err = self.invoke("init", "--no-remote")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(list(redirected.iterdir()), [])
        self.assertTrue((self.state / ".git").is_dir())

    def test_gh_missing_falls_back_to_github_public_probe(self):
        self.valid_snapshot()
        self.init_local()
        self.configure_origin("https://github.com/synthetic-owner/synthetic-name.git")
        os.environ["PATH"] = os.defpath
        with patch.object(repo.urllib.request, "urlopen") as open_request, \
                patch.object(repo.subprocess, "run", wraps=subprocess.run) as processes:
            open_request.return_value.__enter__.return_value.status = 200
            code, out, err = self.invoke("update", "--no-capture", "--assume-private")
        self.assertEqual(code, 2)
        self.assertIn("public", (out + err).lower())
        self.assertTrue(open_request.called)
        self.assertFalse(any("push" in call.args[0] for call in processes.call_args_list))

    def test_update_captures_only_when_today_is_absent_and_forwards_no_sudo(self):
        self.valid_snapshot("old", captured="2026-01-01T12:00:00+00:00")
        self.init_local()
        today = dt.datetime.now().astimezone().strftime("%Y-%m-%d")
        collection = []
        real_run = subprocess.run

        def collect(argv, *args, **kwargs):
            if "collect" in argv:
                collection.append(list(argv))
                self.snapshot(today, captured=dt.datetime.now().astimezone().isoformat())
                return subprocess.CompletedProcess(argv, 0, "synthetic collection done", "")
            return real_run(argv, *args, **kwargs)

        with patch.object(repo.subprocess, "run", side_effect=collect):
            code, out, err = self.invoke("update", "--no-push", "--no-sudo")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(len(collection), 1)
        command = collection[0]
        self.assertEqual(command[1:3], ["-I", "-S"])
        self.assertEqual(command[command.index("collect"):], ["collect", "--snapshot", today, "--no-sudo"])
        with patch.object(repo.subprocess, "run", side_effect=collect):
            code, out, err = self.invoke("update", "--no-push")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(len(collection), 1)

    def test_status_reports_committed_pending_unpushed_and_other_content(self):
        self.valid_snapshot("first")
        self.init_local()
        self.configure_origin()
        self.valid_snapshot("second", captured="2026-01-04T12:00:00+00:00")
        broken = self.valid_snapshot("broken")
        (broken / "data/snapshot.json").unlink()
        (self.state / "local-only.txt").write_text("untracked\n")
        code, out, err = self.invoke("status")
        self.assertEqual(code, 0, err)
        for term in ("first", "second", "broken", str(self.remote), "1", "local-only.txt"):
            self.assertIn(term, out)
        self.assertEqual(self.git(str(self.state), "log", "-1", "--format=%s"), "snapshot first (synthetic-host)")

    def test_status_reports_local_commits_not_yet_pushed_without_pushing(self):
        self.valid_snapshot("first")
        self.init_local()
        self.configure_origin()
        self.valid_snapshot("second", captured="2026-01-04T12:00:00+00:00")
        self.invoke("update", "--no-capture", "--no-push", "--assume-private")
        self.stdout.seek(0); self.stdout.truncate(); self.stderr.seek(0); self.stderr.truncate()
        with patch.object(repo.subprocess, "run", wraps=subprocess.run) as processes:
            code, out, err = self.invoke("status")
        self.assertEqual(code, 0, out + err)
        self.assertIn("pushed", (out + err).lower())
        self.assertIn("2", out)
        self.assertFalse(any("push" in call.args[0] for call in processes.call_args_list))

    def test_status_absence_is_not_a_failure_and_never_creates_a_repository(self):
        code, out, err = self.invoke("status")
        self.assertEqual(code, 0, out + err)
        self.assertIn("no", out.lower())
        self.assertFalse((self.state / ".git").exists())

    def test_collector_has_no_reference_to_repository_module(self):
        collector = (SOURCE / "lib/xsnapshot.py").read_text()
        self.assertNotIn("xsnapshot_repo", collector)
        self.assertNotIn("xsnapshot-repo", collector)
        tree = ast.parse(collector)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertTrue(all(alias.name != "lib.xsnapshot_repo" for alias in node.names))
            if isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, "lib.xsnapshot_repo")
        self.assertNotIn("xsnapshot_repo", (SOURCE / "bin/xsnapshot").read_text())


if __name__ == "__main__":
    unittest.main()

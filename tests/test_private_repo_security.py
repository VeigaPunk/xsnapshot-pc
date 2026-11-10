"""Regression tests for independent review findings: no network or real capture."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch

from lib import xsnapshot_repo as repo
from tests.private_repo_fixture import PrivateRepositoryFixture


class SecurityRegressionTest(PrivateRepositoryFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()

    def raw_git(self, path, *arguments):
        result = subprocess.run(["/usr/bin/git", "-C", str(path), *arguments], env=os.environ,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def remote_head(self, path):
        found = subprocess.run(["/usr/bin/git", "-C", str(path), "rev-parse", "--verify", "main"],
                               env=os.environ, text=True, capture_output=True)
        return found.stdout.strip() if found.returncode == 0 else None

    def choose_state(self, name):
        self.state = self.base / name
        self.state.mkdir()
        return self.state


    def command_is_push(self, call):
        command = call.args[0]
        return Path(command[0]).name == "git" and "push" in command

    def test_pushurl_and_push_insteadof_cannot_authorize_alternate_bare(self):
        canonical = "https://github.com/synthetic-owner/synthetic-name.git"
        for name, key in [("url-redirect", "url." + str(self.remote) + ".pushInsteadOf"),
                          ("explicit-pushurl", "remote.origin.pushurl")]:
            with self.subTest(key=key):
                self.choose_state(name)
                self.valid_snapshot(); self.init_local(); self.configure_origin(canonical)
                value = canonical if key.startswith("url.") else str(self.remote)
                self.git(str(self.state), "config", "--local", "--add", key, value)
                with patch.object(repo, "_privacy", side_effect=AssertionError("must not inspect wrong host")):
                    code, out, err = self.invoke("update", "--no-capture")
                self.assertEqual(code, 2, out + err)
                self.assertIsNone(self.remote_head(self.remote))

    def test_noncanonical_github_urls_are_unrecognized_and_require_explicit_assumption(self):
        urls = ["https://github.com:8443/owner/name.git", "https://github.com/owner/name.git.git",
                "https://github.com/owner/name.git/", "https://github.com/owner/name/other.git",
                "https://github.com/owner/name/"]
        for index, url in enumerate(urls):
            with self.subTest(url=url), patch.object(repo, "_privacy", side_effect=AssertionError("must not probe")):
                self.choose_state("malformed-" + str(index))
                self.valid_snapshot(); self.init_local(); self.configure_origin(url)
                code, out, err = self.invoke("update", "--no-capture")
                self.assertEqual(code, 2)
                self.assertIn("recognized", out + err)
                self.assertIn("--assume-private", out + err)
                self.assertIsNone(repo._github_name(url))
        for url in urls:
            self.assertIsNone(repo._github_name(url))
            self.assertIsNone(repo._canonical_url(url))

    def test_multiple_push_urls_fail_before_probe_or_transport(self):
        other = self.base / "second-bare.git"
        self.git(str(self.base), "init", "--bare", str(other))
        self.valid_snapshot(); self.init_local(); self.configure_origin()
        self.git(str(self.state), "config", "--local", "--replace-all", "remote.origin.pushurl", str(self.remote))
        self.git(str(self.state), "config", "--local", "--add", "remote.origin.pushurl", str(other))
        with patch.object(repo, "_privacy", side_effect=AssertionError("no probe expected")):
            code, out, err = self.invoke("update", "--no-capture", "--assume-private")
        self.assertEqual(code, 2)
        self.assertIn("Exactly one", out + err)
        self.assertIsNone(self.remote_head(other))

    def test_sensitive_destinations_are_refused_without_printing_or_storing_secrets(self):
        pairs = [("https://user:TOKEN@github.com/o/r.git", "TOKEN"),
                 ("https://github.com/o/r.git?access_token=TOKEN", "TOKEN"),
                 ("https://github.com/o/r.git#TOKEN", "TOKEN"),
                 ("git:TOKEN@github.com:o/r.git", "TOKEN")]
        for index, (url, token) in enumerate(pairs):
            with self.subTest(index=index):
                self.choose_state("credentials%d" % index)
                with patch.object(repo, "_privacy", side_effect=AssertionError("no network")):
                    code, out, err = self.invoke("init", "--remote", url)
                self.assertEqual(code, 2)
                self.assertNotIn(token, out + err)
                config = self.state / ".git/config"
                self.assertNotIn(token, config.read_text())

    def test_display_url_removes_every_sensitive_component(self):
        url = "https://user:PASSWORD@github.com/o/r.git?token=TOKEN#PRIVATE"
        self.assertEqual(repo._display_url(url), "https://github.com/o/r.git")
        self.assertEqual(repo._display_url("git:TOKEN@github.com:o/r.git"), "github.com:o/r.git")
        self.valid_snapshot(); self.init_local()
        self.configure_origin("https://user:PASSWORD@github.com/o/r.git")
        code, out, err = self.invoke("status")
        self.assertEqual(code, 2)
        self.assertNotIn("PASSWORD", out + err)

    def test_snapshot_clean_filter_ident_eol_and_worktree_encoding_cannot_change_bytes(self):
        snap = self.valid_snapshot()
        body = b"sealed $Id: synthetic-id$ / CRLF\r\nlast-line\x00"
        target = snap / "applied/example.conf"
        target.write_bytes(body)
        attributes = b"* filter=danger text eol=crlf ident working-tree-encoding=UTF-16\n"
        (snap / ".gitattributes").write_bytes(attributes)
        self.refresh_snapshot(snap)
        marker = self.base / "filter-program-run"
        program = self.base / "filter-program"
        program.write_text("#!/bin/sh\ntouch " + str(marker) + "\nprintf replaced\n")
        program.chmod(0o700)
        self.git(str(self.base), "init", "--initial-branch=main", str(self.state))
        self.git(str(self.state), "config", "filter.danger.clean", str(program))
        self.git(str(self.state), "config", "filter.danger.smudge", str(program))
        self.init_local()
        self.assertFalse(marker.exists())
        actual = self.raw_git(self.state, "show", "HEAD:snapshots/first/applied/example.conf")
        self.assertEqual(actual, body)
        self.assertEqual(self.git(str(self.state), "status", "--porcelain"), "")
        self.assertEqual((self.state / ".git/info/attributes").read_bytes(), repo.ATTRIBUTES)

    def test_config_defined_hooks_and_signing_never_run_local_or_remote(self):
        self.valid_snapshot()
        hook = self.base / "hook-canary"
        signer = self.base / "sign-canary"
        canary = self.base / "inert-canary"
        canary.write_text("#!/bin/sh\ntouch " + str(hook) + "\n")
        canary.chmod(0o700)
        self.git(str(self.base), "init", "--initial-branch=main", str(self.state))
        for key, value in [("commit.gpgSign", "true"), ("tag.gpgSign", "true"),
                           ("gpg.program", str(canary)), ("hook.danger.event", "pre-push"),
                           ("hook.danger.command", "touch " + str(hook)),
                           ("hook.other.event", "pre-commit"), ("hook.other.command", str(canary))]:
            self.git(str(self.state), "config", key, value)
        self.git(str(self.state), "remote", "add", "origin", str(self.remote))
        self.init_local()
        code, out, err = self.invoke("update", "--no-capture", "--assume-private")
        self.assertEqual(code, 0, out + err)
        self.assertFalse(hook.exists() or signer.exists())
        self.assertEqual(self.remote_head(self.state), self.remote_head(self.remote))

    def test_empty_hook_suppression_mutation_executes_pre_push_canary(self):
        self.valid_snapshot(); self.init_local(); self.configure_origin()
        marker = self.base / "config-hook-ran-under-disabled-suppression"
        self.git(str(self.state), "config", "hook.danger.event", "pre-push")
        self.git(str(self.state), "config", "hook.danger.command", "touch " + str(marker))
        original = repo.git

        def mutate(root, *arguments, **options):
            if "push" in arguments:
                arguments = tuple(argument for argument in arguments if argument != "--no-verify")
            return original(root, *arguments, **options)

        with patch.object(repo, "_hook_suppressions", return_value=[]), patch.object(repo, "git", side_effect=mutate):
            code, out, err = self.invoke("update", "--no-capture", "--assume-private")
        self.assertTrue(marker.exists(), "Without pre-push suppression, this inert canary becomes observable")
        self.assertEqual(code, 0, out + err)

    def test_exact_staging_hooks_and_push_argv_survive_mutations(self):
        self.valid_snapshot()
        self.git(str(self.base), "init", "--initial-branch=main", str(self.state))
        self.configure_origin()
        pre_push = self.base / "prepush-ran"
        self.git(str(self.state), "config", "hook.danger.event", "pre-push")
        self.git(str(self.state), "config", "hook.danger.command", "touch " + str(pre_push))
        file_hook = self.state / ".git/hooks/pre-commit"
        file_hook.parent.mkdir(parents=True, exist_ok=True)
        file_hook.write_text("#!/bin/sh\ntouch " + str(pre_push) + "\n")
        file_hook.chmod(0o700)
        calls = []
        execute = subprocess.run
        def observe(argv, *args, **kwargs):
            calls.append(list(argv))
            return execute(argv, *args, **kwargs)
        with patch.object(repo.subprocess, "run", side_effect=observe):
            self.init_local()
            code, out, err = self.invoke("update", "--no-capture", "--assume-private")
        self.assertEqual(code, 0, out + err)
        self.assertFalse(pre_push.exists())
        additions = [list(argv) for argv in calls if Path(argv[0]).name == "git" and "add" in argv]
        self.assertTrue(additions)
        for argv in additions:
            index = argv.index("add")
            self.assertEqual(argv[index:index + 3], ["add", "--no-renormalize", "--"])
            self.assertNotIn("-A", argv[index + 3:])
            self.assertNotIn("add", argv[:index])  # No option can masquerade as git add -A.
        pushes = [argv for argv in calls if Path(argv[0]).name == "git" and "push" in argv]
        self.assertEqual(len(pushes), 1)
        push = pushes[0]
        self.assertIn("--no-verify", push)
        self.assertIn("--signed=no", push)
        self.assertIn(str(self.remote), push)
        index = push.index("push")
        self.assertNotIn("origin", push[index:])

    def test_linked_snapshot_directory_never_validates_or_stages_target(self):
        snap = self.valid_snapshot()
        outside = self.base / "external-capture"
        snap.rename(outside)
        snap.symlink_to(outside, target_is_directory=True)
        with patch.object(repo, "_validate_snapshot", side_effect=AssertionError("must not reach external validator")):
            code, out, err = self.invoke("init", "--no-remote")
        self.assertEqual(code, 0, out + err)
        self.assertIn("symlink", out + err)
        self.assertIsNone(self.remote_head(self.state))

    def test_each_internal_link_is_refused_before_external_writes(self):
        for relative in ("config", "info", "hooks", "objects", "refs"):
            with self.subTest(relative=relative):
                state = self.choose_state("link-" + relative)
                self.git(str(self.base), "init", str(state))
                outside = self.base / ("outside-" + relative)
                target = state / ".git" / relative
                if relative == "config":
                    outside.write_text("[user]\nname = External\n")
                    target.unlink()
                else:
                    outside.mkdir(mode=0o700)
                    shutil.rmtree(target)
                target.symlink_to(outside, target_is_directory=relative != "config")
                code, out, err = self.invoke("init", "--no-remote")
                self.assertEqual(code, 2)
                self.assertIn("symlink", out + err)
                if relative == "config":
                    self.assertEqual(outside.read_text(), "[user]\nname = External\n")
                else:
                    self.assertEqual(list(outside.iterdir()), [])

    def test_generated_launcher_command_and_nothing_new(self):
        self.valid_snapshot(); self.init_local()
        text = (self.state / "README.md").read_text()
        launcher = str(Path(__file__).resolve().parent.parent / "bin/xsnapshot-repo")
        self.assertIn(launcher + " --root " + str(self.state) + " update", text)
        self.assertIn("Run `" + launcher, text)
        result = subprocess.run([launcher, "--root", str(self.state), "update", "--no-capture", "--no-push"],
                                env=os.environ, text=True, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("No new complete snapshot", result.stdout)


"""Source packaging fixtures only. Never run a real collector or read a capture."""
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from tools.package_source import FILES, PackageError, build, package


class SourcePackageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.name', 'Synthetic Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.license = b'SYNTHETIC TEST LICENSE ONLY. Not a project license.\n'
        bodies = {'bin/xsnapshot': b'#!/bin/sh\nexit 99 # inert fixture, never execute\n',
                  'lib/xsnapshot.py': b'# inert synthetic source\n',
                  'docs/DISTRIBUTION.md': b'# Generic source guide\n', 'LICENSE': self.license,
                  'README.md': b'MACHINE-SPECIFIC-INVENTORY-MUST-NOT-BUNDLE\n',
                  'snapshots/private.txt': b'SYNTHETIC-CAPTURE-MUST-NOT-BUNDLE\n',
                  '.env': b'SYNTHETIC-ENV-MUST-NOT-BUNDLE\n'}
        for path, body in bodies.items():
            file = self.repo / path
            file.parent.mkdir(exist_ok=True, parents=True)
            file.write_bytes(body)
        self.commit = self.commit_all()
        self.license_hash = hashlib.sha256(self.license).hexdigest()

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        env = {**os.environ, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull}
        result = subprocess.run(['git', '-C', str(self.repo), *args], env=env,
                                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.stdout.decode().strip()

    def commit_all(self):
        self.git('add', '.')
        self.git('commit', '-qm', 'Synthetic packaging fixture')
        return self.git('rev-parse', 'HEAD')

    def test_deterministic_exact_file_list_bytes_and_manifest(self):
        first = build(self.repo, self.commit, self.license_hash)
        (self.repo / 'lib/xsnapshot.py').write_bytes(b'DIRTY WORKTREE MUST NOT BUNDLE')
        second = build(self.repo, self.commit, self.license_hash)
        self.assertEqual(first, second)
        name, compressed, manifest_raw = first
        manifest = json.loads(manifest_raw)
        self.assertEqual(manifest['commit'], self.commit)
        self.assertEqual(manifest['license_sha256'], self.license_hash)
        with tarfile.open(fileobj=io.BytesIO(compressed), mode='r:gz') as archive:
            members = archive.getmembers()
            prefix = 'xsnapshot-pc-' + self.commit[:12] + '/'
            self.assertEqual([m.name for m in members], sorted(prefix + n for n in [*FILES.values(), 'RELEASE-MANIFEST.json']))
            for member in members:
                self.assertTrue(member.isfile())
                self.assertEqual((member.uid, member.gid, member.mtime), (0, 0, 0))
                self.assertEqual(member.uname + member.gname, '')
                self.assertEqual(member.mode, 0o755 if member.name.endswith('/bin/xsnapshot') else 0o644)
            self.assertEqual(archive.extractfile(prefix + 'RELEASE-MANIFEST.json').read(), manifest_raw)
            for entry in manifest['files']:
                body = archive.extractfile(prefix + entry['path']).read()
                self.assertEqual(len(body), entry['bytes'])
                self.assertEqual(hashlib.sha256(body).hexdigest(), entry['sha256'])
                self.assertEqual(entry['git_blob'], self.git('rev-parse', self.commit + ':' + entry['source_path']))
        raw = gzip.decompress(compressed)
        for forbidden in [b'MACHINE-SPECIFIC', b'SYNTHETIC-CAPTURE', b'SYNTHETIC-ENV', b'DIRTY WORKTREE', b'.git/']:
            self.assertNotIn(forbidden, raw)
        self.assertTrue(name.endswith('.tar.gz'))

    def test_missing_or_mismatched_license_fails_before_output(self):
        for digest in ['0' * 64, 'bad']:
            with self.assertRaises(PackageError):
                package(self.repo, self.commit, digest, self.root / 'output')
        (self.repo / 'LICENSE').unlink()
        commit = self.commit_all()
        with self.assertRaisesRegex(PackageError, 'Missing required source file: LICENSE'):
            package(self.repo, commit, self.license_hash, self.root / 'output')
        self.assertFalse((self.root / 'output').exists())

    def test_branches_tags_short_hashes_and_tree_objects_are_rejected(self):
        for commit in ['HEAD', 'main', 'v1.0', self.commit[:12], '../elsewhere', self.git('rev-parse', 'HEAD^{tree}')]:
            with self.assertRaises(PackageError):
                build(self.repo, commit, self.license_hash)

    def test_symlinks_and_missing_required_code_are_rejected(self):
        code = self.repo / 'lib/xsnapshot.py'
        code.unlink()
        code.symlink_to('../.env')
        commit = self.commit_all()
        with self.assertRaisesRegex(PackageError, 'regular Git blob'):
            build(self.repo, commit, self.license_hash)
        code.unlink()
        commit = self.commit_all()
        with self.assertRaisesRegex(PackageError, 'Missing required'):
            build(self.repo, commit, self.license_hash)

    def test_binary_empty_and_over_limit_source_are_rejected(self):
        for body in [b'\0binary', b'', b'\xff', b'x' * (1024 * 1024 + 1)]:
            (self.repo / 'lib/xsnapshot.py').write_bytes(body)
            commit = self.commit_all()
            with self.assertRaises(PackageError):
                build(self.repo, commit, self.license_hash)

    def test_output_is_private_checksummed_and_never_overwrites(self):
        output = self.root / 'candidate'
        result = package(self.repo, self.commit, self.license_hash, output)
        self.assertFalse(result['published'])
        self.assertEqual(output.stat().st_mode & 0o777, 0o700)
        for line in (output / 'SHA256SUMS').read_text().splitlines():
            digest, name = line.split('  ')
            self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), digest)
            self.assertEqual((output / name).stat().st_mode & 0o777, 0o600)
        before = {p.name: p.read_bytes() for p in output.iterdir()}
        with self.assertRaises(PackageError):
            package(self.repo, self.commit, self.license_hash, output)
        self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir()})
        link = self.root / 'linked-output'
        link.symlink_to(output, target_is_directory=True)
        with self.assertRaises(PackageError):
            package(self.repo, self.commit, self.license_hash, link)

    def test_git_replace_and_routing_environment_cannot_change_selected_bytes(self):
        expected = build(self.repo, self.commit, self.license_hash)
        (self.repo / 'lib/xsnapshot.py').write_bytes(b'REPLACED SOURCE MUST NOT BUNDLE')
        replacement = self.commit_all()
        self.git('replace', self.commit, replacement)
        with patch.dict(os.environ, {'GIT_DIR': str(self.root / 'missing'), 'GIT_WORK_TREE': '/invalid', 'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'core.bare', 'GIT_CONFIG_VALUE_0': 'true'}):
            self.assertEqual(build(self.repo, self.commit, self.license_hash), expected)


if __name__ == '__main__':
    unittest.main()

class PackageCommandTest(unittest.TestCase):
    def test_cli_requires_explicit_commit_license_hash_and_new_output(self):
        script = Path(__file__).resolve().parents[1] / 'tools/package_source.py'
        result = subprocess.run(['python3', str(script)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 2)
        self.assertIn(b'--license-sha256', result.stderr)
        self.assertIn(b'--commit', result.stderr)
        self.assertIn(b'--output', result.stderr)

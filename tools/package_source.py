#!/usr/bin/env python3
"""Build a local, deterministic source candidate. Never collect, upload or release."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile

# Explicit source-to-archive mapping. Never add a recursive directory or git archive.
FILES = {
    'bin/xsnapshot': 'bin/xsnapshot',
    'lib/xsnapshot.py': 'lib/xsnapshot.py',
    'docs/DISTRIBUTION.md': 'README.md',
    'LICENSE': 'LICENSE',
}
MAX_FILE_BYTES = 1024 * 1024
OFFICIAL_REPOSITORY = 'https://github.com/VeigaPunk/xsnapshot-pc'


class PackageError(ValueError):
    pass


def git(repo: Path, *args: str) -> bytes:
    # Replacement objects can silently change the content resolved by a commit ID.
    env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    env.update({'GIT_NO_REPLACE_OBJECTS': '1', 'GIT_TERMINAL_PROMPT': '0',
                'GIT_NO_LAZY_FETCH': '1', 'GIT_ALLOW_PROTOCOL': '', 'GIT_PROTOCOL_FROM_USER': '0',
                'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull})
    # No caller-side routing/config overrides and no lazy fetch, including on
    # older Git versions that do not understand GIT_NO_LAZY_FETCH.
    result = subprocess.run(['git', '-C', str(repo), *args], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise PackageError('Required source object is missing or unreadable in the local repository.')
    return result.stdout


def build(repo: Path, commit: str, license_sha256: str) -> tuple[str, bytes, bytes]:
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise PackageError('Use the full, reviewed 40-character commit, not a branch or tag.')
    if not re.fullmatch(r'[0-9a-f]{64}', license_sha256):
        raise PackageError('Supply the SHA-256 of the owner-approved LICENSE from that commit.')
    if git(repo, 'cat-file', '-t', commit).strip() != b'commit':
        raise PackageError('The requested source object is not a commit.')
    entries, payloads = [], []
    for source, target in sorted(FILES.items(), key=lambda item: item[1]):
        raw = git(repo, 'ls-tree', '-z', commit, '--', source)
        records = raw.rstrip(b'\0').split(b'\0') if raw else []
        if len(records) != 1:
            raise PackageError(f'Missing required source file: {source}. No package was created.')
        metadata, path = records[0].split(b'\t', 1)
        mode, kind, oid = metadata.decode('ascii').split(' ')
        if path.decode('utf8') != source or kind != 'blob' or mode not in ('100644', '100755'):
            raise PackageError(f'Release source must be a regular Git blob, never a symlink or submodule: {source}.')
        size = int(git(repo, 'cat-file', '-s', oid))
        if size < 1 or size > MAX_FILE_BYTES:
            raise PackageError(f'Release file must be nonempty and at most 1 MiB: {source}.')
        body = git(repo, 'cat-file', 'blob', oid)
        if len(body) != size or b'\0' in body:
            raise PackageError(f'Release file has invalid size or binary content: {source}.')
        try:
            body.decode('utf8', errors='strict')
        except UnicodeDecodeError as error:
            raise PackageError(f'Release file is not UTF-8 text: {source}.') from error
        digest = hashlib.sha256(body).hexdigest()
        if source == 'LICENSE' and digest != license_sha256:
            raise PackageError('LICENSE does not match the supplied owner-approved hash. No package was created.')
        archive_mode = 0o755 if target == 'bin/xsnapshot' else 0o644
        payloads.append((target, body, archive_mode))
        entries.append({'path': target, 'source_path': source, 'git_blob': oid,
                        'bytes': size, 'sha256': digest, 'mode': oct(archive_mode)})
    manifest = (json.dumps({
        'schema': 'xsnapshot/source-candidate/v1', 'expected_repository': OFFICIAL_REPOSITORY,
        'commit': commit, 'license_sha256': license_sha256, 'files': entries,
        'notice': 'Local source candidate only. Hashes prove integrity, not publisher identity, license authorization, review, signing or permission to distribute. No captures or repository history included.',
    }, sort_keys=True, indent=2) + '\n').encode()
    root = 'xsnapshot-pc-' + commit[:12]
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        for target, body, mode in sorted([*payloads, ('RELEASE-MANIFEST.json', manifest, 0o644)]):
            info = tarfile.TarInfo(root + '/' + target)
            info.size, info.mode, info.mtime = len(body), mode, 0
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            archive.addfile(info, io.BytesIO(body))
    compressed = io.BytesIO()
    with gzip.GzipFile(filename='', fileobj=compressed, mode='wb', mtime=0, compresslevel=9) as stream:
        stream.write(tar_buffer.getvalue())
    return root + '.tar.gz', compressed.getvalue(), manifest


def package(repo: Path, commit: str, license_sha256: str, output: Path) -> dict:
    name, archive, manifest = build(repo, commit, license_sha256)
    # A new directory is the publication boundary. Never replace existing work.
    try:
        output.mkdir(mode=0o700, parents=False, exist_ok=False)
    except FileExistsError as error:
        raise PackageError('Output directory already exists. Choose a new directory; nothing was overwritten.') from error
    files = {name: archive, 'RELEASE-MANIFEST.json': manifest}
    checksums = ''.join(hashlib.sha256(body).hexdigest() + '  ' + path + '\n'
                        for path, body in sorted(files.items())).encode()
    for path, body in {**files, 'SHA256SUMS': checksums}.items():
        fd = os.open(output / path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(body)
    return {'commit': commit, 'archive': name, 'sha256': hashlib.sha256(archive).hexdigest(),
            'files': len(FILES), 'published': False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--commit', required=True, help='Full reviewed source commit, not a branch or tag')
    parser.add_argument('--license-sha256', required=True, help='Hash of owner-approved LICENSE in that commit')
    parser.add_argument('--output', required=True, type=Path, help='New output directory with an existing parent')
    args = parser.parse_args()
    try:
        result = package(args.repo, args.commit, args.license_sha256, args.output)
    except (PackageError, OSError) as error:
        parser.exit(1, f'Candidate packaging stopped: {error}\nNo release was published. Preserve any partial output before trying a new directory.\n')
    print(json.dumps(result, sort_keys=True))
    print('Local candidate only. Review the manifest and file list. No tag, release, signature or upload was created.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

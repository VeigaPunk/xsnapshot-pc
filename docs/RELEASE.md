# Collector release readiness

This document is the release procedure. It does not itself create a release or
tag; the published releases and their verified commits are listed on the
repository's Releases page, and the website pins one exact tag and commit.

## Verified starting point

Source reviewed: commit 8d62a4d9db49b8b22c1ec057b9a700a48e0e523b.
GitHub reports this commit as unsigned. A Git commit hash binds content; it is
not a publisher signature or an artifact attestation.

The collector uses Python's standard library and a small Bash wrapper. There is
no Python package manifest or third-party Python dependency to install.
The repository intentionally contains a previously published workstation capture.
A software release must not bundle snapshots or the machine-specific inventory
README as a generic product guide.

## Portability fixes in this change

- Capture identifiers cannot traverse directories.
- Force recapture cannot delete the snapshots root or follow a symlink target.
- Validation accepts small complete inventories; the committed seed's 100+
  checks remain in its dedicated regression tests.
- Validation rejects symlinks/special files before reading artifacts, duplicate
  JSON keys/index entries, inconsistent config membership/counts, unsafe paths,
  missing report/seal, tampering and over-limit inputs.
- Existing global --root supports keeping generated state separate from the
  source checkout. For a reviewed collector, a distribution installer should
  invoke bin/xsnapshot --root STATE collect, and validate STATE/snapshots/ID.
  The repository default remains unchanged for its existing inventory workflow.

The new tests use synthetic temporary directories and a mocked Collector.
They do not inventory the developer or CI machine, and do not upload captures.

## Before enabling distribution

1. Review the candidate commit and run the full tests plus a real Linux capture
   with the operator's approval. Exercise first run, same-day refusal, explicit
   force, interrupted/partial output and website folder import. Review all
   captured files locally. Never push an unreviewed capture.
2. License: the owner approved the MIT License on 2026-11-09. `LICENSE` in this
   tree is the authorized text; pass its SHA-256 to the packaging tool.
3. Prepare a code-only source package from an exact reviewed commit. Include
   bin/xsnapshot, lib/xsnapshot.py, product/privacy documentation and the approved
   license. Exclude snapshots, credentials, user configuration and repository
   history. A compiled binary is unnecessary for this stdlib collector.
4. Rebuild deterministically and verify the exact file list and SHA-256 checksum.
   Record candidate commit, checks and package hash. A checksum is integrity,
   not proof of publisher identity.
5. Obtain approval for the named version/tag and distribution. If signing or
   provenance attestation needs new keys, OIDC grants or persistent access,
   obtain separate approval. Do not invent a signature or use an unrelated key.
6. Publish the approved source release, verify the tag's peeled commit and asset
   hash independently, then update the website's immutable pin and its installer
   tests. Do not follow main/latest or accept an environment override.
7. Website deployment and domain/DNS remain separate gates.

CI is read-only to the repository. It creates no tags, releases, credentials,
packages or remote resources.

## Local verification commands

Use a supported Linux machine with Bash, Git and Python 3.10 or newer.
Check out the exact reviewed candidate commit from the official repository first;
do not test an unknown modified checkout. These commands collect locally only.
Start without sudo, so protected configurations may be omitted and reported.

```sh
python3 -m unittest discover -s tests -v
./bin/xsnapshot preflight
state="$(mktemp -d "${TMPDIR:-/tmp}/xsnapshot-verify.XXXXXX")"
./bin/xsnapshot --root "$state" collect --snapshot verify --no-sudo
./bin/xsnapshot --root "$state" validate "$state/snapshots/verify"
printf 'Review locally: %s/snapshots/verify/REPORT.md\n' "$state"
git status --short
```

The source checkout should remain unchanged. A second identical collect command
must refuse to overwrite the existing capture. After reviewing and preserving
anything needed, an operator can deliberately add `--force` to recapture only
that test directory. Review the report, excluded material and every retained
configuration locally; automatic redaction is not a guarantee.

For the website, start its local Pages runtime, select this complete folder and
verify local validation/report review. Do not publish or push this capture as
part of the test. Publishing real machine data is a separate explicit action.
Keep or remove the temporary state yourself after review; these instructions do
not delete it automatically.

## Deterministic local source candidate

After the candidate commit is reviewed, `tools/package_source.py` can prepare a local code-only candidate. It does not make a release. The license must exist in that exact commit, and its SHA-256 must match the explicitly supplied owner-approved value; a missing or mismatched `LICENSE` keeps packaging fail-closed.

```sh
python3 tools/package_source.py \\
  --repo /path/to/reviewed/xsnapshot-pc \\
  --commit FULL_40_CHARACTER_REVIEWED_COMMIT \\
  --license-sha256 OWNER_APPROVED_LICENSE_SHA256 \\
  --output /existing/parent/new-candidate-directory
```

The output directory must not exist. The script writes a private source archive, a matching JSON manifest and SHA256SUMS. Compare two independent local builds and review the exact archive list before considering publication. Existing directories and symlinks are not overwritten. A failed filesystem write can leave partial output; preserve and inspect it, then choose a new destination rather than automatically deleting or overwriting it.

Only four exact source files are included: bin/xsnapshot, lib/xsnapshot.py, LICENSE, and docs/DISTRIBUTION.md mapped to the package README.md. RELEASE-MANIFEST.json is generated with the source commit, Git blob IDs, byte sizes and SHA-256 values. Root README.md, docs/PRIVACY.md (which contains historical capture findings), snapshots, credentials, tests and Git history are not packaged. Symlinks, submodules, missing/empty/over-limit files and non-UTF-8/binary input fail closed. Files are read from immutable Git objects, never the potentially dirty worktree. Git replacement objects, caller routing overrides and all transport protocols are disabled; no missing object is fetched automatically.

Tar ordering, ownership, permissions and timestamps are normalized; gzip has an empty original filename and zero timestamp. Reproducibility is tested for repeated builds with the same Python/zlib toolchain. Cross-toolchain compression identity still needs verification before claiming a universally reproducible release. The manifest's expected_repository is a declared project location, not proof of origin or a publisher attestation. Review the actual repository provenance separately.

The new packaging tests use tiny synthetic Git repositories with an explicitly fake test license, inert source, and marker files representing data that must be excluded. They never collect a machine, package the existing real capture, contact GitHub, sign, create tags/releases, or upload outputs. The complete existing collector tests and seed validation remain required. This preparation does not satisfy real Linux capture/import, licensing, version/distribution approval, signing or website deployment gates.




## Local Docker inventory verification

Before release, run `python3 -m unittest discover -s tests -v`. The Docker locality fixtures use synthetic socket metadata and an inert local executable, never Docker or a real daemon. They verify fixed socket selection, refusal of unsupported file types, no remote context fallback, direct arguments, a private empty configuration, an environment without saved endpoints/credentials/headers/proxies, cleanup, and truthful partial/unavailable status. They do not establish real daemon compatibility or a real workstation capture.

For an approved local smoke check, use a verified source candidate and the no-sudo procedure in DISTRIBUTION.md. Check `data/snapshot.json` under `docker` and `system/docker.txt`. A missing or inaccessible supported socket is an expected unavailable result; do not change Docker permissions, add groups, enable a daemon, grant sudo or switch contexts just to get a green result. Real rootless/system Docker success still needs a separately reviewed local check. Keep the full capture private and do not commit it.


## Private-output verification

The private-output tests run with a permissive umask and verify `0700` capture directories and `0600` files, including copied configuration bodies and the seal. They exercise symlink/hard-link/FIFO destinations, unsafe paths, duplicate writes, replacement of the capture root, unknown files, interruption, competing directory creation and refusal to silently change existing permissions. A synthetic inventory runs the real CLI orchestration, report generation, index, seal and validation without querying a workstation or invoking inventory commands.

These fixtures do not validate source-file privacy, real-machine command behavior, or distribution approval. Real capture review remains a separate release prerequisite. In particular, output permissions do not turn inherited command settings or allow-listed source content into trusted data.


## Startup and preflight verification

The startup fixtures provide synthetic Bash environment hooks, exported functions, inherited shell options, a PATH Python shim, Python startup modules and a shadow standard-library module. The launcher and fixed inventory command shell must ignore these canaries without invoking real inventory commands. Preflight checks are separately tested not to execute programs or read configuration bodies, to return a failing status for unsupported core prerequisites, and never to claim that a real capture was verified. A real preflight on a machine only validates these prerequisites, not collection or output privacy.

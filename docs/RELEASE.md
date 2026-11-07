# Collector release readiness

No release/tag is created by these changes. This repository has no published
release or tag as checked on 2026-11-07. The website installer remains disabled.

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
2. Decide and supply the authorized software license. No LICENSE file exists in
   the current collector tree; this change does not choose or grant one.
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

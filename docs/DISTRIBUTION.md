# xsnapshot-pc source candidate

A Linux-first, Python-standard-library collector for a point-in-time record of a PC's hardware, software and configuration index. It is a local inventory tool, not a disk image, live monitor or automatic restore system. Support depends on the inventory commands available on the machine; missing tools and protected files can leave gaps. Arch/Omarchy-specific inventory does not become portable merely because Python runs on another distribution.

This guide is generic. The source candidate contains no workstation capture, repository history or machine-specific inventory README. The accompanying RELEASE-MANIFEST.json binds each packaged file to its source blob and exact commit. Checksums verify bytes, not who published them, whether their license was authorized, or whether the software is safe. Obtain the release through the official project and verify its approved provenance before running it.

## Requirements and review

- Linux, Bash and Python 3.10 or newer. No third-party Python package is required.
- Read the exact packaged `lib/xsnapshot.py`, especially the configuration allow-list, commands and redaction logic, before collection. Do not run a package from an unverified source.
- Most inventory commands inherit the machine's configuration. Review configured services and command wrappers before execution; do not assume all subprocesses are offline. Docker daemon inventory has the narrower boundary described below.
- Start without sudo. Protected information can be omitted. Do not grant privileges merely to make a capture look complete.

## Capture outside the source directory

Run from the extracted, verified source directory. Pick a new state directory outside it. For example:

```sh
state="$(mktemp -d "${TMPDIR:-/tmp}/xsnapshot-local.XXXXXX")"
./bin/xsnapshot --root "$state" collect --snapshot review --no-sudo
./bin/xsnapshot --root "$state" validate "$state/snapshots/review"
printf 'Review locally: %s/snapshots/review/REPORT.md\n' "$state"
```

Collection reads allow-listed information and writes local files. It does not upload the capture to the xsnapshot website. A repeated collection into the same capture must refuse to overwrite it. `--force` is a deliberate replacement, not a repair step: preserve anything needed and review the exact destination first. Do not run it just to dismiss an error.

Keep the complete output folder. It contains snapshot JSON, the report, the artifact seal and supporting local files. Review REPORT.md, the excluded-material list and every retained configuration. Redaction is best-effort, not proof that all secrets or personal details were removed. Configurations, environment values, inventory and command output can reveal sensitive context. If anything should not be included, correct the source capture before sharing. Validation checks structure and integrity; it does not establish privacy or provenance by itself.

## Private local output

New capture directories and artifact subdirectories are created with mode `0700`; new report, JSON, manifest and configuration files use `0600`, subject to a stricter existing umask. A permissive shell umask cannot make new capture contents group- or world-readable. The collector refuses an existing output directory or subdirectory with another owner or group/other access rather than changing its permissions.

Artifact writes create new files exclusively through directory-relative, no-follow handles. Existing files, hard links, symlink destinations and special files are not overwritten. The collector stops if its capture root is replaced during collection. The seal includes only files written by this collector instance; unexpected files are rejected rather than silently bundled into the capture.

These are local filesystem access controls, not encryption. They do not protect against the same account, administrators, malware, filesystem behavior that does not enforce Unix permissions, or sharing/copying the files elsewhere. Redaction and local review remain necessary. Existing captures and their permissions are not changed. A stopped capture can contain private partial files; inspect them and validate a complete capture before sharing. Rerunning does not silently reuse a partial directory.

## Docker inventory: local transport only

Docker daemon inventory ignores the active context, `DOCKER_HOST`, `DOCKER_CONTEXT`, custom headers, proxies and saved Docker credentials/configuration. It selects the first supported socket: `/run/user/<effective-uid>/docker.sock` (rootless), then `/var/run/docker.sock` (system). The final path must be a socket, not a symlink, directory or regular file. It uses the Docker binary on Python's system default executable path, direct arguments with an explicit Unix host, an empty private temporary configuration directory, and no sudo. Your Docker context and configuration are never changed.

Only `info`, container listing, image listing, volume listing and network listing are requested. The temporary configuration is removed when the commands finish. Rootless takes priority when both sockets exist. Once selected, a failed query does not switch to another daemon. Remote contexts, custom socket paths and Docker Desktop contexts are omitted, even if they are your normal default. A system installation without the supported socket or Docker binary is reported as unavailable, not as a machine with no containers.

The JSON contains `docker.capture_status` (`captured`, `partial` or `unavailable`) and a status for each section. An empty list is meaningful only when that section says `captured`. Unavailable sections and omitted contexts must not be used to infer that Docker resources do not exist. Read `system/docker.txt` and the report notes before sharing.

A local Unix socket establishes transport, not the daemon's physical location or trustworthiness: a local service can proxy elsewhere. `daemon_identity_verified` is therefore always false. This change does not sandbox other collector commands, validate every local executable, or make redaction a privacy guarantee. Docker names, image references and other successful inventory output still require local review.

Sources: [Docker contexts](https://docs.docker.com/engine/manage-resources/contexts/), [Docker CLI configuration and environment](https://docs.docker.com/reference/cli/docker/), and [rootless socket locations](https://docs.docker.com/engine/security/rootless/tips/).

## Optional website use

The website is a separate project. Opening the complete capture folder is a local review step. Only an explicit, separately reviewed publication should send its snapshot JSON. Report and configuration bodies should stay local. A single JSON file is preview-only because it cannot prove the complete folder's integrity.

An unlisted link is readable by anyone who has it. Keep the private delete/recovery receipt separate from the public JSON. Removing a shared copy cannot remove copies somebody else saved. A snapshot is not a backup of every configuration and cannot reinstall or restore a PC automatically.

## License

The package must include the owner's approved LICENSE, with its exact SHA-256 in the release manifest. The packaging tool refuses a missing or mismatched license. A matching hash does not itself grant permission to distribute; release approval and any signing/provenance requirements remain separate.


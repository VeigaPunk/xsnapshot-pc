# xsnapshot-pc source candidate

A Linux-first, Python-standard-library collector for a point-in-time record of a PC's hardware, software and configuration index. It is a local inventory tool, not a disk image, live monitor or automatic restore system. Support depends on the inventory commands available on the machine; missing tools and protected files can leave gaps. Arch/Omarchy-specific inventory does not become portable merely because Python runs on another distribution.

This guide is generic. The source candidate contains no workstation capture, repository history or machine-specific inventory README. The accompanying RELEASE-MANIFEST.json binds each packaged file to its source blob and exact commit. Checksums verify bytes, not who published them, whether their license was authorized, or whether the software is safe. Obtain the release through the official project and verify its approved provenance before running it.

## Requirements and review

- Linux, Bash and Python 3.10 or newer. No third-party Python package is required.
- Read the exact packaged `lib/xsnapshot.py`, especially the configuration allow-list, commands and redaction logic, before collection. Do not run a package from an unverified source.
- Inventory commands inherit the machine's configuration. Review configured services, command wrappers and contexts before execution; do not assume subprocesses cannot contact a configured remote service.
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

## Optional website use

The website is a separate project. Opening the complete capture folder is a local review step. Only an explicit, separately reviewed publication should send its snapshot JSON. Report and configuration bodies should stay local. A single JSON file is preview-only because it cannot prove the complete folder's integrity.

An unlisted link is readable by anyone who has it. Keep the private delete/recovery receipt separate from the public JSON. Removing a shared copy cannot remove copies somebody else saved. A snapshot is not a backup of every configuration and cannot reinstall or restore a PC automatically.

## License

The package must include the owner's approved LICENSE, with its exact SHA-256 in the release manifest. The packaging tool refuses a missing or mismatched license. A matching hash does not itself grant permission to distribute; release approval and any signing/provenance requirements remain separate.

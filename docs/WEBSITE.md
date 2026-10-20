# xsnapshot website — future contract

> Status: **not shipped**. This repository ships the local collector
> (`bin/xsnapshot`, `lib/xsnapshot.py`) and the committed snapshot
> `snapshots/2026-10-19/`. No website, backend, or upload endpoint exists here.
> This document is the contract a future `xsnapshot-pc` website must satisfy;
> it describes no shipped code.

## Why a website cannot collect

A browser cannot read a PC: it cannot enumerate packages, read `/etc`, or
request privilege. The collector must run on the machine being captured.

## 1. Downloadable, run-local collector

- The website distributes the collector, never collects for anyone: a tagged
  clone/tarball of this repository plus a one-line run
  (`./bin/xsnapshot collect`).
- The collector is Python-stdlib-only, Linux-first, and offline; it writes
  `snapshots/<YYYY-MM-DD>/` exactly as this repository's seed snapshot does.
- A published collector build must be byte-identical to the repository tag;
  `data/snapshot.json` records `collector.name`/`collector.version` so a
  snapshot can be traced to the code that produced it.
- Before any upload, the visitor can self-validate locally:
  `./bin/xsnapshot validate` and `python3 -m unittest discover -s tests -v`.

## 2. Import / upload of a snapshot directory

- Primary import path: pick or drop a `snapshots/<id>/` directory (folder
  picker / drag-and-drop); the viewer reads `data/snapshot.json` from the
  visitor's disk with no network traffic.
- Secondary path: explicit upload of the same directory (zip/tar accepted,
  unpacked in the browser or quarantined server-side). Reject archives
  without `data/snapshot.json` or with failing artifact hashes.
- Import must never rewrite snapshot content; the directory is read-only
  input.
- Upload is opt-in and per-snapshot. Loading locally never uploads.

## 3. Static viewer

- The single source of truth is `snapshots/<id>/data/snapshot.json`.
- Artifacts are addressed by the relative paths recorded in
  `artifacts[].path`; the viewer verifies each SHA-256 when the file is
  present and flags unverifiable ones.
- Rendering is inert: file bodies and captured command output are shown as
  text; no snapshot content is executed as script or HTML.
- The viewer works offline over a locally served or picked snapshot and
  tolerates unknown keys (forward compatibility).

## 4. Privacy gate before publish

- Nothing becomes public automatically. Publishing a snapshot (making it
  visible to anyone but its author) requires:
  1. `xsnapshot validate` passing (structure and artifact hashes);
  2. the raw-identifier scan in `tests/test_snapshot.py` passing (UUID, MAC,
     IPv4, machine/boot-ID shapes and literal secret assignments) — any hit
     blocks publish until the source capture is corrected;
  3. an explicit human confirmation that `REPORT.md`'s privacy section and
     the excluded-material list were reviewed.
- The gate runs on the exact bytes being published.

## 5. Schema versioning

- `data/snapshot.json` carries `schema: "xsnapshot/v1"`.
- The viewer is written against one schema major version. Unknown *keys* are
  ignored (additive evolution); an unknown `xsnapshot/vN` must fail closed —
  show a compatibility message instead of half-rendering.
- Breaking changes bump the major; additive changes stay within it.
  `collector.version` versions the collector code, independent of the schema.
- Old snapshots are never migrated in place; any conversion happens in the
  viewer's memory.

## Non-goals

- No server-side collection, no reading a visitor's machine beyond explicitly
  picked files, no analytics identity, no publish without the gate.
- This repository does not ship the website, its backend, or upload endpoints
  yet; this document only fixes the contract they must meet.
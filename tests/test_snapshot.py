#!/usr/bin/env python3
"""Integrity tests for the committed snapshot ``snapshots/2026-10-19/``.

Two layers:

* structure, cross-file and SHA-256 checks over ``data/snapshot.json`` — the
  same invariants ``bin/xsnapshot validate`` enforces, plus inventory
  cross-checks that the CLI does not do;
* a raw-identifier scan over the committed config surface (``applied/`` and
  ``etc/``) that fails if the redactor regresses and lets a UUID, MAC, IPv4 or
  machine/boot-ID shape reach a committed file.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SNAPSHOT_ID = "2026-10-19"  # repository seed; bump when a new capture is committed
SNAPSHOT = ROOT / "snapshots" / SNAPSHOT_ID
DATA_PATH = SNAPSHOT / "data" / "snapshot.json"

REQUIRED_KEYS = (
    "schema",
    "snapshot_id",
    "captured_at",
    "host",
    "os",
    "hardware",
    "storage",
    "desktop",
    "packages",
    "config_index",
    "artifacts",
    "privacy",
    "commands",
    "notes",
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SnapshotJsonTest(unittest.TestCase):
    """Structure and hash integrity of the committed snapshot."""

    @classmethod
    def setUpClass(cls) -> None:
        if not DATA_PATH.is_file():
            raise AssertionError(f"missing committed snapshot: {DATA_PATH}")
        cls.data = json.loads(DATA_PATH.read_text(encoding="utf-8"))

    def test_schema_and_snapshot_identity(self) -> None:
        self.assertEqual(self.data["schema"], "xsnapshot/v1")
        self.assertEqual(self.data["snapshot_id"], SNAPSHOT.name)

    def test_captured_at_is_iso8601(self) -> None:
        dt.datetime.fromisoformat(self.data["captured_at"])

    def test_required_sections_present(self) -> None:
        missing = [key for key in REQUIRED_KEYS if key not in self.data]
        self.assertEqual(missing, [])

    def test_package_counts(self) -> None:
        packages = self.data["packages"]
        self.assertGreater(packages["all_count"], 1000)
        self.assertGreater(packages["explicit_count"], 200)
        self.assertGreaterEqual(packages["all_count"], packages["explicit_count"])
        self.assertEqual(packages["all_count"], len(packages["all"]))
        self.assertEqual(packages["explicit_count"], len(packages["explicit"]))
        self.assertEqual(packages["foreign_count"], len(packages["foreign"]))

    def test_package_inventories_match_committed_files(self) -> None:
        for key in ("all", "explicit", "foreign"):
            lines = (
                (SNAPSHOT / "packages" / f"pacman-{key}.txt")
                .read_text(encoding="utf-8")
                .splitlines()
            )
            self.assertEqual(lines, self.data["packages"][key], key)

    def test_config_index_integrity(self) -> None:
        index = self.data["config_index"]
        self.assertGreater(len(index), 100)
        artifact_paths = {item["path"] for item in self.data["artifacts"]}
        for entry in index:
            path = SNAPSHOT / entry["path"]
            self.assertTrue(path.is_file(), entry["path"])
            self.assertEqual(entry["bytes"], path.stat().st_size, entry["path"])
            self.assertEqual(entry["snapshot_sha256"], sha256_file(path), entry["path"])
            self.assertIn("source", entry)
            self.assertNotIn("source_sha256", entry)
            self.assertGreaterEqual(entry["redactions"], 0)
            self.assertIn(entry["path"], artifact_paths, entry["path"])
        privacy = self.data["privacy"]
        self.assertEqual(privacy["config_files_captured"], len(index))
        # The total also covers redactions applied to command output, which has
        # no per-file counter.
        self.assertGreaterEqual(
            privacy["redactions_applied"], sum(entry["redactions"] for entry in index)
        )

    def test_artifact_hashes_match_files(self) -> None:
        artifacts = self.data["artifacts"]
        self.assertGreater(len(artifacts), 100)
        for item in artifacts:
            path = SNAPSHOT / item["path"]
            self.assertTrue(path.is_file(), f"missing artifact: {item['path']}")
            self.assertEqual(item["bytes"], path.stat().st_size, item["path"])
            self.assertEqual(item["sha256"], sha256_file(path), item["path"])

    def test_artifact_index_covers_every_inventory_file(self) -> None:
        on_disk = {
            str(path.relative_to(SNAPSHOT))
            for path in SNAPSHOT.rglob("*")
            if path.is_file()
        }
        indexed = {item["path"] for item in self.data["artifacts"]}
        # REPORT.md is indexed. data/snapshot.json and ARTIFACTS.sha256 are
        # self-referential; the seal covers both plus every other file.
        self.assertEqual(indexed, on_disk - {"data/snapshot.json", "ARTIFACTS.sha256"})
        self.assertTrue((SNAPSHOT / "REPORT.md").is_file())

    def test_artifact_seal_covers_every_file(self) -> None:
        seal_path = SNAPSHOT / "ARTIFACTS.sha256"
        self.assertTrue(seal_path.is_file())
        seal: dict[str, str] = {}
        for line in seal_path.read_text(encoding="utf-8").splitlines():
            self.assertRegex(line, r"^[0-9a-f]{64}  .+$")
            digest, rel = line.split("  ", 1)
            self.assertNotIn(rel, seal)
            seal[rel] = digest
        on_disk = {
            str(path.relative_to(SNAPSHOT))
            for path in SNAPSHOT.rglob("*")
            if path.is_file()
        }
        self.assertEqual(set(seal), on_disk - {"ARTIFACTS.sha256"})
        for rel, digest in seal.items():
            self.assertEqual(digest, sha256_file(SNAPSHOT / rel), rel)


IDENTIFIER_PATTERNS = {
    "uuid": re.compile(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
    ),
    "mac": re.compile(r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b"),
    "ipv4": re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])"),
    "machine-id label": re.compile(
        r"(?i)(?:machine[-_]?id|boot[-_]?id)\s*[:=]\s*[0-9a-f]{16,}"
    ),
    "machine-id shape": re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{32}(?![0-9a-fA-F])"),
}

CANARY_SAMPLES = {
    "uuid": "8f1c2d3e-4a5b-4c6d-8e9f-0a1b2c3d4e5f",
    "mac": "00:00:5e:00:53:0a",
    "ipv4": "192.0.2.53",
    "machine-id label": "machine-id=3f9a2b7c8d4e5f60a1b2c3d4e5f6a7b8",
    "machine-id shape": "3f9a2b7c8d4e5f60a1b2c3d4e5f6a7b8",
}

# Documented, non-secret hex-shaped values already present in the committed
# captured configs.  Each is an upstream/derived value, not a host identifier.
ALLOWED_IDENTIFIER_SHAPES = {
    "etc/bluetooth/main.conf": {
        # bluez ships this as a comment example for a 128-bit SIRK value.
        "861fae703ed681f0c50b34155b6434fb": "upstream documentation example",
    },
    "etc/ufw/user.rules": {
        # ufw serializes the ASCII rule comment "allow-docker-dns" as hex.
        "616c6c6f772d646f636b65722d646e73": (
            'hex-encoded ASCII rule comment ("allow-docker-dns")'
        ),
    },
}


class RawIdentifierScanTest(unittest.TestCase):
    """applied/ and etc/ must contain no raw identifier shapes.

    ``packages/`` and ``system/`` are deliberately out of scope:

    * ``packages/`` holds package inventories whose version strings match the
      IPv4 shape (56 occurrences in the committed capture, e.g. ``1.2.16.1``
      in ``pacman-all.txt``) — false positives, not addresses;
    * ``system/`` holds sanitized command transcripts, not allow-listed config
      files; those transcripts legitimately carry public build identifiers as
      hex tokens (e.g. the 40-hex Hyprland commit hash in
      ``system/desktop.txt``) and version tables.

    The allow-listed config surface is the one where a raw identifier means
    the redactor failed.
    """

    def test_patterns_still_match_their_canaries(self) -> None:
        for name, pattern in IDENTIFIER_PATTERNS.items():
            self.assertTrue(pattern.search(CANARY_SAMPLES[name]), name)

    def test_no_local_username_in_config_files(self) -> None:
        username = Path.home().name
        findings = []
        for base in ("applied", "etc"):
            for path in sorted((SNAPSHOT / base).rglob("*")):
                if not path.is_file():
                    continue
                text = path.read_bytes().decode("utf-8", "replace")
                if re.search(rf"\b{re.escape(username)}\b", text):
                    findings.append(str(path.relative_to(SNAPSHOT)))
        self.assertEqual(findings, [])

    def test_no_raw_identifier_shapes_in_config_files(self) -> None:
        findings: list[str] = []
        scanned = 0
        for base in ("applied", "etc"):
            for path in sorted((SNAPSHOT / base).rglob("*")):
                if not path.is_file():
                    continue
                scanned += 1
                rel = str(path.relative_to(SNAPSHOT))
                text = path.read_bytes().decode("utf-8", "replace")
                allowed = ALLOWED_IDENTIFIER_SHAPES.get(rel, {})
                for name, pattern in IDENTIFIER_PATTERNS.items():
                    for match in pattern.finditer(text):
                        if match.group(0).lower() in allowed:
                            continue
                        line = text.count("\n", 0, match.start()) + 1
                        findings.append(f"{rel}:{line}: {name}: {match.group(0)!r}")
        self.assertGreater(scanned, 100, "scan surface shrank unexpectedly")
        self.assertEqual(
            findings,
            [],
            "raw identifier shapes reached the committed snapshot:\n"
            + "\n".join(findings),
        )


if __name__ == "__main__":
    unittest.main()
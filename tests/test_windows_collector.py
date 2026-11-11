#!/usr/bin/env python3
"""Schema and file tests for the Windows collector sources.

These tests run on Linux CI. They do not capture a real Windows machine.
A synthetic xsnapshot/v1 folder is validated with the existing collector
validator so a Windows capture remains importable by the website.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.xsnapshot import SCHEMA, _validate_snapshot  # noqa: E402


WINDOWS_FILES = (
    "bin/xsnapshot.ps1",
    "lib/XSnapshot.ps1",
    "install.ps1",
    "docs/WINDOWS.md",
)


def _write(path: Path, text: str) -> bytes:
    body = (text.rstrip() + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return body


def _sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _artifact(rel: str, body: bytes) -> dict:
    return {"path": rel, "bytes": len(body), "sha256": _sha(body)}


class WindowsCollectorSourcesTest(unittest.TestCase):
    def test_windows_sources_are_present(self) -> None:
        for rel in WINDOWS_FILES:
            path = ROOT / rel
            self.assertTrue(path.is_file(), rel)
            self.assertGreater(path.stat().st_size, 100)

    def test_install_pin_is_fail_closed_until_a_tag_exists(self) -> None:
        text = (ROOT / "install.ps1").read_text(encoding="utf-8")
        self.assertIn("$CollectorTag = ''", text)
        self.assertIn("$CollectorCommit = ''", text)
        self.assertIn("https://github.com/VeigaPunk/xsnapshot-pc.git", text)
        self.assertIn("verified tagged Windows collector release has not been pinned", text)
        self.assertNotRegex(text, r"\$CollectorCommit = '[0-9a-f]{40}'")

    def test_docs_describe_schema_and_package_lists(self) -> None:
        text = (ROOT / "docs/WINDOWS.md").read_text(encoding="utf-8")
        self.assertIn("xsnapshot/v1", text)
        self.assertIn("packages.all", text)
        self.assertIn("winget", text)
        self.assertIn("Get-AppxPackage", text)
        self.assertIn("ARTIFACTS.sha256", text)
        self.assertIn("allow-list", text.lower())

    def test_library_declares_windows_collector_version(self) -> None:
        text = (ROOT / "lib/XSnapshot.ps1").read_text(encoding="utf-8")
        self.assertIn("xsnapshot/v1", text)
        self.assertIn("1.2.0-windows", text)
        self.assertIn("function Invoke-XsnapshotCollect", text)
        self.assertIn("function Invoke-XsnapshotValidate", text)
        self.assertIn("Get-AppxPackage", text)
        self.assertIn("Win32_Service", text)


class WindowsSyntheticSnapshotTest(unittest.TestCase):
    def test_validator_accepts_a_windows_shaped_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            snap = Path(raw) / "2026-11-11-before-claude-onboarder"
            files: dict[str, bytes] = {}
            files["system/identity.txt"] = _write(snap / "system/identity.txt", "hostname=TESTBOX\nos=Windows 11")
            files["packages/uninstall.txt"] = _write(snap / "packages/uninstall.txt", "Example App 1.0 (Example Inc)")
            files["etc/hosts"] = _write(snap / "etc/hosts", "127.0.0.1 localhost\n")
            report_body = None
            artifacts = [_artifact(rel, body) for rel, body in sorted(files.items())]
            # REPORT.md is part of artifacts[] and of the seal.
            # Written after we know the other artifacts; then snapshot.json is
            # sealed but omitted from artifacts[].
            config_index = [
                {
                    "source": "C:\\Windows\\System32\\drivers\\etc\\hosts",
                    "path": "etc/hosts",
                    "bytes": len(files["etc/hosts"]),
                    "snapshot_sha256": _sha(files["etc/hosts"]),
                    "redactions": 0,
                }
            ]
            # Placeholder report so we can hash it after the path list exists.
            report = (
                "# Snapshot report: 2026-11-11-before-claude-onboarder\n\n"
                "> Captured **2026-11-11T12:00:00-08:00** on `TESTBOX`.\n"
            )
            files["REPORT.md"] = _write(snap / "REPORT.md", report)
            artifacts.append(_artifact("REPORT.md", files["REPORT.md"]))
            data = {
                "schema": SCHEMA,
                "snapshot_id": "2026-11-11-before-claude-onboarder",
                "captured_at": "2026-11-11T12:00:00-08:00",
                "collector": {
                    "name": "xsnapshot-pc",
                    "version": "1.2.0-windows",
                    "powershell": "5.1.0",
                    "platform": "windows",
                },
                "host": {
                    "hostname": "TESTBOX",
                    "chassis": "desktop",
                    "machine": "Example Board",
                    "kernel": "10.0.26100",
                    "architecture": "AMD64",
                    "os": "Microsoft Windows 11 Pro",
                    "os_id": "windows",
                    "os_version": "24H2",
                },
                "os": {
                    "name": "Microsoft Windows",
                    "pretty_name": "Microsoft Windows 11 Pro",
                    "id": "windows",
                    "build_id": "26100.1",
                    "home_url": "https://www.microsoft.com/windows",
                    "documentation_url": "https://learn.microsoft.com/windows",
                    "kernel": "10.0.26100",
                    "arch": "AMD64",
                },
                "hardware": {
                    "cpu": {"name": "Example CPU", "cores": 8, "threads": 16},
                    "memory": {"total_bytes": 17179869184, "total_human": "16.0 GiB", "modules": []},
                    "gpu": {"name": "Example GPU", "vram": "unknown", "driver": "unknown"},
                    "board": {"model": "Example Board", "version": "1.0", "bios": "1.0", "bios_date": "20260101"},
                },
                "storage": {"disks": [], "volumes": [], "df": "", "swap": None, "encryption": "omitted"},
                "desktop": {"env": "SESSIONNAME=Console", "theme": "dark", "locale": "en-US", "time": "timezone=UTC", "monitors": []},
                "packages": {
                    "all_count": 1,
                    "explicit_count": 1,
                    "foreign_count": 1,
                    "all": ["Example App 1.0 (Example Inc)"],
                    "explicit": ["Example.App Example.App 1.0 winget"],
                    "foreign": ["Example.App 1.0.0.0"],
                },
                "config_index": config_index,
                "artifacts": sorted(artifacts, key=lambda row: row["path"]),
                "privacy": {
                    "policy": "allow-list plus redaction; secrets and unique identifiers excluded",
                    "excluded": ["SSH/GPG private keys"],
                    "redactions_applied": 0,
                    "config_files_captured": 1,
                    "artifact_seal": "ARTIFACTS.sha256",
                    "local_output": "owner-only capture directories and files",
                },
            }
            json_text = json.dumps(data, indent=2) + "\n"
            json_body = json_text.encode("utf-8")
            (snap / "data").mkdir(parents=True, exist_ok=True)
            (snap / "data/snapshot.json").write_bytes(json_body)
            seal_rows = artifacts + [_artifact("data/snapshot.json", json_body)]
            lines = [f"{row['sha256']}  {row['path']}" for row in sorted(seal_rows, key=lambda r: r["path"])]
            (snap / "ARTIFACTS.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
            count, digest = _validate_snapshot(snap)
            self.assertEqual(count, len(artifacts))
            self.assertEqual(len(digest), 64)


if __name__ == "__main__":
    unittest.main()

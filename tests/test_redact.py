#!/usr/bin/env python3
"""Redaction tests for ``lib.xsnapshot.redact_text``.

Fixtures are synthetic and use documentation ranges only (RFC 5737 IPv4,
RFC 7042 MAC, example.com addresses); no real host identifiers are needed.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.xsnapshot import redact_text

UUID = "8f1c2d3e-4a5b-4c6d-8e9f-0a1b2c3d4e5f"
MACHINE_ID = "3f9a2b7c8d4e5f60a1b2c3d4e5f6a7b8"
ORG_ID = "1a2b3c4d5e6f708192a3b4c5d6e7f809"
UKI_HASH = "0123456789abcdef" * 4  # 64 hex chars, limine UKI payload digest

# One sample per required shape; reused by the combined and stability tests.
SAMPLE = "\n".join(
    [
        f"machine-id={MACHINE_ID}",
        "nameserver 192.0.2.53",
        "link/ether 00:00:5e:00:53:0a brd ff:ff:ff:ff:ff:ff",
        "maintainer: ops@example.com",
        '{"disk_uuid": "%s"}' % UUID,
        f"organization: org-{ORG_ID}",
        "#Environment=GLM_LEG2_KEY=9c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f.kq7x2p",
        '{"password": "literal"}',
        f"path: boot():/EFI/Linux/omarchy_linux.efi#{UKI_HASH}",
    ]
)

SAMPLE_RAW = (
    MACHINE_ID,
    "192.0.2.53",
    "00:00:5e:00:53:0a",
    "ops@example.com",
    UUID,
    f"org-{ORG_ID}",
    "9c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f",
    '"literal"',
    UKI_HASH,
)

SAMPLE_MARKERS = (
    "machine-id=<redacted>",
    "<ip>",
    "<mac>",
    "<email>",
    "<uuid>",
    "org-<redacted>",
    "#Environment=GLM_LEG2_KEY=<redacted>",
    '"<redacted>"',
    "#<redacted-hash>",
)


class RedactIdentifierShapesTest(unittest.TestCase):
    """Each unique-identifier shape must be replaced."""

    def test_uuid_shape_is_redacted(self) -> None:
        out, count = redact_text('{"disk_uuid": "%s"}' % UUID)
        self.assertNotIn(UUID, out)
        self.assertIn("<uuid>", out)
        self.assertGreaterEqual(count, 1)

    def test_partuuid_label_is_redacted(self) -> None:
        out, count = redact_text(f"cryptdevice=PARTUUID={UUID}:root")
        self.assertNotIn("8f1c", out)
        self.assertIn("<uuid>", out)
        self.assertGreaterEqual(count, 1)

    def test_mac_address_is_redacted(self) -> None:
        out, count = redact_text("link/ether 00:00:5e:00:53:0a brd ff:ff:ff:ff:ff:ff")
        self.assertNotIn("00:00:5e:00:53:0a", out)
        self.assertNotIn("ff:ff:ff:ff:ff:ff", out)
        self.assertIn("<mac>", out)
        self.assertGreaterEqual(count, 2)

    def test_ipv4_is_redacted(self) -> None:
        out, count = redact_text("nameserver 192.0.2.53")
        self.assertNotIn("192.0.2.53", out)
        self.assertIn("<ip>", out)
        self.assertGreaterEqual(count, 1)

    def test_email_is_redacted(self) -> None:
        out, count = redact_text("maintainer: ops@example.com")
        self.assertNotIn("ops@example.com", out)
        self.assertIn("<email>", out)
        self.assertGreaterEqual(count, 1)

    def test_machine_id_assignment_is_redacted(self) -> None:
        out, count = redact_text(f"machine-id={MACHINE_ID}")
        self.assertNotIn(MACHINE_ID, out)
        self.assertIn("machine-id=<redacted>", out)
        self.assertGreaterEqual(count, 1)

    def test_machine_id_line_is_redacted(self) -> None:
        out, count = redact_text(f"Machine ID: {MACHINE_ID}\n")
        self.assertNotIn(MACHINE_ID, out)
        self.assertIn("Machine ID: <redacted>", out)
        self.assertGreaterEqual(count, 1)

    def test_provider_org_id_is_redacted(self) -> None:
        out, count = redact_text(f"organization: org-{ORG_ID}")
        self.assertNotIn(ORG_ID, out)
        self.assertIn("org-<redacted>", out)
        self.assertGreaterEqual(count, 1)

    def test_json_org_id_value_is_redacted(self) -> None:
        out, count = redact_text('{"org_id": "%s"}' % ORG_ID)
        self.assertNotIn(ORG_ID, out)
        self.assertIn('"org_id": "<redacted>"', out)
        self.assertGreaterEqual(count, 1)

    def test_environment_key_assignment_is_redacted(self) -> None:
        out, count = redact_text(
            "#Environment=GLM_LEG2_KEY=9c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f.kq7x2p"
        )
        self.assertNotIn("9c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f", out)
        self.assertIn("#Environment=GLM_LEG2_KEY=<redacted>", out)
        self.assertGreaterEqual(count, 1)

    def test_json_password_value_is_redacted(self) -> None:
        out, count = redact_text('{"password": "literal"}')
        self.assertNotIn('"literal"', out)
        self.assertIn('"<redacted>"', out)
        self.assertGreaterEqual(count, 1)

    def test_limine_uki_hash_is_redacted(self) -> None:
        out, count = redact_text(
            f"path: boot():/EFI/Linux/omarchy_linux.efi#{UKI_HASH}"
        )
        self.assertNotIn(UKI_HASH, out)
        self.assertIn("#<redacted-hash>", out)
        self.assertGreaterEqual(count, 1)


class RedactIntegrationTest(unittest.TestCase):
    """Combined-behavior checks over one multi-shape sample."""

    def test_sample_redacts_every_shape(self) -> None:
        out, count = redact_text(SAMPLE)
        for raw in SAMPLE_RAW:
            self.assertNotIn(raw, out)
        for marker in SAMPLE_MARKERS:
            self.assertIn(marker, out)
        self.assertGreaterEqual(count, len(SAMPLE_RAW))

    def test_sample_output_is_stable(self) -> None:
        """Re-redacting the output must not change bytes; placeholder lines may
        be re-counted, so only the text is asserted."""
        out, _ = redact_text(SAMPLE)
        again, _ = redact_text(out)
        self.assertEqual(again, out)


class PreserveInnocuousTextTest(unittest.TestCase):
    """Harmless text must survive untouched."""

    def test_package_version_strings_are_preserved(self) -> None:
        text = "\n".join(
            [
                "linux 7.2.3.arch1-3",
                "hyprland 0.56.2-1",
                "wine 10.0rc4-1",
                "docker 29.7.2-1",
            ]
        )
        out, count = redact_text(text)
        self.assertEqual(out, text)
        self.assertEqual(count, 0)

    def test_shell_command_substitution_is_preserved(self) -> None:
        text = 'OPENAI_CODEX_TOKEN="$(helper)"'
        out, count = redact_text(text)
        self.assertEqual(out, text)
        self.assertEqual(count, 0)

    def test_sudoers_nopasswd_command_is_preserved(self) -> None:
        text = "%wheel ALL=(root) NOPASSWD: /usr/bin/asdcontrol ^--detect$"
        out, count = redact_text(text)
        self.assertIn("NOPASSWD: /usr/bin/asdcontrol", out)
        self.assertEqual(count, 0)

    def test_token_helper_path_is_preserved(self) -> None:
        text = "Environment=SHIM_TOKEN_CMD=/home/user/.local/bin/token-helper"
        out, count = redact_text(text)
        self.assertEqual(out, text)
        self.assertEqual(count, 0)

    def test_ipv6_is_redacted(self) -> None:
        text = "DNS Servers: 2804:14d:1:0:181:213:132:3\n          2606:4700:4700::1111"
        out, count = redact_text(text)
        self.assertNotIn("2804:14d", out)
        self.assertNotIn("2606:4700", out)
        self.assertGreaterEqual(count, 2)

    def test_clock_time_is_not_ipv6(self) -> None:
        text = "last run 00:57:51"
        out, count = redact_text(text)
        self.assertEqual(out, text)
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
#!/usr/bin/env python3
"""xsnapshot-pc: reproducible, sanitized workstation snapshot collector.

The collector is intentionally dependency-free (Python 3 standard library) and
Linux-first.  It writes a single snapshot directory containing:

  applied/       allow-listed user configuration files, redacted
  etc/           allow-listed system configuration files, redacted
  packages/      exact package inventories
  system/        command output grouped by subsystem
  data/          machine-readable snapshot.json
  REPORT.md      capture manifest, coverage, privacy and artifact index

Nothing is uploaded.  The output is designed to be reviewable before commit.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import hashlib
import ipaddress
import json
import os
import platform
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "xsnapshot/v1"
REPO_ROOT = Path(__file__).resolve().parent.parent
HOME = Path.home()
USERNAME = HOME.name

# ---------------------------------------------------------------------------
# Sanitization
# ---------------------------------------------------------------------------

UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
MAC_RE = re.compile(r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b")
IPV4_RE = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
BRACKET_IPV6_RE = re.compile(r"\[[0-9A-Fa-f]*:[0-9A-Fa-f:]*:[0-9A-Fa-f:.]*\]")
IPV6_TOKEN_RE = re.compile(
    r"(?<![\w:])(?:[0-9A-Fa-f]{0,4}:){2,}[0-9A-Fa-f]{0,4}"
    r"(?:%[A-Za-z0-9_.-]+)?(?![\w:])"
)
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}")
JSON_SECRET_RE = re.compile(
    r'(?i)("(?:password|passwd|secret|token|api[_-]?key|access[_-]?key|'
    r'refresh[_-]?token|client[_-]?secret|private[_-]?key|auth[_-]?token|'
    r'org_id)"\s*:\s*")[^"]{4,}(")'
)
KV_SECRET_RE = re.compile(
    r"(?im)^(\s*(?:password|passwd|secret|token|api[_-]?key|access[_-]?key|"
    r"refresh[_-]?token|client[_-]?secret|private[_-]?key|auth[_-]?token)"
    r"\s*[:=]\s*)([\"']?)(?!\$)([A-Za-z0-9._~+/=-]{16,})\2\s*$"
)
ENV_SECRET_RE = re.compile(
    r"(?i)(\b[A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|API_KEY|ACCESS_KEY|"
    r"PRIVATE_KEY|AUTH_KEY)\b\s*=\s*)([\"']?)(?!\$)"
    r"([A-Za-z0-9._~+/=-]{16,})\2"
)
DMI_SERIAL_RE = re.compile(r"(?im)^(\s*Serial Number:\s*)(?!To be filled)(.+)$")
DMI_UUID_RE = re.compile(r"(?im)^(\s*UUID:\s*)(.+)$")
PIPEWIRE_COOKIE_RE = re.compile(r"(?i)(cookie:)\d+")
LIMINE_HASH_RE = re.compile(r"(?m)(#)[0-9a-f]{64,}\b")
ORG_ID_RE = re.compile(r"\borg-[0-9a-f]{16,}\b")
IPV6_LOOPBACK_RE = re.compile(r"(?<![\w:])(?:::1|::)(?![\w:])")
SECRETISH_ASSIGN_RE = re.compile(
    r"(?im)(\b[A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|"
    r"ACCESS_KEY|PRIVATE_KEY|AUTH_KEY|_KEY)\b"
    r"\s*[:=]\s*)([\"']?)(?!\$)([A-Za-z0-9._~+/=-]{12,})\2"
)
SERIAL_LINE_RE = re.compile(r"(?im)^(\s*serial:\s*).+$")
UKI_PATH_RE = re.compile(r"(?m)(#)[0-9a-f]{64,}")


def redact_identity(text: str) -> tuple[str, int]:
    """Replace the local account name and home path in published text."""
    n = 0
    home = str(HOME)
    if home in text:
        text = text.replace(home, "/home/user")
        n += 1
    if USERNAME in text:
        n += text.count(USERNAME)
        text = text.replace(USERNAME, "user")
    return text, n


def redact_text(text: str, *, protect_versions: bool = False,
                protect_systemd_units: bool = False) -> tuple[str, int]:
    """Redact common secret and unique-identifier shapes.

    This is a best-effort defense.  The stronger control is the allow-list in
    ``copy_file``; only reviewed files are copied.
    """

    n = 0
    protected: dict[str, str] = {}

    def protect(pattern: re.Pattern[str], value: str, label: str) -> str:
        def repl(match: re.Match[str]) -> str:
            key = f"__XS_{label}_{len(protected)}__"
            protected[key] = match.group(0)
            return key
        return pattern.sub(repl, value)

    s = text
    if protect_versions:
        s = protect(re.compile(r"\b\d+\.\d+\.\d+(?:\.\d+)?\b"), s, "VER")
    if protect_systemd_units:
        s = protect(
            re.compile(
                r"\b[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+\."
                r"(?:service|timer|socket|target|path|mount|automount|slice|scope)\b"
            ),
            s,
            "UNIT",
        )
    # sudoers NOPASSWD is a keyword, not a password value.
    s = protect(re.compile(r"\bNOPASSWD\b"), s, "KW")

    def sub(pattern: re.Pattern[str], repl: str, value: str) -> str:
        nonlocal n
        new, count = pattern.subn(repl, value)
        n += count
        return new
    s = sub(
        re.compile(r"(?im)^(\s*(?:Machine ID|Boot ID|machine-id|boot-id)\s*[:=]\s*)[0-9a-f]{16,}\s*$"),
        r"\1<redacted>",
        s,
    )
    s = sub(re.compile(r"(?i)(machine-id=)[0-9a-f]{16,}"), r"\1<redacted>", s)
    s = sub(re.compile(r"(?i)(PARTUUID=)[0-9A-Fa-f-]{4,}"), r"\1<uuid>", s)
    s = sub(re.compile(r"(?i)(UUID=)[0-9A-Fa-f-]{4,}"), r"\1<uuid>", s)
    s = sub(UUID_RE, "<uuid>", s)
    s = sub(MAC_RE, "<mac>", s)
    s = sub(IPV4_RE, "<ip>", s)
    s = sub(IPV6_LOOPBACK_RE, "<ipv6>", s)
    s = sub(BRACKET_IPV6_RE, "<ipv6>", s)

    ipv6_count = 0

    def ipv6_repl(match: re.Match[str]) -> str:
        nonlocal ipv6_count
        token = match.group(0)
        try:
            ipaddress.IPv6Address(token.split("%", 1)[0])
        except ValueError:
            return token
        ipv6_count += 1
        return "<ipv6>"

    s = IPV6_TOKEN_RE.sub(ipv6_repl, s)
    n += ipv6_count
    s = sub(EMAIL_RE, "<email>", s)
    s = sub(BEARER_RE, "Bearer <redacted>", s)
    s = sub(JSON_SECRET_RE, r"\1<redacted>\2", s)
    s = sub(KV_SECRET_RE, r"\1\2<redacted>\2", s)
    s = sub(ENV_SECRET_RE, r"\1\2<redacted>\2", s)
    s = sub(SECRETISH_ASSIGN_RE, r"\1\2<redacted>\2", s)
    s = sub(DMI_SERIAL_RE, r"\1<redacted>", s)
    s = sub(DMI_UUID_RE, r"\1<redacted>", s)
    s = sub(PIPEWIRE_COOKIE_RE, r"\1<redacted>", s)
    s = sub(UKI_PATH_RE, r"\1<redacted-hash>", s)
    s = sub(ORG_ID_RE, "org-<redacted>", s)
    s = sub(SERIAL_LINE_RE, r"\1<redacted>", s)
    # systemd-boot / bootctl may print PARTUUID paths with a different label.
    s = sub(re.compile(r"(?i)(/dev/disk/by-partuuid/)[0-9a-f-]{16,}"), r"\1<uuid>", s)
    s = sub(re.compile(r"(?i)(by-uuid/)[0-9a-f-]{16,}"), r"\1<uuid>", s)
    s, identity_count = redact_identity(s)
    n += identity_count
    for key, original in protected.items():
        s = s.replace(key, original)
    return s, n


def redact_network(text: str) -> str:
    """Redact addresses in network command output without mangling timestamps."""

    s, _ = redact_text(text)
    s = re.sub(r"(?im)^(\s*(?:Current DNS Server|DNS Servers?|Fallback DNS Servers?|"
               r"Gateway|address|inet6?|MAC Address)\s*[:=]?\s*).*$",
               r"\1<redacted>", s)
    s = re.sub(r"(?i)(via\s+)(?:[0-9A-Fa-f:.%]+)", r"\1<gateway>", s)
    s = re.sub(r"(?i)(src\s+)(?:[0-9A-Fa-f:.%]+)", r"\1<source>", s)
    return s


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def shquote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


MAX_CONFIG_BYTES = 1024 * 1024


def _open_config_directory(path: Path) -> int:
    """Pin a directory without following any component's symlink."""
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("unsupported config path")
    flags = os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open("/", flags)
    try:
        for name in path.parts[1:]:
            child = os.open(name, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_config_text(path: Path, limit: int = MAX_CONFIG_BYTES) -> str:
    """Bounded regular UTF-8 text; no symlink traversal or privileged fallback."""
    if not 0 < limit <= MAX_CONFIG_BYTES:
        raise ValueError("unsupported config size limit")
    descriptors = [_open_config_directory(path.parent)]
    try:
        pinned = os.open(path.name, os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC,
                         dir_fd=descriptors[0])
        descriptors.append(pinned)
        before = os.fstat(pinned)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError("config is not a single regular file")
        if before.st_size > limit:
            raise ValueError("config exceeds size limit")
        readable = os.open(f"/proc/self/fd/{pinned}", os.O_RDONLY | os.O_CLOEXEC)
        descriptors.append(readable)
        opened = os.fstat(readable)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError("config changed while opening")
        chunks, length = [], 0
        while length <= limit:
            chunk = os.read(readable, min(65536, limit + 1 - length))
            if not chunk:
                break
            chunks.append(chunk)
            length += len(chunk)
        after = os.fstat(readable)
        stamp = lambda info: (info.st_dev, info.st_ino, info.st_size,
                              info.st_mtime_ns, info.st_ctime_ns)
        if length > limit:
            raise ValueError("config exceeds size limit")
        if stamp(before) != stamp(after) or length != after.st_size:
            raise ValueError("config changed while reading")
        raw = b"".join(chunks)
        if b"\x00" in raw:
            raise ValueError("config contains binary data")
        return raw.decode("utf-8", errors="strict")
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def parse_os_release(path: Path = Path("/etc/os-release")) -> dict[str, str]:
    data: dict[str, str] = {}
    try:
        for line in read_config_text(path).splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, _, value = line.partition("=")
            data[key] = value.strip().strip('"').strip("'")
    except (OSError, ValueError):
        if path == Path("/etc/os-release"):
            return parse_os_release(Path("/usr/lib/os-release"))
    return data


def human_bytes(value: int) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{value} B"


def first_nonempty(text: str, default: str = "unknown") -> str:
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("["):
            return line
    return default


def md_table(headers: list[str], rows: Iterable[Iterable[Any]]) -> str:
    rows = [list(map(str, row)) for row in rows]
    if not rows:
        return "_none observed_"
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    out = ["| " + " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers)) + " |"]
    out.append("|" + "|".join("-" * (w + 2) for w in widths) + "|")
    for row in rows:
        out.append("| " + " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)) + " |")
    return "\n".join(out)


def package_version(packages: list[str], name: str) -> str:
    for item in packages:
        if item == name or item.startswith(name + " "):
            return item
    return f"{name} (not installed)"


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------

class Collector:
    def __init__(self, root: Path, out: Path, sudo: bool = True) -> None:
        self.root = root
        self.out = out
        self.use_sudo = sudo and os.geteuid() != 0
        self.data: dict[str, Any] = {
            "schema": SCHEMA,
            "snapshot_id": out.name,
            "captured_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "collector": {
                "name": "xsnapshot-pc",
                "version": "1.0.0",
                "python": platform.python_version(),
            },
        }
        self.artifacts: list[dict[str, Any]] = []
        self.config_index: list[dict[str, Any]] = []
        self.notes: list[str] = []
        self.redaction_total = 0
        self.commands: list[dict[str, Any]] = []
        self.packages: dict[str, Any] = {}
        self._output_identity: tuple[int, int] | None = None

    # -- command execution -------------------------------------------------
    def run(self, cmd: str, timeout: int = 30) -> str:
        # Inventory programs still use the operator's PATH/configuration, but
        # the shell parsing these fixed commands must not import startup code.
        excluded = {"BASH_ENV", "ENV", "SHELLOPTS", "BASHOPTS", "CDPATH", "GLOBIGNORE"}
        env = {key: value for key, value in os.environ.items()
               if key not in excluded and not key.startswith("BASH_FUNC_")}
        env.update({"LC_ALL": "C", "LANG": "C", "TERM": "dumb"})
        started = dt.datetime.now().isoformat(timespec="seconds")
        try:
            proc = subprocess.run(
                ["/bin/bash", "--noprofile", "--norc", "-c", cmd],
                shell=False,
                text=True,
                capture_output=True,
                timeout=timeout,
                env=env,
            )
            stdout = proc.stdout.rstrip()
            stderr = proc.stderr.rstrip()
            record = {
                "command": cmd,
                "started_at": started,
                "returncode": proc.returncode,
                "stdout_bytes": len(stdout.encode()),
                "stderr_bytes": len(stderr.encode()),
            }
            self.commands.append(record)
            if proc.returncode != 0:
                suffix = f"[exit {proc.returncode}"
                if stderr:
                    suffix += f": {stderr.splitlines()[-1][:200]}"
                suffix += "]"
                return (stdout + ("\n" if stdout else "") + suffix).strip()
            return stdout
        except subprocess.TimeoutExpired:
            self.commands.append({"command": cmd, "started_at": started, "returncode": "timeout"})
            return f"[unavailable: timeout after {timeout}s]"
        except Exception as exc:  # noqa: BLE001 - collector must continue
            self.commands.append({"command": cmd, "started_at": started, "returncode": "error"})
            return f"[unavailable: {exc}]"

    def sudo_run(self, cmd: str, timeout: int = 30) -> str:
        if os.geteuid() == 0:
            return self.run(cmd, timeout=timeout)
        if not self.use_sudo:
            return "[unavailable: root required]"
        return self.run("sudo -n " + cmd, timeout=timeout)

    # -- private output ----------------------------------------------------
    @staticmethod
    def _check_private_directory(fd: int) -> os.stat_result:
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise PermissionError("capture directory must be owned by this user with no group/other access")
        return info

    def _open_private_output(self) -> int:
        self.out.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.out.mkdir(mode=0o700)
        except FileExistsError:
            pass
        fd = os.open(self.out, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            info = self._check_private_directory(fd)
            identity = (info.st_dev, info.st_ino)
            if self._output_identity is not None and self._output_identity != identity:
                raise OSError("capture directory changed during collection")
            self._output_identity = identity
            return fd
        except BaseException:
            os.close(fd)
            raise

    def _write_private_file(self, rel: str, body: bytes) -> Path:
        parts = Path(_snapshot_path(rel)).parts
        fd = self._open_private_output()
        try:
            for name in parts[:-1]:
                try:
                    os.mkdir(name, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
                try:
                    self._check_private_directory(child)
                except BaseException:
                    os.close(child)
                    raise
                os.close(fd)
                fd = child
            # Exclusive creation rejects existing regular files, hard links,
            # symlinks and special files rather than truncating their targets.
            output = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                             0o600, dir_fd=fd)
            with os.fdopen(output, "wb") as stream:
                stream.write(body)
        finally:
            os.close(fd)
        return self.out / rel

    def write(self, rel: str, text: str, *, sanitize: bool = False) -> Path:
        if sanitize:
            text, redactions = redact_text(text)
            self.redaction_total += redactions
        body = (text.rstrip() + "\n").encode("utf-8")
        dest = self._write_private_file(rel, body)
        self.artifacts.append({
            "path": rel, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
        })
        return dest

    def write_section(
        self,
        rel: str,
        sections: list[tuple[str, str]],
        *,
        protect_versions: bool = False,
        protect_systemd_units: bool = False,
    ) -> None:
        chunks = []
        for title, body in sections:
            chunks.append(f"## {title}\n\n{body.rstrip()}\n")
        text, redactions = redact_text(
            "\n".join(chunks),
            protect_versions=protect_versions,
            protect_systemd_units=protect_systemd_units,
        )
        self.redaction_total += redactions
        self.write(rel, text, sanitize=False)

    def copy_file(
        self,
        src: str | Path,
        rel: str,
        *,
        missing_ok: bool = True,
        follow_symlinks: bool = False,
    ) -> Path | None:
        srcp = Path(os.path.expanduser(str(src)))
        # Only the standard vendor os-release alias has a fixed safe destination.
        source = srcp
        if follow_symlinks and srcp == Path("/etc/os-release"):
            try:
                if os.readlink(srcp) in ("../usr/lib/os-release", "/usr/lib/os-release"):
                    source = Path("/usr/lib/os-release")
            except OSError:
                pass
        try:
            text = read_config_text(source)
        except FileNotFoundError:
            if not missing_ok:
                self.notes.append(f"missing required config: {rel}")
            return None
        except (OSError, ValueError):
            # No target paths, raw OS diagnostics or privileged retry.
            self.notes.append(f"config omitted (unreadable, linked, oversized or non-text): {rel}")
            return None
        text, redactions = redact_text(text)
        body = (text.rstrip() + "\n").encode("utf-8")
        dest = self._write_private_file(rel, body)
        source_display = str(srcp).replace(str(HOME), "~", 1)
        source_display, _ = redact_identity(source_display)
        entry = {
            "source": source_display,
            "path": rel,
            "bytes": len(body),
            "snapshot_sha256": hashlib.sha256(body).hexdigest(),
            "redactions": redactions,
        }
        self.config_index.append(entry)
        self.redaction_total += redactions
        self.artifacts.append({
            "path": rel,
            "bytes": entry["bytes"],
            "sha256": entry["snapshot_sha256"],
        })
        return dest

    def copy_tree(
        self,
        src: Path,
        dest_prefix: str,
        *,
        include_suffixes: tuple[str, ...] | None = None,
        exclude_globs: tuple[str, ...] = (),
        exclude_dirs: tuple[str, ...] = (".git", "node_modules", "__pycache__", ".cache"),
    ) -> int:
        count = 0
        try:
            directory = _open_config_directory(src)
            os.close(directory)
        except FileNotFoundError:
            return 0
        except (OSError, ValueError):
            self.notes.append(f"config tree omitted (unreadable or linked): {dest_prefix}")
            return 0
        for visited, item in enumerate(src.rglob("*"), 1):
            if visited > 8192:
                self.notes.append(f"config tree entry limit reached: {dest_prefix}")
                break
            if len(item.relative_to(src).parts) > 32:
                continue
            if item.is_symlink() or not item.is_file():
                continue
            if any(part in exclude_dirs for part in item.parts):
                continue
            rel_name = item.relative_to(src).as_posix()
            if any(fnmatch.fnmatch(rel_name, pat) for pat in exclude_globs):
                continue
            if include_suffixes and item.suffix.lower() not in include_suffixes:
                continue
            dest_rel = f"{dest_prefix}/{rel_name}" if rel_name != "." else dest_prefix
            if self.copy_file(item, dest_rel) is not None:
                count += 1
        return count

    # -- identity / hardware ----------------------------------------------
    def collect_identity(self) -> None:
        osr = parse_os_release()
        hostnamectl = self.run("hostnamectl")
        self.data["host"] = {
            "hostname": socket.gethostname(),
            "chassis": "desktop" if "Chassis: desktop" in hostnamectl else "unknown",
            "machine": first_nonempty(hostnamectl),
            "kernel": platform.release(),
            "architecture": platform.machine(),
            "os": osr.get("PRETTY_NAME", osr.get("NAME", "unknown")),
            "os_id": osr.get("ID", "unknown"),
            "os_version": osr.get("VERSION_ID", "rolling"),
        }
        self.data["os"] = {
            "name": osr.get("NAME", "unknown"),
            "pretty_name": osr.get("PRETTY_NAME", "unknown"),
            "id": osr.get("ID", "unknown"),
            "build_id": osr.get("BUILD_ID", ""),
            "home_url": osr.get("HOME_URL", ""),
            "documentation_url": osr.get("DOCUMENTATION_URL", ""),
            "kernel": platform.release(),
            "arch": platform.machine(),
        }
        omarchy_version = self.run("omarchy-version 2>/dev/null || true")
        self.data["omarchy"] = {
            "version": first_nonempty(omarchy_version, "not installed"),
            "branch": first_nonempty(self.run("omarchy-version-branch 2>/dev/null || true"), ""),
            "channel": first_nonempty(self.run("omarchy-version-channel 2>/dev/null || true"), ""),
            "last_package_update": first_nonempty(self.run("omarchy-version-pkgs 2>/dev/null || true"), ""),
        }

    def collect_hardware(self) -> None:
        lscpu = self.run("lscpu")
        cpu_model = "unknown"
        for line in lscpu.splitlines():
            if line.startswith("Model name:"):
                cpu_model = line.split(":", 1)[1].strip()
                break
        cpu = {
            "model": cpu_model,
            "sockets": "unknown",
            "cores": "unknown",
            "threads": "unknown",
            "max_mhz": "unknown",
            "min_mhz": "unknown",
            "microcode": "unknown",
            "virtualization": "unknown",
        }
        for line in lscpu.splitlines():
            if ":" not in line:
                continue
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if not val:
                continue
            if key == "CPU(s)":
                if re.fullmatch(r"[1-9][0-9]{0,7}", val):
                    cpu["threads"] = val
            elif key == "Core(s) per socket":
                if re.fullmatch(r"[1-9][0-9]{0,7}", val):
                    cpu["cores"] = f"{val} per socket"
            elif key == "Socket(s)":
                if re.fullmatch(r"[1-9][0-9]{0,7}", val):
                    cpu["sockets"] = val
            elif key in ("CPU max MHz", "CPU min MHz"):
                if re.fullmatch(r"[0-9]{1,9}(?:\.[0-9]{1,9})?", val) and float(val) > 0:
                    cpu["max_mhz" if key == "CPU max MHz" else "min_mhz"] = f"{float(val):.3f}"
            elif key == "Microcode version":
                cpu["microcode"] = val
            elif key == "Virtualization":
                cpu["virtualization"] = val
        mem = self.run("free -b")
        mem_total = mem_used = mem_avail = None
        for line in mem.splitlines():
            if line.startswith("Mem:"):
                parts = line.split()
                if len(parts) >= 7 and re.fullmatch(r"[0-9]{1,16}", parts[1]):
                    total = int(parts[1])
                    if 0 < total <= (1 << 53) - 1:
                        mem_total = total
                        if re.fullmatch(r"[0-9]{1,16}", parts[2]) and int(parts[2]) <= total:
                            mem_used = int(parts[2])
                        if re.fullmatch(r"[0-9]{1,16}", parts[6]) and int(parts[6]) <= total:
                            mem_avail = int(parts[6])
                break
        gpu = self.run(
            "nvidia-smi --query-gpu=name,memory.total,driver_version,power.limit "
            "--format=csv,noheader 2>/dev/null || true"
        )
        gpu_name = gpu_mem = gpu_driver = gpu_power = "unknown"
        if gpu and "," in gpu:
            bits = [bit.strip() for bit in gpu.splitlines()[0].split(",")]
            if len(bits) >= 4:
                gpu_name, gpu_mem, gpu_driver, gpu_power = bits[:4]
        dmidecode = self.sudo_run(
            "dmidecode -t system -t baseboard -t bios -t memory 2>/dev/null || true"
        )
        dmidecode, redactions = redact_text(dmidecode)
        self.redaction_total += redactions
        memory_dmi = self.sudo_run("dmidecode -t memory 2>/dev/null || true")
        memory_dmi, redactions = redact_text(memory_dmi)
        self.redaction_total += redactions
        dimm_lines = [
            line.strip()
            for line in memory_dmi.splitlines()
            if re.match(r"^\s*(Size|Locator|Bank Locator|Type|Speed|Configured Memory Speed|"
                        r"Manufacturer|Part Number|Rank|Volatile Size):", line)
        ]
        # Use dmidecode -s for unambiguous section values.  The full dump is
        # still captured below for review.
        board = self.sudo_run("dmidecode -s baseboard-product-name 2>/dev/null || true").strip() or "unknown"
        board_version = self.sudo_run("dmidecode -s baseboard-version 2>/dev/null || true").strip() or "unknown"
        bios = self.sudo_run("dmidecode -s bios-version 2>/dev/null || true").strip() or "unknown"
        bios_date = self.sudo_run("dmidecode -s bios-release-date 2>/dev/null || true").strip() or "unknown"
        system_product = self.sudo_run("dmidecode -s system-product-name 2>/dev/null || true").strip() or "unknown"
        self.data["hardware"] = {
            "cpu": cpu,
            "memory": {
                "total_bytes": mem_total,
                "used_bytes": mem_used,
                "available_bytes": mem_avail,
                "total_human": human_bytes(mem_total) if mem_total is not None else "unknown",
                "modules": dimm_lines,
            },
            "gpu": {
                "name": gpu_name,
                "vram": gpu_mem,
                "driver": gpu_driver,
                "power_limit": gpu_power,
            },
            "board": {
                "model": board,
                "version": board_version,
                "bios": bios,
                "bios_date": bios_date,
                "system_product": system_product,
            },
            "devices": self.run("lspci -nn 2>/dev/null | sed -n '1,120p'"),
            "usb": self.run("lsusb 2>/dev/null | sed -n '1,80p'"),
        }
        self.write_section("system/hardware.txt", [
            ("lscpu", lscpu),
            ("free -h", self.run("free -h")),
            ("DMI (sanitized)", dmidecode),
            ("PCI devices", self.data["hardware"]["devices"]),
            ("USB devices", self.data["hardware"]["usb"]),
            ("NVIDIA", self.run("nvidia-smi 2>/dev/null || true")),
            ("Sensors", self.run("sensors 2>/dev/null || true")),
            ("Vulkan summary", self.run("vulkaninfo --summary 2>/dev/null | sed -n '1,120p' || true")),
            ("Kernel modules loaded", f"{len(self.run('lsmod').splitlines())} modules"),
        ], protect_versions=True)

    def collect_storage(self) -> None:
        lsblk = self.run(
            "lsblk -J -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS,ROTA,MODEL,TRAN 2>/dev/null"
        )
        lsblk_text = self.run(
            "lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS,ROTA,MODEL,TRAN 2>/dev/null"
        )
        lsblk_text, redactions = redact_text(lsblk_text)
        self.redaction_total += redactions
        df = self.run("df -hT -x tmpfs -x devtmpfs 2>/dev/null")
        findmnt = self.run(
            "findmnt -rno TARGET,SOURCE,FSTYPE,OPTIONS 2>/dev/null | "
            "sed -E 's#/dev/[^ ]+#<dev>#g'"
        )
        findmnt, redactions = redact_text(findmnt)
        self.redaction_total += redactions
        swap = self.run("swapon --show=NAME,TYPE,SIZE,PRIO 2>/dev/null || true")
        swap, redactions = redact_text(swap)
        self.redaction_total += redactions
        zram = self.run("zramctl 2>/dev/null || true")
        btrfs = self.run("btrfs filesystem usage / 2>/dev/null || true")
        snapper = self.run("snapper list-configs 2>/dev/null || true")
        crypt = self.sudo_run("cryptsetup status root 2>/dev/null || true")
        crypt, redactions = redact_text(crypt)
        self.redaction_total += redactions
        self.data["storage"] = {
            "lsblk_json": self._safe_json(lsblk),
            "df": df,
            "swap": swap,
            "zram": zram,
            "snapper": snapper,
            "encryption": crypt,
        }
        self.write_section("system/storage.txt", [
            ("lsblk", lsblk_text),
            ("df -hT", df),
            ("findmnt", findmnt),
            ("swapon", swap),
            ("zramctl", zram),
            ("btrfs usage", btrfs),
            ("snapper", snapper or "no snapper configurations"),
            ("LUKS root", crypt),
        ])

    @staticmethod
    def _safe_json(text: str) -> Any:
        try:
            return json.loads(text)
        except Exception:  # noqa: BLE001
            return None

    def collect_network(self) -> None:
        links = self.run("ip -brief link 2>/dev/null || true")
        links, redactions = redact_text(links)
        self.redaction_total += redactions
        routes = self.run("ip route 2>/dev/null || true")
        routes = redact_network(routes)
        ss = self.run("ss -tulpn 2>/dev/null || true")
        ss = redact_network(ss)
        dns = self.run("resolvectl status 2>/dev/null || true")
        dns = redact_network(dns)
        ufw = self.sudo_run("ufw status verbose 2>/dev/null || true")
        ufw = redact_network(ufw)
        rfkill = self.run("rfkill list 2>/dev/null || true")
        self.data["network"] = {
            "links": links,
            "routes": routes,
            "listeners": ss,
            "dns": dns,
            "firewall": ufw,
            "rfkill": rfkill,
        }
        self.write_section("system/network.txt", [
            ("Interfaces", links),
            ("Routes (sanitized)", routes),
            ("Listening sockets", ss),
            ("Resolver", dns),
            ("Firewall", ufw),
            ("rfkill", rfkill),
        ])

    def collect_services(self) -> None:
        enabled = self.run(
            "systemctl list-unit-files --state=enabled --no-pager --no-legend 2>/dev/null || true"
        )
        running = self.run(
            "systemctl list-units --type=service --state=running --no-pager --no-legend 2>/dev/null || true"
        )
        timers = self.run("systemctl list-timers --all --no-pager --no-legend 2>/dev/null || true")
        user_enabled = self.run(
            "systemctl --user list-unit-files --state=enabled --no-pager --no-legend 2>/dev/null || true"
        )
        user_running = self.run(
            "systemctl --user list-units --type=service --state=running --no-pager --no-legend 2>/dev/null || true"
        )
        failed = self.run("systemctl --failed --no-pager --no-legend 2>/dev/null || true")
        user_failed = self.run("systemctl --user --failed --no-pager --no-legend 2>/dev/null || true")
        self.data["services"] = {
            "system_enabled": enabled,
            "system_running": running,
            "timers": timers,
            "user_enabled": user_enabled,
            "user_running": user_running,
            "failed": failed,
            "user_failed": user_failed,
        }
        self.write_section("system/services.txt", [
            ("Enabled system units", enabled),
            ("Running system services", running),
            ("Timers", timers),
            ("Enabled user units", user_enabled),
            ("Running user services", user_running),
            ("Failed system units", failed or "none"),
            ("Failed user units", user_failed or "none"),
        ], protect_systemd_units=True)

    def collect_boot(self) -> None:
        bootctl = self.run("bootctl status 2>/dev/null || true")
        bootctl, redactions = redact_text(bootctl)
        self.redaction_total += redactions
        efiboot_raw = self.run("efibootmgr -v 2>/dev/null || true")
        efiboot = "\n".join(
            line for line in efiboot_raw.splitlines()
            if not line.lstrip().startswith(("dp:", "data:"))
        )
        efiboot, redactions = redact_text(efiboot)
        self.redaction_total += redactions
        secureboot = self.run("mokutil --sb-state 2>/dev/null || true")
        tpm = self.run(
            "printf 'tpm_version_major='; cat /sys/class/tpm/tpm0/tpm_version_major 2>/dev/null || echo none"
        )
        cmdline = self.run("cat /proc/cmdline 2>/dev/null || true")
        cmdline, redactions = redact_text(cmdline)
        self.redaction_total += redactions
        self.data["boot"] = {
            "bootctl": bootctl,
            "efibootmgr": efiboot,
            "secure_boot": secureboot,
            "tpm": tpm,
            "cmdline": cmdline,
        }
        self.write_section("system/boot.txt", [
            ("bootctl status", bootctl),
            ("UEFI boot entries", efiboot),
            ("Secure Boot", secureboot or "not reported"),
            ("TPM", tpm),
            ("Kernel command line (sanitized)", cmdline),
        ])

    def collect_desktop(self) -> None:
        env = self.run(
            "printf 'XDG_CURRENT_DESKTOP=%s\\nXDG_SESSION_TYPE=%s\\nDESKTOP_SESSION=%s\\n"
            "WAYLAND_DISPLAY=%s\\nGDK_SCALE=%s\\n' \"$XDG_CURRENT_DESKTOP\" \"$XDG_SESSION_TYPE\" "
            "\"$DESKTOP_SESSION\" \"$WAYLAND_DISPLAY\" \"$GDK_SCALE\""
        )
        hypr_version = self.run("hyprctl version 2>/dev/null || true")
        monitors = self.run("hyprctl monitors 2>/dev/null || true")
        serials = re.findall(r"(?im)^\s*serial:\s*(\S+)", monitors)
        for serial in serials:
            if len(serial) >= 4:
                monitors = monitors.replace(serial, "<redacted>")
        monitors, redactions = redact_text(monitors)
        self.redaction_total += redactions
        binds = self.run("hyprctl binds 2>/dev/null || true")
        binds, redactions = redact_text(binds)
        self.redaction_total += redactions
        devices = self.run("hyprctl devices 2>/dev/null || true")
        for serial in re.findall(r"(?im)^\s*serial:\s*(\S+)", devices):
            if len(serial) >= 4:
                devices = devices.replace(serial, "<redacted>")
        devices, redactions = redact_text(devices)
        self.redaction_total += redactions
        waybar = self.run("waybar --version 2>/dev/null || true")
        theme = self.run("omarchy-theme-current 2>/dev/null || true")
        if not theme:
            try:
                theme = read_config_text(HOME / ".config/omarchy/current/theme.name")
            except (OSError, ValueError):
                theme = ""
        locales = self.run("localectl status 2>/dev/null || true")
        timedate = self.run("timedatectl 2>/dev/null || true")
        fonts = self.run(
            "fc-list : family 2>/dev/null | sort -u | grep -Ei "
            "'JetBrains|Liberation|Noto|Adwaita|Font Awesome' | sed -n '1,80p' || true"
        )
        audio = self.run("wpctl status 2>/dev/null || true")
        audio, redactions = redact_text(audio)
        self.redaction_total += redactions
        self.data["desktop"] = {
            "env": env,
            "hyprland": (re.search(r"Hyprland\s+([0-9.]+)", hypr_version).group(0)
                         if re.search(r"Hyprland\s+([0-9.]+)", hypr_version) else "Hyprland"),
            "monitors": monitors,
            "bindings": binds,
            "theme": first_nonempty(theme, "unknown"),
            "waybar": first_nonempty(waybar, "unknown"),
            "locale": locales,
            "time": timedate,
            "audio": audio,
        }
        self.write_section("system/desktop.txt", [
            ("Environment", env),
            ("Hyprland version", hypr_version),
            ("Monitors (sanitized)", monitors),
            ("Hyprland bindings", binds),
            ("Input devices", devices),
            ("Waybar", waybar),
            ("Theme", theme),
            ("Locale", locales),
            ("Time", timedate),
            ("Fonts", fonts),
            ("PipeWire / WirePlumber", audio),
        ])

    def collect_dev(self) -> None:
        tools = [
            ("bash", "bash --version 2>&1 | head -n1"),
            ("git", "git --version"),
            ("gh", "gh --version 2>&1 | head -n1"),
            ("neovim", "nvim --version 2>&1 | head -n1"),
            ("tmux", "tmux -V"),
            ("docker", "docker --version"),
            ("docker-compose", "docker compose version"),
            ("node", "node --version"),
            ("npm", "npm --version"),
            ("bun", "bun --version"),
            ("deno", "deno --version 2>&1 | head -n1"),
            ("python", "python3 --version"),
            ("ruby", "ruby --version"),
            ("rustc", "rustc --version"),
            ("cargo", "cargo --version"),
            ("go", "go version"),
            ("dotnet", "dotnet --version 2>&1 | head -n1"),
            ("lua", "lua -v 2>&1 | head -n1"),
            ("luarocks", "luarocks --version 2>&1 | head -n1"),
            ("cmake", "cmake --version 2>&1 | head -n1"),
            ("make", "make --version 2>&1 | head -n1"),
            ("gcc", "gcc --version 2>&1 | head -n1"),
            ("clang", "clang --version 2>&1 | head -n1"),
            ("java", "java -version 2>&1 | head -n1"),
            ("ghidra", "test -d \"$HOME/.local/opt/ghidra_12.1.4_PUBLIC\" && echo present || echo absent"),
            ("radare2", "radare2 -v 2>&1 | head -n1"),
            ("rizin", "rizin -v 2>&1 | head -n1"),
            ("gdb", "gdb --version 2>&1 | head -n1"),
            ("apktool", "apktool --version 2>&1 | head -n1"),
            ("binwalk", "binwalk --version 2>&1 | head -n1"),
        ]
        rows = []
        for name, cmd in tools:
            out = self.run(cmd)
            rows.append((name, first_nonempty(out, "not installed")))
        npm_global, _ = redact_identity(self.run("npm ls -g --depth=0 2>/dev/null || true"))
        cargo_installed, _ = redact_identity(self.run("cargo install --list 2>/dev/null || true"))
        pip_user, _ = redact_identity(self.run("python3 -m pip list --user 2>/dev/null || true"))
        gem_local, _ = redact_identity(self.run("gem list --local 2>/dev/null || true"))
        projects = self.run(
            "find \"$HOME/Projects\" -maxdepth 1 -mindepth 1 -type d -printf '%f\\n' 2>/dev/null | sort"
        )
        manifests = self.run(
            "find \"$HOME/Projects\" -maxdepth 3 -type f \\( -name package.json -o -name Cargo.toml "
            "-o -name go.mod -o -name pyproject.toml -o -name composer.json \\) "
            "-not -path '*/node_modules/*' -not -path '*/.git/*' 2>/dev/null | sort"
        )
        self.data["dev"] = {
            "tools": dict(rows),
            "npm_global": npm_global,
            "cargo_installed": cargo_installed,
            "pip_user": pip_user,
            "gem_local": gem_local,
            "projects": projects.splitlines(),
            "manifests": manifests.splitlines(),
        }
        self.write_section("system/dev.txt", [
            ("Tool versions", md_table(["Tool", "Version"], rows)),
            ("npm global packages", npm_global),
            ("Cargo installed packages", cargo_installed or "none"),
            ("pip user packages", pip_user or "none"),
            ("Ruby gems", gem_local),
            ("Projects", projects),
            ("Project manifests", manifests),
        ], protect_versions=True)

    @staticmethod
    def _local_docker_socket() -> tuple[Path, str] | None:
        # Never resolve the active context, DOCKER_HOST or XDG_RUNTIME_DIR.
        # Only known Linux Unix transports are eligible. The final path must
        # itself be a socket, not a symlink or an ordinary file.
        candidates = (
            (Path(f"/run/user/{os.geteuid()}/docker.sock"), "rootless"),
            (Path("/var/run/docker.sock"), "system"),
        )
        for path, source in candidates:
            try:
                if stat.S_ISSOCK(path.lstat().st_mode):
                    return path, source
            except OSError:
                continue
        return None

    def _run_local_docker(self, executable: str, endpoint: Path, config: str,
                          arguments: list[str], source: str) -> tuple[str | None, str]:
        # No shell, saved Docker configuration, inherited Docker/proxy settings,
        # custom HTTP headers or user PATH wrappers. Do not elevate privileges.
        argv = [executable, "--config", config, "--host", f"unix://{endpoint}", *arguments]
        record: dict[str, Any] = {
            "command": "docker --config <empty-private-directory> --host "
                       f"<local-{source}-unix-socket> " + " ".join(arguments),
            "started_at": dt.datetime.now().isoformat(timespec="seconds"),
        }
        try:
            proc = subprocess.run(
                argv, shell=False, text=True, capture_output=True, timeout=30,
                env={"PATH": os.defpath, "HOME": config, "DOCKER_CONFIG": config,
                     "LC_ALL": "C", "LANG": "C", "TERM": "dumb"},
            )
            record.update(returncode=proc.returncode,
                          stdout_bytes=len(proc.stdout.encode()),
                          stderr_bytes=len(proc.stderr.encode()))
            if proc.returncode != 0:
                # Diagnostics may contain endpoint or authentication information.
                # Record only the exit status; never present a failure as empty.
                return None, "command_failed"
            return proc.stdout.rstrip(), "captured"
        except subprocess.TimeoutExpired:
            record["returncode"] = "timeout"
            return None, "timeout"
        except (OSError, UnicodeError):
            record["returncode"] = "error"
            return None, "command_unavailable"
        finally:
            self.commands.append(record)

    def collect_docker(self) -> None:
        fields = {
            "info": ["info", "--format", "{{json .}}"],
            "containers": ["ps", "-a", "--format", "{{.Names}} | {{.Image}} | {{.Status}}"],
            "images": ["images", "--format", "{{.Repository}}:{{.Tag}} | {{.Size}}"],
            "volumes": ["volume", "ls", "--format", "{{.Name}} | {{.Driver}}"],
            "networks": ["network", "ls", "--format", "{{.Name}} | {{.Driver}} | {{.Scope}}"],
        }
        data: dict[str, Any] = {
            "capture_status": "unavailable", "transport": "local-unix-socket-only",
            "daemon_identity_verified": False, "info": {},
            "containers": [], "images": [], "volumes": [], "networks": [],
        }
        status = {key: "not_attempted" for key in fields}
        socket_info = self._local_docker_socket()
        executable = shutil.which("docker", path=os.defpath)
        if socket_info is None:
            data["reason"] = "no_supported_local_socket"
        elif executable is None:
            data["reason"] = "system_docker_cli_unavailable"
        else:
            endpoint, source = socket_info
            data["socket_kind"] = source
            try:
                # Contexts, credentials, headers and plugins in the user's Docker
                # config are not consulted or copied. This directory is removed
                # after all five read-only commands, including on failure.
                with tempfile.TemporaryDirectory(prefix="xsnapshot-docker-") as config:
                    for key, arguments in fields.items():
                        output, status[key] = self._run_local_docker(
                            executable, endpoint, config, arguments, source)
                        if output is None:
                            continue
                        if key == "info":
                            info = self._safe_json(output)
                            if not isinstance(info, dict):
                                status[key] = "invalid_response"
                                continue
                            data["info"] = {k: info.get(k) for k in (
                                "ServerVersion", "StorageDriver", "CgroupDriver", "CgroupVersion",
                                "OperatingSystem", "Architecture", "NCPU", "MemTotal",
                                "DockerRootDir", "LiveRestoreEnabled",
                            )}
                        else:
                            data[key] = output.splitlines()
            except OSError:
                data["reason"] = "private_config_unavailable"
            captured = sum(value == "captured" for value in status.values())
            data["capture_status"] = "captured" if captured == len(fields) else (
                "partial" if captured else "unavailable")
            if data["capture_status"] != "captured" and "reason" not in data:
                data["reason"] = "inventory_incomplete"
        data["section_status"] = status
        self.data["docker"] = data
        explanation = (
            "Only a known local Unix socket is queried, without saved Docker settings or sudo. "
            "Rootless is preferred when present; failed queries never fall back to another daemon. "
            "Remote, custom and Docker Desktop contexts are omitted. A local socket is a transport, "
            "not proof the daemon runs on this PC. Unavailable sections do not mean empty inventory."
        )
        self.notes.append(f"Docker inventory: {data['capture_status']}. {explanation}")
        self.write_section("system/docker.txt", [
            ("Capture boundary", explanation),
            ("Capture status", json.dumps({key: data[key] for key in (
                "capture_status", "transport", "daemon_identity_verified", "section_status")}, indent=2)),
            ("docker info", json.dumps(data["info"], indent=2) if status["info"] == "captured" else "unavailable"),
            *[(key.title(), ("\n".join(data[key]) or "none") if status[key] == "captured"
               else "unavailable") for key in ("containers", "images", "volumes", "networks")],
        ])

    def collect_agents(self) -> None:
        def count_files(path: str, pattern: str = "*") -> int:
            root = Path(os.path.expanduser(path))
            if not root.exists():
                return 0
            return sum(1 for p in root.rglob(pattern) if p.is_file())

        omp_cfg = HOME / ".omp/agent/config.yml"
        omp_model_roles: dict[str, str] = {}
        try:
            omp_text = read_config_text(omp_cfg)
        except (OSError, ValueError):
            omp_text = ""
        if omp_text:
            in_roles = False
            for line in omp_text.splitlines():
                if line.startswith("modelRoles:"):
                    in_roles = True
                    continue
                if in_roles and line and not line.startswith(" "):
                    break
                if not in_roles:
                    continue
                m = re.match(r"^\s{2}([A-Za-z0-9_]+):\s*(@?[^\s#]+)", line)
                if m:
                    omp_model_roles[m.group(1)] = m.group(2)
        devin_cfg = HOME / ".config/devin/config.json"
        devin_data: dict[str, Any] = {}
        try:
            devin_data = json.loads(read_config_text(devin_cfg))
            if not isinstance(devin_data, dict):
                devin_data = {}
        except (OSError, ValueError):
            devin_data = {}
        self.data["agents"] = {
            "omp_agents": count_files("~/.omp/agent/agents", "*.md"),
            "omp_model_roles": omp_model_roles,
            "devin_agents": count_files("~/.config/devin/agents", "*.md"),
            "devin_theme": devin_data.get("theme_mode", "unknown"),
            "devin_model": (devin_data.get("agent") or {}).get("model", "unknown"),
            "agents_skills": count_files("~/.agents/skills", "SKILL.md"),
            "opencode_configs": [str(p.relative_to(HOME)) for p in (HOME / ".config/opencode").glob("*.json") if p.name != "service.json"],
            "codex_config": (HOME / ".codex/config.toml").exists(),
            "grok_config": (HOME / ".grok/config.toml").exists(),
            "kimi_tui_config": (HOME / ".kimi-code/tui.toml").exists(),
            "claude_settings": (HOME / ".claude/settings.json").exists(),
        }
        lines = [
            f"OMP agent definitions: {self.data['agents']['omp_agents']}",
            f"Devin agent definitions: {self.data['agents']['devin_agents']}",
            f"Agent skills with SKILL.md: {self.data['agents']['agents_skills']}",
            f"Devin theme: {self.data['agents']['devin_theme']}",
            f"Devin default model: {self.data['agents']['devin_model']}",
            "",
            "OMP model roles:",
        ]
        lines.extend(f"- {k}: {v}" for k, v in sorted(omp_model_roles.items()))
        skills_dir = HOME / ".agents/skills"
        if skills_dir.exists():
            links = []
            for item in sorted(skills_dir.iterdir()):
                if item.is_symlink():
                    links.append(f"- {item.name}: linked skill (not copied)")
            if links:
                lines.extend(["", "Agent skill symlinks:", *links])
        self.write("system/agents.txt", "\n".join(lines), sanitize=True)

    def package_query(self, command: str) -> list[str] | None:
        """Keep a failed native package query distinct from a successful empty one."""
        before = len(self.commands)
        output = self.run(command)
        if len(self.commands) <= before or self.commands[-1].get("returncode") != 0:
            return None
        return output.splitlines()

    def collect_packages(self) -> None:
        distro = self.data.get("os", {}).get("id", "")
        preferred = {"arch": "pacman", "omarchy": "pacman", "manjaro": "pacman",
                     "ubuntu": "dpkg-query", "debian": "dpkg-query", "linuxmint": "dpkg-query",
                     "fedora": "rpm", "rhel": "rpm", "centos": "rpm", "opensuse": "rpm"}.get(distro)
        candidates = [preferred] if preferred else ["pacman", "dpkg-query", "rpm"]
        available = [name for name in candidates if shutil.which(name)]
        manager = available[0] if len(available) == 1 else None
        explicit = all_pkgs = foreign = None
        if manager == "pacman":
            explicit = self.package_query("pacman -Qe")
            all_pkgs = self.package_query("pacman -Q")
            foreign = self.package_query("pacman -Qmq")
            # pacman uses exit 1 for a successful query with no foreign packages.
            if foreign is None and self.commands[-1].get("returncode") == 1:
                # Do not infer emptiness from exit 1: it can also be a query error.
                self.notes.append("Foreign package inventory unavailable; pacman returned no successful result.")
        elif manager == "dpkg-query":
            rows = self.package_query("dpkg-query -W -f='${db:Status-Status}\\t${binary:Package}\\t${Version}\\n'")
            if rows is not None:
                all_pkgs = []
                for row in rows:
                    parts = row.split("\t")
                    if len(parts) != 3 or not parts[1].strip() or (parts[0] == "installed" and not parts[2].strip()):
                        all_pkgs = None
                        break
                    if parts[0] == "installed":
                        all_pkgs.append(parts[1] + " " + parts[2])
            if all_pkgs is not None and shutil.which("apt-mark"):
                manual = self.package_query("apt-mark showmanual")
                if manual is not None:
                    names = set(manual)
                    explicit = [row for row in all_pkgs if row.split()[0] in names or row.split()[0].split(":")[0] in names]
        elif manager == "rpm":
            all_pkgs = self.package_query("rpm -qa --qf '%{NAME}.%{ARCH} %{VERSION}-%{RELEASE}\\n'")
        # Reject malformed rows instead of importing command diagnostics as packages.
        def valid(rows: list[str] | None, versioned: bool = True) -> list[str] | None:
            pattern = r"[A-Za-z0-9][A-Za-z0-9+_.:@/-]*" + (r" [^\s]+" if versioned else "")
            if rows is None or any(not re.fullmatch(pattern, row) for row in rows):
                return None
            return sorted(set(rows))
        all_pkgs, explicit, foreign = valid(all_pkgs), valid(explicit), valid(foreign, False)
        if all_pkgs is None:
            explicit = None
        if all_pkgs is None:
            self.notes.append("Installed package inventory unavailable; no zero-package claim is made.")
        npm_global, _ = redact_identity(self.run("npm ls -g --depth=0 2>/dev/null || true"))
        cargo_installed, _ = redact_identity(self.run("cargo install --list 2>/dev/null || true"))
        pip_user, _ = redact_identity(self.run("python3 -m pip list --user 2>/dev/null || true"))
        gem_local, _ = redact_identity(self.run("gem list --local 2>/dev/null || true"))
        self.packages = {"explicit": explicit, "all": all_pkgs, "foreign": foreign,
                         "npm_global": npm_global.splitlines(), "cargo_installed": cargo_installed.splitlines(),
                         "pip_user": pip_user.splitlines(), "gem_local": gem_local.splitlines()}
        prefix = "pacman" if manager == "pacman" else "system"
        for label, rows in (("explicit", explicit), ("all", all_pkgs), ("foreign", foreign)):
            self.write(f"packages/{prefix}-{label}.txt", "\n".join(rows) if rows else "(none)" if rows == [] else "(unavailable)")
        self.write("packages/npm-global.txt", npm_global or "(none)")
        self.write("packages/cargo-installed.txt", cargo_installed or "(none)")
        self.write("packages/pip-user.txt", pip_user or "(none)")
        self.write("packages/gem-local.txt", gem_local or "(none)")
        sizes = self.run("expac -H M '%m %n %v' $(pacman -Qq) 2>/dev/null | sort -rn | sed -n '1,40p' || true") if manager == "pacman" else ""
        self.write("packages/largest-installed.txt", sizes or "(unavailable)")
        self.data["packages"] = {
            "manager": manager or "unknown",
            "explicit_count": len(explicit) if explicit is not None else None,
            "all_count": len(all_pkgs) if all_pkgs is not None else None,
            "foreign_count": len(foreign) if foreign is not None else None,
            "foreign": foreign, "explicit": explicit, "all": all_pkgs, "largest": sizes.splitlines(),
        }

    # -- configuration copies ---------------------------------------------
    def collect_configs(self) -> None:
        # Shell, prompt, terminal, editor.
        simple = [
            ("~/.bashrc", "applied/.bashrc"),
            ("~/.bash_profile", "applied/.bash_profile"),
            ("~/.profile", "applied/.profile"),
            ("~/.tmux.conf", "applied/.tmux.conf"),
            ("~/.config/starship.toml", "applied/starship.toml"),
            ("~/.config/git/config", "applied/git/config"),
            ("~/.config/mise/config.toml", "applied/mise/config.toml"),
            ("~/.config/alacritty/alacritty.toml", "applied/alacritty/alacritty.toml"),
            ("~/.config/ghostty/config", "applied/ghostty/config"),
            ("~/.config/kitty/kitty.conf", "applied/kitty/kitty.conf"),
            ("~/.config/foot/foot.ini", "applied/foot/foot.ini"),
            ("~/.config/tmux/tmux.conf", "applied/tmux/tmux.conf"),
            ("~/.config/fontconfig/fonts.conf", "applied/fontconfig/fonts.conf"),
            ("~/.config/btop/btop.conf", "applied/btop/btop.conf"),
            ("~/.config/fastfetch/config.jsonc", "applied/fastfetch/config.jsonc"),
            ("~/.config/swayosd/config.toml", "applied/swayosd/config.toml"),
            ("~/.config/swayosd/style.css", "applied/swayosd/style.css"),
            ("~/.config/walker/config.toml", "applied/walker/config.toml"),
            ("~/.config/gtk-3.0/bookmarks", "applied/gtk-3.0/bookmarks"),
            ("~/.config/fcitx5/profile", "applied/fcitx5/profile"),
            ("~/.config/omarchy/current/theme.name", "applied/omarchy/theme.name"),
            ("~/.config/omarchy/branding/about.txt", "applied/omarchy/branding/about.txt"),
            ("~/.config/omarchy/branding/screensaver.txt", "applied/omarchy/branding/screensaver.txt"),
            ("~/.agents/AGENTS.md", "applied/agents/AGENTS.md"),
            ("~/.omp/agent/config.yml", "applied/omp/config.yml"),
            ("~/.config/opencode/cli.json", "applied/opencode/cli.json"),
            ("~/.config/opencode/opencode.json", "applied/opencode/opencode.json"),
            ("~/.config/devin/config.json", "applied/devin/config.json"),
            ("~/.config/devin/mcp_config.json", "applied/devin/mcp_config.json"),
            ("~/.config/devin/AGENTS.md", "applied/devin/AGENTS.md"),
            ("~/.grok/config.toml", "applied/grok/config.toml"),
            ("~/.codex/config.toml", "applied/codex/config.toml"),
            ("~/.kimi-code/tui.toml", "applied/kimi-code/tui.toml"),
            ("~/.claude/settings.json", "applied/claude/settings.json"),
            ("~/nvme1-scratch-sudoers", "applied/sudoers/nvme1-scratch-sudoers"),
        ]
        for src, rel in simple:
            self.copy_file(src, rel)
        # Record a linked theme as omitted; ordinary files are handled by the tree.
        theme_plugin = HOME / ".config/nvim/lua/plugins/theme.lua"
        if theme_plugin.is_symlink():
            self.copy_file(theme_plugin, "applied/nvim/lua/plugins/theme.lua", follow_symlinks=True)
        # A regular theme.lua is included once by the Neovim tree below.

        # Globs of small text configs.
        for pattern, prefix in [
            ("~/.config/hypr/*.conf", "applied/hypr"),
            ("~/.config/waybar/*.jsonc", "applied/waybar"),
            ("~/.config/waybar/*.css", "applied/waybar"),
            ("~/.config/environment.d/*.conf", "applied/environment.d"),
            ("~/.config/fcitx5/conf/*.conf", "applied/fcitx5/conf"),
            ("~/.config/systemd/user/*.service", "applied/systemd/user"),
            ("~/.config/systemd/user/*.timer", "applied/systemd/user"),
            ("~/.config/systemd/user/*.socket", "applied/systemd/user"),
            ("~/.config/systemd/user/*.conf", "applied/systemd/user"),
            ("~/.config/devin/agents/*.md", "applied/devin/agents"),
            ("~/.omp/agent/agents/*.md", "applied/omp/agents"),
        ]:
            for src in sorted(Path(os.path.expanduser(pattern)).parent.glob(Path(pattern).name)):
                if src.is_file() and not src.is_symlink() and ".bak" not in src.name:
                    self.copy_file(src, f"{prefix}/{src.name}")

        # Trees.
        self.copy_tree(
            HOME / ".config/nvim",
            "applied/nvim",
            include_suffixes=(".lua", ".json", ".toml", ".vim", ".neoconf"),
            exclude_globs=("LICENSE", "README.md", "*.log"),
        )
        self.copy_tree(
            HOME / ".config/omarchy/current/theme",
            "applied/omarchy/theme",
            include_suffixes=(".conf", ".css", ".ini", ".toml", ".lua", ".json", ".name"),
        )
        self.copy_tree(HOME / ".agents/skills", "applied/agents/skills", include_suffixes=(".md", ".sh", ".py", ".js", ".json", ".yaml", ".yml", ".txt"))

        # System files.
        system_files = [
            ("/etc/pacman.conf", "etc/pacman.conf"),
            ("/etc/pacman.d/mirrorlist", "etc/pacman.d/mirrorlist"),
            ("/etc/mkinitcpio.conf", "etc/mkinitcpio.conf"),
            ("/etc/default/limine", "etc/default/limine"),
            ("/etc/limine-entry-tool.conf", "etc/limine-entry-tool.conf"),
            ("/etc/limine-entry-tool.d/resume.conf", "etc/limine-entry-tool.d/resume.conf"),
            ("/etc/fstab", "etc/fstab"),
            ("/etc/crypttab", "etc/crypttab"),
            ("/etc/systemd/resolved.conf", "etc/systemd/resolved.conf"),
            ("/etc/systemd/resolved.conf.d/10-disable-multicast.conf", "etc/systemd/resolved.conf.d/10-disable-multicast.conf"),
            ("/etc/systemd/resolved.conf.d/20-docker-dns.conf", "etc/systemd/resolved.conf.d/20-docker-dns.conf"),
            ("/etc/systemd/journald.conf", "etc/systemd/journald.conf"),
            ("/etc/systemd/journald.conf.d/size.conf", "etc/systemd/journald.conf.d/size.conf"),
            ("/etc/systemd/zram-generator.conf", "etc/systemd/zram-generator.conf"),
            ("/etc/sysctl.d/90-omarchy-file-watchers.conf", "etc/sysctl.d/90-omarchy-file-watchers.conf"),
            ("/etc/sysctl.d/99-sysctl.conf", "etc/sysctl.d/99-sysctl.conf"),
            ("/etc/modprobe.d/disable-usb-autosuspend.conf", "etc/modprobe.d/disable-usb-autosuspend.conf"),
            ("/etc/modprobe.d/hid_apple.conf", "etc/modprobe.d/hid_apple.conf"),
            ("/etc/modprobe.d/nvidia.conf", "etc/modprobe.d/nvidia.conf"),
            ("/etc/security/limits.conf", "etc/security/limits.conf"),
            ("/etc/ufw/ufw.conf", "etc/ufw/ufw.conf"),
            ("/etc/default/ufw", "etc/default/ufw"),
            ("/etc/ufw/user.rules", "etc/ufw/user.rules"),
            ("/etc/ufw/user6.rules", "etc/ufw/user6.rules"),
            ("/etc/ufw/before.rules", "etc/ufw/before.rules"),
            ("/etc/ufw/before6.rules", "etc/ufw/before6.rules"),
            ("/etc/ufw/after.rules", "etc/ufw/after.rules"),
            ("/etc/ufw/after6.rules", "etc/ufw/after6.rules"),
            ("/etc/ufw/sysctl.conf", "etc/ufw/sysctl.conf"),
            ("/etc/sddm.conf.d/10-wayland.conf", "etc/sddm.conf.d/10-wayland.conf"),
            ("/etc/sddm.conf.d/autologin.conf", "etc/sddm.conf.d/autologin.conf"),
            ("/etc/bluetooth/main.conf", "etc/bluetooth/main.conf"),
            ("/etc/bluetooth/input.conf", "etc/bluetooth/input.conf"),
            ("/etc/bluetooth/network.conf", "etc/bluetooth/network.conf"),
            ("/etc/cups/cupsd.conf", "etc/cups/cupsd.conf"),
            ("/etc/cups/cups-browsed.conf", "etc/cups/cups-browsed.conf"),
            ("/etc/cups/printers.conf", "etc/cups/printers.conf"),
            ("/etc/docker/daemon.json", "etc/docker/daemon.json"),
            ("/etc/X11/xorg.conf.d/00-keyboard.conf", "etc/X11/xorg.conf.d/00-keyboard.conf"),
            ("/etc/vconsole.conf", "etc/vconsole.conf"),
            ("/etc/locale.conf", "etc/locale.conf"),
            ("/etc/hostname", "etc/hostname"),
            ("/etc/hosts", "etc/hosts"),
            ("/etc/environment", "etc/environment"),
            ("/etc/os-release", "etc/os-release"),
            ("/etc/systemd/system.conf.d/10-faster-shutdown.conf", "etc/systemd/system.conf.d/10-faster-shutdown.conf"),
            ("/etc/systemd/system.conf.d/99-omarchy-nofile.conf", "etc/systemd/system.conf.d/99-omarchy-nofile.conf"),
            ("/etc/systemd/user.conf.d/99-omarchy-nofile.conf", "etc/systemd/user.conf.d/99-omarchy-nofile.conf"),
            ("/etc/systemd/coredump.conf.d/limit.conf", "etc/systemd/coredump.conf.d/limit.conf"),
            ("/etc/systemd/system/docker.service.d/no-block-boot.conf", "etc/systemd/system/docker.service.d/no-block-boot.conf"),
            ("/etc/systemd/system/plocate-updatedb.service.d/ac-only.conf", "etc/systemd/system/plocate-updatedb.service.d/ac-only.conf"),
            ("/etc/systemd/system/user@.service.d/faster-shutdown.conf", "etc/systemd/system/user@.service.d/faster-shutdown.conf"),
            ("/etc/systemd/system/limine-snapper-watcher.service", "etc/systemd/system/limine-snapper-watcher.service"),
            ("/etc/systemd/logind.conf", "etc/systemd/logind.conf"),
            ("/etc/systemd/sleep.conf", "etc/systemd/sleep.conf"),
            ("/etc/systemd/timesyncd.conf", "etc/systemd/timesyncd.conf"),
            ("/etc/systemd/networkd.conf", "etc/systemd/networkd.conf"),
            ("/etc/systemd/coredump.conf", "etc/systemd/coredump.conf"),
            ("/etc/systemd/homed.conf", "etc/systemd/homed.conf"),
            ("/etc/systemd/oomd.conf", "etc/systemd/oomd.conf"),
            ("/etc/systemd/pstore.conf", "etc/systemd/pstore.conf"),
            ("/etc/systemd/system.conf", "etc/systemd/system.conf"),
            ("/etc/systemd/user.conf", "etc/systemd/user.conf"),
            ("/etc/systemd/journal-remote.conf", "etc/systemd/journal-remote.conf"),
            ("/etc/systemd/journal-upload.conf", "etc/systemd/journal-upload.conf"),
            ("/boot/limine.conf", "etc/limine.conf"),
        ]
        for src, rel in system_files:
            self.copy_file(src, rel, follow_symlinks=True)
        for src in sorted(Path("/etc/systemd/network").glob("*.network")):
            self.copy_file(src, f"etc/systemd/network/{src.name}")
        sudoers_list = self.sudo_run(
            "find /etc/sudoers.d -maxdepth 1 -type f -printf '%f\\n' 2>/dev/null || true"
        )
        if sudoers_list and not sudoers_list.startswith("["):
            for name in sorted(sudoers_list.splitlines()):
                if name:
                    safe_name = name.replace(USERNAME, "user")
                    self.copy_file(Path("/etc/sudoers.d") / name,
                                   f"etc/sudoers.d/{safe_name}", follow_symlinks=True)
        else:
            for src in sorted(Path("/etc/sudoers.d").glob("*")):
                if src.is_file():
                    self.copy_file(src, f"etc/sudoers.d/{src.name}",
                                   follow_symlinks=True)

        # Active locale definitions only (the full file is mostly comments).
        try:
            active = []
            for line in read_config_text(Path("/etc/locale.gen")).splitlines():
                if line.strip() and not line.lstrip().startswith("#"):
                    active.append(line)
            self.write("etc/locale.gen.active", "\n".join(active) or "(none)")
        except (OSError, ValueError):
            self.notes.append("locale definitions unavailable")

        # Config footprint by top-level area.
        areas: dict[str, dict[str, int]] = {}
        for entry in self.config_index:
            path = Path(entry["path"])
            parts = path.parts
            if parts[0] == "applied":
                area = "home" if len(parts) > 1 and parts[1].startswith(".") else (
                    parts[1] if len(parts) > 1 else "applied"
                )
            elif parts[0] == "etc":
                second = parts[1] if len(parts) > 1 else ""
                if second.endswith(".conf"):
                    second = second[:-5]
                area = "etc/" + second
            else:
                area = parts[0]
            bucket = areas.setdefault(area, {"files": 0, "bytes": 0})
            bucket["files"] += 1
            bucket["bytes"] += entry["bytes"]
        self.data["config_footprint"] = {
            k: v for k, v in sorted(areas.items(), key=lambda kv: (-kv[1]["files"], kv[0]))
        }
        self.data["config_index"] = self.config_index

    def write_manifest(self) -> None:
        """Seal only the collector's own writes; never absorb an unexpected file."""
        fd = self._open_private_output()
        os.close(fd)
        found = set()
        for path in self.out.rglob("*"):
            info = path.lstat()
            if info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise PermissionError("capture contains output with non-private ownership or permissions")
            if stat.S_ISDIR(info.st_mode):
                continue
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("capture contains a symlink or special file")
            found.add(_snapshot_path(path.relative_to(self.out).as_posix()))
        expected = {row["path"] for row in self.artifacts}
        if len(expected) != len(self.artifacts) or found != expected:
            raise ValueError("capture contains unexpected or missing files; refusing to seal it")
        lines = [f"{row['sha256']}  {row['path']}" for row in sorted(self.artifacts, key=lambda row: row["path"])]
        self._write_private_file("ARTIFACTS.sha256", ("\n".join(lines) + "\n").encode("utf-8"))

    # -- report ------------------------------------------------------------
    def write_report(self) -> None:
        host = self.data["host"]
        hw = self.data["hardware"]
        pkg = self.data["packages"]
        areas = self.data.get("config_footprint", {})
        area_rows = [
            (area, info["files"], human_bytes(info["bytes"]))
            for area, info in areas.items()
        ]
        artifact_rows = [
            (a["path"], human_bytes(a["bytes"]), a["sha256"][:12] + "…")
            for a in sorted(self.artifacts, key=lambda x: x["path"])
        ]
        report = f"""# Snapshot report: {self.data['snapshot_id']}

> Captured **{self.data['captured_at']}** on `{host['hostname']}`.
>
> This report is the capture manifest. The human-readable inventory is the
> repository `README.md`; the machine-readable form is `data/snapshot.json`.

## Method

The snapshot was produced by `xsnapshot collect`. The collector:

1. Runs read-only inventory commands (`lscpu`, `lsblk`, `systemctl`, `pacman`,
   `docker`, `hyprctl`, `npm`, `cargo`, and friends).
2. Copies only allow-listed configuration files. Browser profiles, SSH keys,
   password-manager data, histories, caches, sessions, blobs, logs, and
   credential stores are never copied.
3. Applies a defense-in-depth redactor to every copied file and selected
   command output. The redactor removes UUIDs/PARTUUIDs, MAC and IP addresses,
   email addresses, machine/boot IDs, serial numbers, bearer tokens, literal
   secret assignments, and provider organization IDs.
4. Writes a SHA-256 index for the captured artifacts and an
   `ARTIFACTS.sha256` seal covering every file in the snapshot except the seal
   itself, so a later snapshot can be verified and diffed.

## Capture summary

| Field | Value |
|---|---|
| Hostname | `{host['hostname']}` |
| Chassis | {host['chassis']} |
| Board | {hw['board']['model']} ({hw['board']['version']}) |
| Firmware | {hw['board']['bios']} dated {hw['board']['bios_date']} |
| OS | {host['os']} |
| Kernel | `{host['kernel']}` |
| Architecture | {host['architecture']} |
| CPU | {hw['cpu']['model']} ({hw['cpu']['threads']} threads) |
| Memory | {hw['memory']['total_human']} |
| GPU | {hw['gpu']['name']} ({hw['gpu']['vram']}, driver {hw['gpu']['driver']}) |
| Omarchy | {self.data['omarchy']['version']} ({self.data['omarchy']['branch']}/{self.data['omarchy']['channel']}) |
| Desktop | {first_nonempty(self.data['desktop']['hyprland'], 'Hyprland')} |
| Theme | {self.data['desktop']['theme']} |
| System packages | {pkg['all_count'] if pkg['all_count'] is not None else 'unavailable'} total / {pkg['explicit_count'] if pkg['explicit_count'] is not None else 'unavailable'} explicit / {pkg['foreign_count'] if pkg['foreign_count'] is not None else 'unavailable'} foreign |
| Config files captured | {len(self.config_index)} |
| Redactions applied | {self.redaction_total} |

## Configuration footprint

{md_table(["Area", "Files", "Bytes"], area_rows)}

## Package inventory

- System package inventories: `packages/` (`pacman-*` on Arch/Omarchy, `system-*` elsewhere).
- Unavailable or inapplicable package lists and counts are null, not zero.
- APT manual selections are explicit; foreign/AUR applies only to pacman.
- npm globals: `packages/npm-global.txt`
- Cargo installs: `packages/cargo-installed.txt`
- pip user packages: `packages/pip-user.txt`
- Ruby gems: `packages/gem-local.txt`
- Largest installed packages: `packages/largest-installed.txt`

## Coverage and limits

- **Captured:** hardware, firmware, boot chain, storage, encryption, package
  sets, services, network posture, firewall, desktop/compositor settings,
  shell and prompt, terminal and tmux, editor, theme, fonts, audio devices,
  developer tool versions, global language packages, containers, agent tool
  configuration, and allow-listed dotfiles.
- **Not captured:** file contents outside the allow-list; browser profiles,
  cookies, history, local storage; SSH/GPG private keys; password-manager
  vaults; API keys, OAuth tokens, session tokens; shell and agent conversation
  histories; machine/boot IDs; partition UUIDs; MAC/IP addresses; hardware
  serial numbers; raw kernel keyrings; and any file that failed the text/binary
  guard.
- **Docker:** inventory uses only a known local Unix socket, without saved Docker
  configuration or sudo. Remote/custom contexts are omitted. See the Docker
  notes and per-section status; unavailable never means no containers.
- **Local output:** new capture directories and files are owner-only. This is
  not encryption, does not change earlier captures, and does not remove the need
  to review every retained file before sharing.
- **Not a backup:** this is a descriptive inventory. It cannot restore
  credentials, encrypted volumes, browser sessions, or application state.
- **Privilege:** root-owned files are read through `sudo -n` when available.
  If passwordless sudo is unavailable, those files are reported as missing in
  the notes instead of being approximated.

## Artifact index

The table below lists every captured artifact except this report and
`data/snapshot.json`; both are covered by `ARTIFACTS.sha256`, which seals every
file in the snapshot except itself.

{md_table(["Path", "Size", "SHA-256"], artifact_rows)}

## Notes

{chr(10).join('- ' + note for note in self.notes) if self.notes else '- none'}
"""
        self.write("REPORT.md", report)

    # -- orchestration -----------------------------------------------------
    def collect(self) -> None:
        fd = self._open_private_output()
        os.close(fd)
        self.collect_identity()
        self.collect_hardware()
        self.collect_storage()
        self.collect_network()
        self.collect_services()
        self.collect_boot()
        self.collect_desktop()
        self.collect_dev()
        self.collect_docker()
        self.collect_agents()
        self.collect_packages()
        self.collect_configs()
        self.data["privacy"] = {
            "policy": "allow-list plus redaction; secrets and unique identifiers excluded",
            "excluded": [
                "SSH/GPG private keys",
                "password-manager vaults",
                "browser profiles, cookies, history, local storage",
                "API keys, OAuth tokens, session tokens",
                "shell and agent conversation histories",
                "machine and boot IDs",
                "partition UUIDs, MAC/IP addresses, hardware serials",
                "local account names and home paths",
                "caches, blobs, logs, sessions, backups",
            ],
            "redactions_applied": self.redaction_total,
            "config_files_captured": len(self.config_index),
            "artifact_seal": "ARTIFACTS.sha256",
            "local_output": "owner-only capture directories and files; not encryption or a privacy guarantee",
        }
        self.data["commands"] = self.commands
        self.data["notes"] = self.notes
        # Account the identity scrub of the JSON document before the report so
        # REPORT.md and data/snapshot.json publish the same redaction total.
        preview = json.dumps(self.data, indent=2, sort_keys=False)
        preview, identity_count = redact_identity(preview)
        self.redaction_total += identity_count
        self.data["privacy"]["redactions_applied"] = self.redaction_total
        # REPORT.md is an artifact too. Write it first, then freeze the index
        # and write the machine-readable snapshot. The two self-referential
        # files are covered by ARTIFACTS.sha256, not by artifacts[].
        self.write_report()
        self.data["artifacts"] = sorted(self.artifacts, key=lambda x: x["path"])
        json_text = json.dumps(self.data, indent=2, sort_keys=False)
        json_text, _ = redact_identity(json_text)
        self.write("data/snapshot.json", json_text, sanitize=False)
        self.write_manifest()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def snapshot_dirs(root: Path) -> list[Path]:
    base = root / "snapshots"
    if not base.exists():
        return []
    return sorted([p for p in base.iterdir() if p.is_dir()], reverse=True)


def preflight_report() -> dict[str, Any]:
    """Inspect prerequisites only: no inventory command, config body or socket I/O."""
    linux = platform.system() == "Linux"
    check = {
        "linux": linux,
        "python_3_10_or_newer": sys.version_info >= (3, 10),
        "isolated_python_startup": bool(sys.flags.isolated and sys.flags.no_site),
        "fixed_bash_available": os.path.isfile("/bin/bash") and os.access("/bin/bash", os.X_OK),
        "private_output_primitives": all(hasattr(os, flag) for flag in ("O_NOFOLLOW", "O_DIRECTORY", "O_CLOEXEC"))
            and os.open in os.supports_dir_fd and os.mkdir in os.supports_dir_fd,
    }
    tools = {name: shutil.which(name, path=os.defpath) is not None for name in (
        "lscpu", "free", "lspci", "lsusb", "lsblk", "findmnt", "ip", "systemctl",
        "pacman", "dpkg-query", "rpm", "npm", "cargo", "hyprctl", "wpctl", "docker",
    )}
    warnings = []
    if not any(tools[name] for name in ("pacman", "dpkg-query", "rpm")):
        warnings.append("No supported native package query tool is present in the system search path. Installed package inventory may be unavailable.")
    if not all(tools.values()):
        warnings.append("Some optional inventory tools are absent from the system search path. Missing tool output is not evidence of missing hardware or software.")
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        warnings.append("This process is running as root. Start an actual capture as an ordinary user with --no-sudo; this check does not change privileges.")
    warnings.append("Inventory programs can still load their own configuration or contact configured services. Preflight does not execute or authenticate them.")
    socket_info = Collector._local_docker_socket() if linux and hasattr(os, "geteuid") else None
    return {
        "schema": "xsnapshot/preflight/v1", "core_prerequisites_met": all(check.values()),
        "checks": check, "system_path_tools": tools,
        "supported_docker_socket_present": socket_info is not None,
        "docker_socket_checked_without_connecting": True,
        "capture_verified": False, "warnings": warnings,
        "limits": "No workstation inventory, configuration bodies, daemon queries, uploads, installs or permission changes. Presence is not trust, compatibility, privacy or release verification.",
    }


def cmd_preflight(args: argparse.Namespace) -> int:
    report = preflight_report()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("xsnapshot preflight: " + ("core prerequisites available" if report["core_prerequisites_met"] else "blocked prerequisites"))
        for name, passed in report["checks"].items():
            print(f"  {'ok' if passed else 'missing/unsupported'}: {name}")
        missing = [name for name, found in report["system_path_tools"].items() if not found]
        print("  optional tools absent from system path: " + (", ".join(missing) or "none"))
        print("  supported Docker socket: " + ("present, not queried" if report["supported_docker_socket_present"] else "not found; Docker inventory may be unavailable"))
        for warning in report["warnings"]:
            print("  note: " + warning)
        print(report["limits"])
    return 0 if report["core_prerequisites_met"] else 2


def cmd_collect(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    snapshot_id = args.snapshot or dt.datetime.now().astimezone().strftime("%Y-%m-%d")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", snapshot_id):
        print("snapshot id must be a single safe filename", file=sys.stderr)
        return 2
    requested = Path(args.out).expanduser() if args.out else root / "snapshots" / snapshot_id
    if requested.is_symlink() or (root / "snapshots").is_symlink():
        print("refusing a symlink snapshot destination", file=sys.stderr)
        return 2
    out = requested.resolve()
    if out.exists() and not args.force:
        print(f"refusing to overwrite existing snapshot: {out}", file=sys.stderr)
        print("use --force to replace this capture deliberately", file=sys.stderr)
        return 2
    if out.exists() and args.force:
        base = root / "snapshots"
        managed_child = out != base and out.is_relative_to(base)
        temporary_capture = out.parent == Path("/tmp") and out.name.startswith("xsnapshot")
        if not out.is_dir() or not (managed_child or temporary_capture):
            print("refusing to replace a directory outside the capture boundary", file=sys.stderr)
            return 2
        shutil.rmtree(out)
    try:
        # The final directory must be new. A competing creation is not permission
        # to reuse or change it, even after an approved force removal.
        out.mkdir(mode=0o700, parents=True, exist_ok=False)
    except OSError as exc:
        print(f"cannot create a new private capture directory: {exc}", file=sys.stderr)
        return 2
    collector = Collector(root=root, out=out, sudo=not args.no_sudo)
    print(f"collecting snapshot {snapshot_id} -> {out}")
    try:
        collector.collect()
    except (OSError, ValueError) as exc:
        print(f"capture stopped: {exc}", file=sys.stderr)
        print("Partial output remains local. Inspect it before any deliberate replacement; do not share it.", file=sys.stderr)
        return 1
    print(f"done: {len(collector.artifacts)} artifacts, {collector.redaction_total} redactions")
    print(f"report: {out / 'REPORT.md'}")
    print(f"json:   {out / 'data/snapshot.json'}")
    return 0


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError("non-finite JSON constants are not permitted")


def _snapshot_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("invalid snapshot-relative path")
    path = Path(value)
    if not path.parts or path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise ValueError("unsafe snapshot-relative path")
    if any(ord(char) < 32 for char in value):
        raise ValueError("control character in snapshot path")
    return value


def _validate_snapshot(snap: Path) -> tuple[int, str]:
    # Inspect the entire supplied tree before reading any artifact. Symlink and
    # special-file rejection prevents following a sealed path outside the tree.
    on_disk: set[str] = set()
    total_bytes = 0
    for count, path in enumerate(snap.rglob("*"), 1):
        rel = path.relative_to(snap)
        if count > 8192 or len(rel.parts) > 32:
            raise ValueError("snapshot traversal limit exceeded")
        if path.is_symlink() or (not path.is_dir() and not path.is_file()):
            raise ValueError("snapshot contains a symlink or special file")
        if path.is_file():
            on_disk.add(_snapshot_path(rel.as_posix()))
            total_bytes += path.stat().st_size
            if len(on_disk) > 4096 or total_bytes > 64 * 1024 * 1024:
                raise ValueError("snapshot exceeds 4096 files or 64 MiB")
    if not {"data/snapshot.json", "REPORT.md", "ARTIFACTS.sha256"} <= on_disk:
        raise ValueError("snapshot JSON, report and artifact seal are required")
    data_path, seal_path = snap / "data/snapshot.json", snap / "ARTIFACTS.sha256"
    if data_path.stat().st_size > 8 * 1024 * 1024 or seal_path.stat().st_size > 1024 * 1024:
        raise ValueError("snapshot JSON or seal exceeds its size limit")
    data = json.loads(data_path.read_text(encoding="utf-8"), object_pairs_hook=_unique_json_object, parse_constant=_reject_json_constant)
    required = ["schema", "snapshot_id", "captured_at", "host", "os", "hardware",
                "storage", "desktop", "packages", "config_index", "artifacts", "privacy"]
    if not isinstance(data, dict) or any(key not in data for key in required):
        raise ValueError("snapshot is not an object with the required sections")
    if data["schema"] != SCHEMA:
        raise ValueError("unexpected snapshot schema")
    if not isinstance(data["snapshot_id"], str) or data["snapshot_id"] != snap.name:
        raise ValueError("snapshot id does not match the capture directory")
    if not isinstance(data["captured_at"], str):
        raise ValueError("capture date must be an ISO timestamp")
    dt.datetime.fromisoformat(data["captured_at"])
    for key in ("host", "os", "hardware", "storage", "desktop", "packages", "privacy"):
        if not isinstance(data[key], dict):
            raise ValueError("snapshot section has an invalid type")

    seal: dict[str, str] = {}
    for line in seal_path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            raise ValueError("malformed artifact seal line")
        digest, rel = match.groups()
        rel = _snapshot_path(rel)
        if rel in seal:
            raise ValueError("duplicate artifact seal entry")
        seal[rel] = digest
    if set(seal) != on_disk - {"ARTIFACTS.sha256"}:
        raise ValueError("artifact seal does not exactly cover the capture")
    for rel, expected in seal.items():
        if hashlib.sha256((snap / rel).read_bytes()).hexdigest() != expected:
            raise ValueError("artifact seal hash mismatch")

    artifacts = data["artifacts"]
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("artifact index must be a nonempty list")
    indexed: dict[str, dict[str, Any]] = {}
    for item in artifacts:
        if not isinstance(item, dict):
            raise ValueError("artifact entry must be an object")
        rel = _snapshot_path(item.get("path"))
        if rel in indexed:
            raise ValueError("duplicate artifact index entry")
        indexed[rel] = item
    if set(indexed) != on_disk - {"data/snapshot.json", "ARTIFACTS.sha256"}:
        raise ValueError("artifact index does not exactly cover the capture")
    for rel, item in indexed.items():
        if type(item.get("bytes")) is not int or item["bytes"] != (snap / rel).stat().st_size:
            raise ValueError("artifact byte size mismatch")
        if item.get("sha256") != seal[rel]:
            raise ValueError("artifact hash mismatch")

    configs = data["config_index"]
    if not isinstance(configs, list):
        raise ValueError("config index must be a list")
    seen: set[str] = set()
    for entry in configs:
        if not isinstance(entry, dict):
            raise ValueError("config entry must be an object")
        rel = _snapshot_path(entry.get("path"))
        if rel in seen or rel not in indexed:
            raise ValueError("duplicate or unindexed config entry")
        seen.add(rel)
        if type(entry.get("bytes")) is not int or entry.get("snapshot_sha256") != seal[rel] or entry["bytes"] != indexed[rel]["bytes"]:
            raise ValueError("config hash or byte size mismatch")
        if type(entry.get("redactions")) is not int or entry["redactions"] < 0:
            raise ValueError("invalid config redaction count")
        if not isinstance(entry.get("source"), str):
            raise ValueError("config source label must be text")
    copied = {rel for rel in indexed if rel.startswith(("etc/", "applied/"))
              and rel != "etc/locale.gen.active"}
    if seen != copied:
        raise ValueError("config index does not exactly cover copied configs")
    if type(data["privacy"].get("config_files_captured")) is not int or data["privacy"]["config_files_captured"] != len(configs):
        raise ValueError("privacy count does not match config index")
    for name in ("all", "explicit", "foreign"):
        values = data["packages"].get(name)
        count = data["packages"].get(name + "_count")
        if name in data["packages"] and name + "_count" in data["packages"] and values is None and count is None:
            continue
        if not isinstance(values, list) or any(not isinstance(item, str) for item in values) or type(count) is not int or count != len(values):
            raise ValueError("package inventory count or type mismatch")
    return len(indexed), hashlib.sha256(seal_path.read_bytes()).hexdigest()


def cmd_validate(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    snap = Path(args.snapshot).resolve() if args.snapshot else (
        snapshot_dirs(root)[0] if snapshot_dirs(root) else None
    )
    if not snap:
        print("no snapshots found", file=sys.stderr)
        return 2
    try:
        count, seal_digest = _validate_snapshot(snap)
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        print(f"invalid snapshot: {exc}", file=sys.stderr)
        return 1
    print(f"valid: {snap} ({count} artifacts, seal {seal_digest[:12]}…)")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    for snap in snapshot_dirs(root):
        data_path = snap / "data/snapshot.json"
        captured = ""
        if data_path.exists():
            try:
                captured = json.loads(data_path.read_text(encoding="utf-8")).get("captured_at", "")
            except json.JSONDecodeError:
                captured = "invalid-json"
        print(f"{snap.name}\t{captured}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="xsnapshot", description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=str(REPO_ROOT), help="repository root (default: %(default)s)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_preflight = sub.add_parser("preflight", help="check prerequisites without collecting or querying services")
    p_preflight.add_argument("--json", action="store_true", help="print a non-capture JSON readiness report")
    p_preflight.set_defaults(func=cmd_preflight)

    p_collect = sub.add_parser("collect", help="capture a new snapshot")
    p_collect.add_argument("--snapshot", help="snapshot id (default: local date)")
    p_collect.add_argument("--out", help="output directory (default: <root>/snapshots/<id>)")
    p_collect.add_argument("--force", action="store_true", help="replace an existing snapshot")
    p_collect.add_argument("--no-sudo", action="store_true", help="do not attempt root-only files")
    p_collect.set_defaults(func=cmd_collect)

    p_validate = sub.add_parser("validate", help="validate a snapshot and its artifact hashes")
    p_validate.add_argument("snapshot", nargs="?", help="snapshot directory (default: newest)")
    p_validate.set_defaults(func=cmd_validate)

    p_list = sub.add_parser("list", help="list snapshots")
    p_list.set_defaults(func=cmd_list)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())


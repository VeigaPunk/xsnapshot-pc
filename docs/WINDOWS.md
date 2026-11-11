# Windows collector

This is the native Windows implementation of `xsnapshot-pc`. It emits the same
`xsnapshot/v1` schema as the Linux collector: a reviewable folder containing
`data/snapshot.json`, `REPORT.md`, allow-listed redacted configuration copies,
and an `ARTIFACTS.sha256` seal. Nothing is uploaded.

It is not a tagged release yet. Production `https://xsnapshot.app/install.ps1`
stays unpinned (and refuses to run) until a reviewed tag is published and the
site pin is filled. Until then, run the collector from this checkout.

## Requirements

- Windows 10 or 11, or Windows Server 2019 or newer
- Windows PowerShell 5.1 (ships with Windows) or PowerShell 7
- No elevation, no package installation, and no persistent execution-policy change

Optional tools improve inventory but are not required: `winget`, `git`, `npm`,
`python`/`py`, `cargo`, `choco`, `scoop`, `nvidia-smi`.

## Capture

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\bin\xsnapshot.ps1 --root $env:USERPROFILE\xsnapshot-data collect --snapshot 2026-11-11-label
```

The process-scoped `-ExecutionPolicy Bypass` applies only to this invocation.
The collector does not change the user or machine policy.

From a checkout, `.\install.ps1` also runs the local collector into
`./xsnapshot-data` (or `$env:XSNAPSHOT_STATE_DIR`). That path is not a pinned
release; it prints that warning first.

Output:

```
<root>/snapshots/<id>/
  applied/     allow-listed user configuration, redacted
  etc/         allow-listed system configuration, redacted
  packages/    Uninstall, winget, Appx and language-tool inventories
  system/      identity, hardware, storage, network, boot, desktop, services, tools, agents
  data/snapshot.json
  REPORT.md
  ARTIFACTS.sha256
```

Validate with either the Windows entry point or the Linux one (the seal and
schema are the same):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\bin\xsnapshot.ps1 --root $env:USERPROFILE\xsnapshot-data validate
```

```bash
./bin/xsnapshot --root /path/to/xsnapshot-data validate snapshots/<id>
```

## Package lists

`packages.all`, `packages.explicit` and `packages.foreign` are required
`xsnapshot/v1` string lists. On Windows they mean:

| Field | Source |
|---|---|
| `all` | Uninstall registry entries: `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall`, the Wow6432Node view, and the HKCU Uninstall key. Each line is `Name Version (Publisher)`. |
| `explicit` | `winget list --disable-interactivity --accept-source-agreements`, when `winget` is on `PATH`. Empty, with a note, when it is not. |
| `foreign` | `Get-AppxPackage` as `Name Version`. GUID-shaped names are written as `<uuid>`; exact versions are kept. This is the Appx/MSIX inventory, not a trust judgement. |

npm (`-g`), pip, cargo, Chocolatey and Scoop inventories, when those tools are
present, are written to `packages/language.txt` and are not folded into the
three schema lists.

## Configuration allow-list

Only these paths are copied, and only when they are regular files no larger
than 1 MiB. Symlinks and reparse points are skipped. Every copied body is
redacted before it is written.

- PowerShell profiles under `Documents\WindowsPowerShell` and `Documents\PowerShell`
- `~/.gitconfig` and `~/.config/git/config`
- `~/.ssh/config` (never private keys, never `known_hosts`)
- `~/.vimrc`, `~/.config/nvim/init.lua`, `~/.config/nvim/init.vim`
- `~/.cargo/config.toml`, `~/.condarc`, user `pip.ini` / `pip.conf`
- VS Code and Cursor user `settings.json`, `keybindings.json`, `argv.json`
- Windows Terminal `settings.json` (unpackaged and packaged locations)
- WinGet user `settings.json`
- `~/.config/alacritty/alacritty.toml`, `~/.wezterm.lua`
- `C:\Windows\System32\drivers\etc\hosts`

Not copied: browser profiles, credential vaults, `.npmrc`, `.netrc`, cloud
vendor credentials, agent conversation histories, Claude, Cursor or VS Code
storage and workspace databases, logs, caches, dumps, and anything else
outside this list.

## Redaction

The same shapes the Linux collector redacts, plus Windows-specific ones:

- IPv4, IPv6 and MAC addresses (colon and hyphen forms)
- UUID/GUID, MachineGuid, ProductId, including GUID-named Appx/MSIX packages
  in the package inventory lists and in `data/snapshot.json` (`<uuid>`)
- Hardware serial lines
- Bearer tokens, JSON/key-value/environment secret assignments, `org-` ids
- Email addresses
- Windows SIDs (`S-1-5-21-...`)
- The local account name and every form of the user profile path, replaced
  with `user` and `C:\Users\user` (or `C:/Users/user` when the original used
  slashes)

The hostname, hardware model names, package names and exact versions, and
service names are kept, as on Linux. Dotted package versions are not rewritten
as addresses. Redaction is defense in depth; the allow-list is
the primary control. Review `REPORT.md` and the copied files before sharing.

## Publishing

Open the complete snapshot folder on https://xsnapshot.app (not just
`data/snapshot.json`). The site verifies the seal and scans the JSON for
identifier shapes locally. Publishing sends only the reviewed JSON. A signed-in
session attaches the snapshot to the account; there is no CLI that uploads
with a copied cookie or token.

## Limits

- Not application or configuration parity with the Arch/Linux collector
- GPU VRAM is reported from `nvidia-smi` when present; otherwise it stays
  `unknown` rather than using overflow-prone CIM AdapterRAM values
- Network routes, listeners, DNS addresses and volume/disk serials are omitted
- BitLocker presence is not attested
- The official website installer is not live for Windows until a tag is pinned

A hardware-only Python experiment lived on the draft branch
`stakker/add-windows-capture` (PR #7). This collector supersedes it for
workstation inventory: it is PowerShell-native and covers packages, services
and allow-listed configuration, not only CIM hardware fields.

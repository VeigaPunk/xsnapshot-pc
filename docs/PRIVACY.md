# Privacy policy — xsnapshot-pc

This document states the privacy model the collector actually implements. The authoritative
implementation is [`lib/xsnapshot.py`](../lib/xsnapshot.py); if this document and the code
disagree, the code is correct and this document is a bug. The shipped capture is
`snapshots/2026-10-19/`.

## Publication status

This repository (`VeigaPunk/xsnapshot-pc`) is public, and every snapshot committed under
`snapshots/` is published with it: readable, indexable, cloneable, and retained in history.
There is no private tier. The review gate in this document is therefore mandatory for every
capture, not a pre-release courtesy, and the residual findings listed below are already part of
the public `snapshots/2026-10-19/` tree. A file that might contain a secret or a unique
identifier must be left out of the allow-list; the redactor is a second line of defense and is
not a substitute for that decision.

## Model

Three controls, in order of strength:

1. **Allow-list.** The collector never sweeps a home directory, a browser profile, or `/etc`.
   It copies exactly the paths listed in `collect_configs()` below, plus filtered trees. A file
   that is not on the list is not read, regardless of what it contains.
2. **Structural guards.** Symlinked user config is skipped (system config is followed
   deliberately); any file with a NUL byte in its first 8192 bytes is skipped as binary; files
   that cannot be read are recorded in `REPORT.md` notes as missing instead of being guessed.
3. **Redactor.** Every copied config file, every `system/*.txt` section, `system/agents.txt`,
   and selected command output pass through `redact_text()`, which ends with
   `redact_identity()` (home path → `/home/user`, account name → `user`). The JSON document is
   additionally passed through `redact_identity()` before it is written. Package-manager output
   (npm, Cargo, pip, RubyGems) is identity-scrubbed the same way. Each config entry records its
   source label, path, byte size, post-redaction `snapshot_sha256`, and `redactions` count, so a
   reviewer can see exactly which files were touched and how often. `ARTIFACTS.sha256` then
   seals every file in the snapshot except itself.

The collector performs **no network I/O**. It shells out to local inventory commands
(`hostnamectl`, `lscpu`, `dmidecode`, `lsblk`, `systemctl`, `pacman`, `docker`, `hyprctl`,
`npm`, `cargo`, and similar) and writes files under the snapshot directory. Nothing is uploaded
or executed from captured content.

## Allow-list

### User configuration (copied verbatim through the redactor)

```text
~/.bashrc
~/.bash_profile
~/.profile
~/.tmux.conf
~/.config/starship.toml
~/.config/git/config
~/.config/mise/config.toml
~/.config/alacritty/alacritty.toml
~/.config/ghostty/config
~/.config/kitty/kitty.conf
~/.config/foot/foot.ini
~/.config/tmux/tmux.conf
~/.config/fontconfig/fonts.conf
~/.config/btop/btop.conf
~/.config/fastfetch/config.jsonc
~/.config/swayosd/config.toml
~/.config/swayosd/style.css
~/.config/walker/config.toml
~/.config/gtk-3.0/bookmarks
~/.config/fcitx5/profile
~/.config/omarchy/current/theme.name
~/.config/omarchy/branding/about.txt
~/.config/omarchy/branding/screensaver.txt
~/.agents/AGENTS.md
~/.omp/agent/config.yml
~/.config/opencode/cli.json
~/.config/opencode/opencode.json
~/.config/devin/config.json
~/.config/devin/mcp_config.json
~/.config/devin/AGENTS.md
~/.grok/config.toml
~/.codex/config.toml
~/.kimi-code/tui.toml
~/.claude/settings.json
~/nvme1-scratch-sudoers
```

### Globbed user configuration

```text
~/.config/hypr/*.conf
~/.config/waybar/*.jsonc
~/.config/waybar/*.css
~/.config/environment.d/*.conf
~/.config/fcitx5/conf/*.conf
~/.config/systemd/user/*.service
~/.config/systemd/user/*.timer
~/.config/systemd/user/*.socket
~/.config/systemd/user/*.conf
~/.config/devin/agents/*.md
~/.omp/agent/agents/*.md
```

Globbed items are copied only when they are regular files (no symlinks) and their name does not
contain `.bak`.

### Trees (filtered)

| Tree | Included suffixes | Excluded |
|---|---|---|
| `~/.config/nvim` | `.lua`, `.json`, `.toml`, `.vim`, `.neoconf` | `LICENSE`, `README.md`, `*.log`; directories `.git`, `node_modules`, `__pycache__`, `.cache` |
| `~/.config/omarchy/current/theme` | `.conf`, `.css`, `.ini`, `.toml`, `.lua`, `.json`, `.name` | directories as above |
| `~/.agents/skills` | `.md`, `.sh`, `.py`, `.js`, `.json`, `.yaml`, `.yml`, `.txt` | directories as above |

One user-config symlink is followed deliberately: `~/.config/nvim/lua/plugins/theme.lua` points
into the active Omarchy theme, so it is copied with `follow_symlinks=True`. Every other
symlinked user config is skipped and recorded in `REPORT.md` notes.

### System configuration

```text
/etc/pacman.conf
/etc/pacman.d/mirrorlist
/etc/mkinitcpio.conf
/etc/default/limine
/etc/limine-entry-tool.conf
/etc/limine-entry-tool.d/resume.conf
/etc/fstab
/etc/crypttab
/etc/systemd/resolved.conf
/etc/systemd/resolved.conf.d/10-disable-multicast.conf
/etc/systemd/resolved.conf.d/20-docker-dns.conf
/etc/systemd/journald.conf
/etc/systemd/journald.conf.d/size.conf
/etc/systemd/zram-generator.conf
/etc/systemd/logind.conf
/etc/systemd/sleep.conf
/etc/systemd/timesyncd.conf
/etc/systemd/networkd.conf
/etc/systemd/coredump.conf
/etc/systemd/homed.conf
/etc/systemd/oomd.conf
/etc/systemd/pstore.conf
/etc/systemd/system.conf
/etc/systemd/user.conf
/etc/systemd/journal-remote.conf
/etc/systemd/journal-upload.conf
/etc/systemd/system.conf.d/10-faster-shutdown.conf
/etc/systemd/system.conf.d/99-omarchy-nofile.conf
/etc/systemd/user.conf.d/99-omarchy-nofile.conf
/etc/systemd/coredump.conf.d/limit.conf
/etc/systemd/system/docker.service.d/no-block-boot.conf
/etc/systemd/system/plocate-updatedb.service.d/ac-only.conf
/etc/systemd/system/user@.service.d/faster-shutdown.conf
/etc/systemd/system/limine-snapper-watcher.service
/etc/systemd/network/*.network
/etc/sysctl.d/90-omarchy-file-watchers.conf
/etc/sysctl.d/99-sysctl.conf
/etc/modprobe.d/disable-usb-autosuspend.conf
/etc/modprobe.d/hid_apple.conf
/etc/modprobe.d/nvidia.conf
/etc/security/limits.conf
/etc/ufw/ufw.conf
/etc/default/ufw
/etc/ufw/user.rules
/etc/ufw/user6.rules
/etc/ufw/before.rules
/etc/ufw/before6.rules
/etc/ufw/after.rules
/etc/ufw/after6.rules
/etc/ufw/sysctl.conf
/etc/sddm.conf.d/10-wayland.conf
/etc/sddm.conf.d/autologin.conf
/etc/bluetooth/main.conf
/etc/bluetooth/input.conf
/etc/bluetooth/network.conf
/etc/cups/cupsd.conf
/etc/cups/cups-browsed.conf
/etc/cups/printers.conf
/etc/docker/daemon.json
/etc/X11/xorg.conf.d/00-keyboard.conf
/etc/vconsole.conf
/etc/locale.conf
/etc/hostname
/etc/hosts
/etc/environment
/etc/os-release
/etc/locale.gen          # active (uncommented) lines only, as etc/locale.gen.active
/boot/limine.conf
/etc/sudoers.d/*         # all regular files, read via sudo -n when needed
```

System files are read through `sudo -n` when the collector is not root and passwordless sudo
works; otherwise the file is reported as missing in `REPORT.md` notes. Sudoers filenames pass
through the identity scrub, so a file named after the account is stored as
`etc/sudoers.d/99-user-nopasswd` (its contents also show `user`).

## Deny-list (never copied, by construction)

The collector does not walk directories other than the three filtered trees above, so the
following are never read in the first place:

- browser profiles, cookies, history, local storage, session stores;
- SSH and GPG private keys, `authorized_keys`, known-hosts files;
- password-manager vaults, keyrings (`/etc/pacman.d/gnupg`, `~/.local/share/keyrings`);
- API keys, OAuth tokens, session tokens, provider credential stores;
- shell histories (`.bash_history`, `.zsh_history`), agent/LLM conversation transcripts and
  prompt histories;
- caches, blobs, logs, `node_modules`, VCS metadata, backups, `.bak` files, editor swap files;
- mail stores, chat databases, media libraries;
- kernel keyrings, process memory, environment dumps;
- machine ID, boot ID, partition/filesystem UUIDs, hardware serial numbers, MAC addresses,
  IP addresses (removed by redaction where they appear inside an allow-listed output).

## What the redactor removes

Applied to text, in this order (each rule counts its substitutions):

| Rule | Pattern | Replacement |
|---|---|---|
| Machine/Boot ID lines | `Machine ID` / `Boot ID` / `machine-id` / `boot-id` line with a ≥16-hex value | `<redacted>` |
| `machine-id=` | `machine-id=[0-9a-f]{16,}` | `machine-id=<redacted>` |
| PARTUUID | `PARTUUID=` followed by ≥4 chars of `[0-9A-Fa-f-]` | `PARTUUID=<uuid>` |
| UUID assignment | `UUID=` followed by ≥4 chars of `[0-9A-Fa-f-]` | `UUID=<uuid>` |
| Canonical UUID | `8-4-4-4-12` hex form | `<uuid>` |
| MAC | six colon-separated hex pairs | `<mac>` |
| IPv4 | dotted quad, not adjacent to word/dot characters | `<ip>` |
| IPv6 loopback | `::1` or `::` | `<ipv6>` |
| IPv6 (general) | token that parses as an IPv6 address, optional `%zone` | `<ipv6>` |
| Bracketed IPv6 | `[ … ]` literal | `<ipv6>` |
| Email | `local@domain.tld` | `<email>` |
| Bearer token | `Bearer <12+ token chars>` | `Bearer <redacted>` |
| JSON secret keys | `password`, `passwd`, `secret`, `token`, `api_key`, `access_key`, `refresh_token`, `client_secret`, `private_key`, `auth_token`, `org_id` with a ≥4-char value | value → `<redacted>` |
| Key/value secrets | same key names with `:` or `=` and a ≥16-char value (quoted or bare, not `$`-prefixed) | value → `<redacted>` |
| Environment secrets | `*TOKEN*`, `*SECRET*`, `*PASSWORD*`, `*API_KEY*`, `*ACCESS_KEY*`, `*PRIVATE_KEY*`, `*AUTH_KEY*` assignments with a ≥16-char value | value → `<redacted>` |
| Generic secret-ish assignments | `*TOKEN`, `*SECRET`, `*PASSWORD`, `*PASSWD`, `*_KEY`, `*APIKEY` with a ≥12-char value | value → `<redacted>` |
| DMI serial | `Serial Number:` (except "To be filled") | `<redacted>` |
| DMI UUID | `UUID:` line in DMI output | `<redacted>` |
| PipeWire cookie | `cookie:<digits>` | `cookie:<redacted>` |
| UKI / config hash | `#` + ≥64 lowercase hex chars | `#<redacted-hash>` |
| Provider org ID | `org-` + ≥16 hex chars | `org-<redacted>` |
| Serial lines | `serial:` line | `serial: <redacted>` |
| Device paths | `/dev/disk/by-partuuid/<hex>`, `by-uuid/<hex>` | `<uuid>` |
| Local identity | the literal home path, then the literal account name | `/home/user`, then `user` |

Network command output additionally passes `redact_network()`, which blanks the value on lines
beginning with `Current DNS Server`, `DNS Server(s)`, `Fallback DNS Server(s)`, `Gateway`,
`address`, `inet`, `inet6`, or `MAC Address`, and rewrites `via <addr>` → `<gateway>` and
`src <addr>` → `<source>`.

Two pre-passes protect values that would otherwise be over-matched, and one protects a sudoers
keyword: `protect_versions` shields version-shaped tokens (`N.N.N[.N]`) in
`system/hardware.txt` and `system/dev.txt`, so Vulkan driver and Java build versions survive;
`protect_systemd_units` shields unit names of the form
`name@instance.{service,timer,socket,target,path,mount,automount,slice,scope}` in
`system/services.txt`, so `user@1000.service` is not rewritten as an email; and `NOPASSWD` is
protected before the password rules run, so a sudoers grant keeps its meaning.

Redaction is applied to copied config files and to every `system/*.txt` section. Package
inventories under `packages/` come from package-manager output: the npm, Cargo, pip, and
RubyGems listings are identity-scrubbed, while the pacman lists contain only names and
versions. `data/snapshot.json` is not re-run through `redact_text()` — its strings were already
redacted where they were produced — but it passes through `redact_identity()` and is covered by
the seal; `REPORT.md` is written from the same data and is sealed too. This is why exact
package versions and tool versions survive.

## What is deliberately retained

These are inventory facts, not identifiers to scrub:

- hostname (`plazir27`);
- package names and exact versions, tool versions, model identifiers used by agent clients;
- unit/service/timer names and their enablement state;
- hardware models, BIOS/firmware version and date, CPU microcode revision, GPU driver version;
- kernel command line, mount options, filesystem layout, LUKS parameters (cipher/keysize), with
  UUIDs replaced;
- interface names, listening ports, process names, firewall rule ports, container/image names;
- configuration content itself: Hyprland/Waybar/terminal/editor settings, theme files, shell
  startup logic, agent role definitions, and skill instructions;
- project directory names and the absolute manifest paths under `/home/user`.

The local account name and home path are **not** retained: the collector rewrites them to
`user` and `/home/user` in config contents, unit files, JSON strings, and sudoers filenames.

The `etc/sudoers.d/99-user-nopasswd` file (and `~/nvme1-scratch-sudoers`) is captured and
discloses that `user` has `NOPASSWD: ALL`. That is a policy statement, not a secret, and the
`NOPASSWD` keyword is deliberately preserved while the account name is scrubbed. Reviewers
should still know the privilege model is visible in the snapshot. The git identity is the
sanitized placeholder `ci <ci@local>`.

## Verified clean in the regenerated capture

The 2026-10-19 tree was regenerated at 21:13 local after the identity pass described above.
Inspection of the shipped files finds none of the earlier residuals:

- monitor EDID serials — the `hyprctl monitors` description ends in `<redacted>`;
- the ESP FAT volume identifier and every other `UUID=`/`PARTUUID=` value — all `<uuid>`;
- efibootmgr device-path GUID bytes — the `dp:` lines are gone and GPT identifiers are `<uuid>`;
- unbracketed IPv6 literals — validated tokens are `<ipv6>`, and only clock times remain as
  colon-separated digit groups;
- pre-redaction file hashes — the old per-file source hash was removed from `config_index`, so a
  hash can no longer confirm a guessed secret;
- MAC addresses, machine/boot IDs, and DMI serial numbers — none present; the only remaining
  dotted-quad shapes are software versions such as `610.57.4.0` and `1.4.3.3`.

## Residual limits

These are limits of the mechanism, not findings in the current tree:

1. **Thresholds leave short values in place.** Assignments shorter than the rule thresholds
   (for example an 8-character token) are not matched. Values that are `$`-prefixed are treated
   as indirection and kept.
2. **The secret-key list is fixed.** A credential stored under a name outside the list
   (`password`, `secret`, `token`, `api_key`, `access_key`, `refresh_token`, `client_secret`,
   `private_key`, `auth_token`, `org_id`, plus the `*_TOKEN`/`*_SECRET`/`*_PASSWORD`/
   `*_API_KEY`/`*_ACCESS_KEY`/`*_PRIVATE_KEY`/`*_AUTH_KEY` families) is not recognized.
3. **The identity scrub is literal.** Only the exact home path and account name are replaced.
   Other account or group names, other machines' hostnames in `/etc/hosts`, and the host's own
   name (`plazir27`, intentional) remain.
4. **Binary and non-UTF-8 files** are skipped whole by the NUL guard or decoded with replacement
   characters; skipped files are recorded as notes, and replacement characters can hide context
   from a reviewer.
5. **Regex, not a secret scanner.** Secrets split across lines, encoded in base64 or hex blobs,
   or embedded in binary content are not detected. A dedicated scanner is not part of the
   collector; the host has `gitleaks` installed, so run it separately over the staged tree for a
   second opinion.
6. **The seal is integrity, not privacy.** `ARTIFACTS.sha256` proves the tree is the one the
   collector wrote; it does not make the content safe. A capture that passes the allow-list and
   the redactor is published verbatim.

## Review before commit

`./bin/xsnapshot validate` proves integrity only (the seal, the artifact index, config hashes,
and package counts); it is **not** a privacy check. Before committing or publishing a capture:

1. Run `./bin/xsnapshot list` and `./bin/xsnapshot validate`, and confirm the artifact count and
   the seal digest it prints match what `collect` reported for that capture.
2. Read the `## Notes` section of `REPORT.md`. Any `skipped binary config`, `skipped symlink`,
   `unreadable config`, or `missing required config` line is a coverage change that deserves a
   look.
3. Inspect `config_index` in `data/snapshot.json`: each entry has a source label, path, size,
   post-redaction `snapshot_sha256`, and a redaction count. Files with `redactions: 0` were
   copied unchanged — read those by hand, because no rule fired on them.
4. Diff the tree (`git diff --stat`, then `git diff` for `etc/` and `applied/`). Do not
   `git add -A` a capture you have not read; commit the snapshot as its own change so a revert
   is possible.
5. Scan the staged tree for identifier shapes. A quick heuristic pass (expect false positives
   on package lists and timestamps):

   ```bash
   rg -n --hidden -g '!*.json' -g '!packages/**' \
     -e '\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b' \
     -e '\b([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b' \
     -e '(?<![\w:])([0-9A-Fa-f]{0,4}:){2,}[0-9A-Fa-f]{0,4}' \
     -e 'PARTUUID=' -e 'UUID=' -e 'machine-id' \
     -e '(?i)(token|secret|password|api[_-]?key)\s*[:=]\s*\S{12,}' \
     snapshots/<id>/
   ```

   Also grep for the *actual* account name and home path — the published tree must contain only
   `user` and `/home/user`:

   ```bash
   rg -n "$(id -un)" snapshots/<id>/
   ```

   These are heuristics, not proof; run a dedicated scanner such as `gitleaks` over the staged
   tree as a second opinion before publishing.
6. Confirm that any new file class added to `collect_configs()` was reviewed for secret content
   before the snapshot is committed, and update this document if the allow-list changed.
7. Because the repository is public, treat every commit as a publication event: re-collect with
   the current collector first, then re-run this review. The verified-clean checklist above must
   still hold (no UUID, MAC, IPv4/IPv6, machine-id, or serial hits; no account-name or home-path
   hits), and any residual limit that applies must be accepted by the operator for that capture.

## Reporting a leak

If a secret or unique identifier reaches a snapshot:

1. **Rotate first.** Revoke or rotate the credential before anything else. Removing it from the
   tree does not remove it from history, forks, or clones.
2. **Report privately to the owner.** Send the workstation operator the snapshot id, the
   artifact path, and the line, plus the rule that missed it. Do not paste the value into a
   public issue, chat, or pull request; the issue tracker is public, so reference the location
   instead of the content. This repository ships no `SECURITY.md` and defines no separate
   security contact, so the owner is the contact.
3. **Fix the cause.** Either remove the file from the allow-list in `collect_configs()`, add or
   tighten a rule in `redact_text()`, or add a guard to the copy path — then re-capture with
   `--force` and re-run the review. If the leak is a missing pattern, add a regression test
   under `tests/` so the rule is exercised.
4. **History rewrite is an operator decision.** Purging a public commit requires rewriting
   history and force-pushing; require explicit operator approval before doing either. Treat any
   value that was public as compromised regardless of the rewrite.

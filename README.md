# xsnapshot-pc — Workstation Inventory, 2026-10-19

> Captured **2026-10-19T21:13:22-03:00** on `plazir27` by `xsnapshot collect`
> (collector `1.0.0`, schema `xsnapshot/v1`, Python 3.14.7). This is the regenerated
> 2026-10-19 capture, produced after the identity-scrubbing privacy pass described in
> [`docs/PRIVACY.md`](docs/PRIVACY.md).
> The capture manifest is [`snapshots/2026-10-19/REPORT.md`](snapshots/2026-10-19/REPORT.md);
> the machine-readable form is [`snapshots/2026-10-19/data/snapshot.json`](snapshots/2026-10-19/data/snapshot.json);
> [`snapshots/2026-10-19/ARTIFACTS.sha256`](snapshots/2026-10-19/ARTIFACTS.sha256) seals every
> file in the snapshot except itself.
> This document is the human-readable inventory for that one capture.
>
> This is a descriptive snapshot, **not a backup**. Secrets and unique identifiers
> are excluded by an allow-list plus a defense-in-depth redactor; see
> [Privacy boundary](#privacy-boundary) and [`docs/PRIVACY.md`](docs/PRIVACY.md).

## About xsnapshot-pc

xsnapshot-pc records a single Linux workstation as a reviewable, sanitized tree that can be
diffed against a later capture. The collector is deliberately boring: Python 3 standard
library only, read-only inventory commands, no upload, no package installation, no mutation of
the host.

| Path | Purpose |
|---|---|
| `bin/xsnapshot` | Thin bash entry point; pins `--root` to this repository and execs the collector. |
| `lib/xsnapshot.py` | The collector: allow-listed file copy, redaction, command inventory, report/JSON writers. |
| `snapshots/<YYYY-MM-DD>/` | One directory per capture (`applied/`, `etc/`, `packages/`, `system/`, `data/`, `REPORT.md`). |
| `docs/` | The privacy policy and design notes: [`PRIVACY.md`](docs/PRIVACY.md) and [`WEBSITE.md`](docs/WEBSITE.md) (a future contract for a viewer website; no site is shipped). |
| `plans/<YYYY-MM-DD>-<topic>/` | Change plans for the machine, kept with their reviews and checked against a committed snapshot; written by hand, not by the collector. |
| `templates/`, `tests/` | Future capture templates (currently empty) and the stdlib unittest suite. |

Snapshot output is committed on purpose — `.gitignore` excludes only Python bytecode,
`__pycache__`, editor swap files, `.DS_Store`, `*.tmp`, and transient `/tmp`/`/scratch` paths.

The 2026-10-19 capture contains **237 artifacts**: 218 allow-listed configuration files
(143 under `applied/`, 75 under `etc/`), 9 subsystem files under `system/`, 8 inventory files
under `packages/`, `REPORT.md` itself, and the active-locale extract `etc/locale.gen.active`.
`ARTIFACTS.sha256` seals every file in the snapshot except itself (238 entries, 23,386 bytes);
`data/snapshot.json` (250,372 bytes) is excluded from `artifacts[]` but is covered by the seal.
The run recorded **110 read-only commands** and applied **170 redactions** (both
`data/snapshot.json` and `REPORT.md`), and reported **zero** skipped, unreadable, or missing
allow-listed files.

## Privacy boundary

This repository is public, so a committed snapshot is a published snapshot; the review gate in
[`docs/PRIVACY.md`](docs/PRIVACY.md) is mandatory for every capture, and the allow-list — not
the redactor — is the primary control.

The inventory is built from an allow-list of configuration files, not from a directory sweep,
and every copied file passes through the redactor before it is written. Excluded by design:
authentication tokens and API keys, password-manager data, SSH/GPG private keys, browser
profiles/cookies/history/local storage, shell and agent conversation histories, keyrings,
session state, caches, blobs, logs, and backups. Unique identifiers — machine and boot IDs,
partition/filesystem UUIDs, MAC and IP addresses, hardware serial numbers — are excluded as
well. What is intentionally kept is inventory-shaped: the hostname, package versions, tool
versions, service and unit names, hardware models, and firmware/BIOS versions. The local
account name and home path are not kept: every occurrence is replaced with `user` and
`/home/user` (including sudoers filenames and JSON strings), and the config index stores source
labels with `$HOME` compressed to `~`.

The redactor is a second line of defense, not the primary control; the allow-list in
`lib/xsnapshot.py` (`collect_configs`, `copy_file`, `copy_tree`) is. `docs/PRIVACY.md` states
the exact rule set, the verified-clean checks for the committed capture, the residual limits of
the mechanism, and the review procedure before a snapshot is pushed. Nothing in the collector
reaches the network: it shells out to local inventory commands only.

## Executive summary

| Area | Configuration |
|---|---|
| Host | `plazir27`, desktop, MSI MS-7E59 v2.0 / MAG X870E TOMAHAWK WIFI |
| Firmware | American Megatrends UEFI `2.AC3`, dated 2026-06-25, revision 5.41 |
| OS | Arch Linux rolling, Omarchy `3.8.3` (master, stable channel) |
| Kernel | Linux `7.2.3-arch1-3` (x86_64) |
| Boot | Limine `12.8.0` booting a unified kernel image, systemd-stub `261.2-1-arch`, Secure Boot disabled |
| CPU | AMD Ryzen 9 9950X, 16 cores / 32 threads, 624 MHz – 5.756 GHz, microcode `0xb404038` |
| GPU | NVIDIA GeForce RTX 5070, 12,227 MiB VRAM, driver `610.57.04`, 250 W cap; integrated AMD Granite Ridge Radeon |
| RAM | 2×16 GiB Kingston `KF560C30-16` in DIMMA2/DIMMB2, DDR5-6000, 30.3 GiB usable |
| Storage | WD_BLACK SN8100 1 TB NVMe; 2 GiB vfat `/boot` + 929.5 GiB LUKS2 Btrfs (`@`, `@home`, `@log`, `@pkg`) |
| Swap | 4 GiB zstd zram (priority 100) + 30.3 GiB Btrfs swapfile (priority 0, hibernate resume offset) |
| Display | LG ULTRAWIDE on DP-1, 3440×1440 at ~100 Hz, scale 1, `GDK_SCALE=1` |
| Desktop | Hyprland `0.56.2` (Wayland), Omarchy "Matte Black" theme, JetBrainsMono Nerd Font |
| Shell | Bash `5.3.15`, Starship `1.26.0`, fnm-managed Node.js `24.21.0` |
| Editor | Neovim `0.12.5`, LazyVim (51 locked plugins) |
| Terminal | Alacritty `0.17.0` (primary); Ghostty, Kitty, and Foot configs present; tmux `3.7c` |
| Containers | Docker `29.7.2` + containerd, cgroup v2, 6 images, 1 stopped container |
| Networking | Realtek RTL8126 5 GbE (`enp7s0`, up, DHCP); Qualcomm WCN785x Wi-Fi 7 (`wlan0`, down); UFW active |
| Package footprint | 1,348 pacman packages; 270 explicit; 16 foreign |
| Capture footprint | 218 allow-listed config files, 237 artifacts, 170 redactions, sealed by `ARTIFACTS.sha256` |

## Hardware

### Platform and firmware

- Vendor/model: Micro-Star International, `MS-7E59`, system version 2.0.
- Baseboard: MAG X870E TOMAHAWK WIFI (MS-7E59), version 2.0, hosting board, replaceable.
- Firmware: American Megatrends International UEFI `2.AC3` (2026-06-25), platform firmware
  revision 5.41, UEFI 2.110, 32 MiB ROM, upgradeable.
- Boot loader: Limine `12.8.0`; current entry `Omarchy.linux`; Secure Boot **disabled**;
  bootctl reports `TPM2 Support: no`, `Measured UKI: no`.
- SMBIOS 3.8.0 present; physical memory array supports up to 128 GiB over 4 slots; wake-up type
  "AC Power Restored". Chassis: desktop.
- Two DMI slots (DIMMA1, DIMMB1) are unpopulated; the populated pair is DIMMA2 + DIMMB2.

### Processor

- AMD Ryzen 9 9950X, family 26, model 68, stepping 0; 1 socket, 16 cores, 32 threads
  (`CPU(s): 0-31`), 2 threads per core.
- Observed frequency range 624.194 MHz – 5,756.4521 MHz; boost enabled, 65% scaling reported
  at capture; BogoMIPS 8599.99.
- Caches: 768 KiB L1d and 512 KiB L1i (16 instances each), 16 MiB L2, 64 MiB L3 (2 instances).
- Microcode `0xb404038`; `amd-ucode` installed; AMD-V exposed; AVX2 and the AVX-512 family
  exposed; one NUMA node.
- Hardware mitigations reported for Spec rstack overflow, Spec store bypass, Spectre v1/v2, and
  Vmscape; the other listed vulnerabilities report "Not affected".

### Graphics and compute

- Discrete: NVIDIA GeForce RTX 5070 (GB205), 12,227 MiB VRAM, power cap 250 W, 34 °C and
  973 MiB in use at capture; 0% fan.
- NVIDIA driver `610.57.04` (`nvidia-utils`, `nvidia-open-dkms`, `lib32-nvidia-utils`,
  `libva-nvidia-driver`); `nvidia_drm modeset=1` via `/etc/modprobe.d/nvidia.conf`;
  persistence mode off; CUDA UMD 13.3.
- Integrated: AMD Granite Ridge Radeon Graphics (`1002:13c0`) driven by RADV / Mesa 26.2.2;
  llvmpipe also enumerated; Vulkan instance 1.4.357; Vulkan layers include the NVIDIA
  Optimus/present layers and the Steam fossilize/overlay layers.
- Hyprland binds the NVIDIA adapter directly; the environment overlay sets
  `NVD_BACKEND=direct`, `LIBVA_DRIVER_NAME=nvidia`, `__GLX_VENDOR_LIBRARY_NAME=nvidia`.

### Memory and swap

- 2×16 GiB Kingston Fury `KF560C30-16`, 1 rank, DDR5-6000 configured (6000 MT/s), 1.1 V;
  30.3 GiB total (32,483,102,720 bytes), 9.8 GiB used and 20 GiB available at capture.
- zram: one 4 GiB zstd device at priority 100 (`/etc/systemd/zram-generator.conf` sets only
  `compression-algorithm = zstd`); 3.3 GiB of data, 1.4 GiB compressed, 1.5 GiB total at capture.
- Hibernate swap: `/swap/swapfile`, 30.3 GiB, priority 0, mounted through fstab; resume is
  configured as `resume=/dev/mapper/root resume_offset=3795013` in the kernel command line.
- No snapper configuration is registered (`snapper list-configs` is empty), although
  `limine-snapper-sync.service` is enabled and Limine keeps `MAX_SNAPSHOT_ENTRIES=5`.

### Storage and filesystems

- One NVMe device: WD_BLACK SN8100 1000GB (`nvme0n1`, 931.5 GB, non-rotational).
  - `nvme0n1p1`: 2 GiB vfat mounted at `/boot` (279 MiB used), firmware-visible ESP.
  - `nvme0n1p2`: 929.5 GiB `crypto_LUKS` (LUKS2, aes-xts-plain64, 512-bit key, keyring unlock)
    opened as `/dev/mapper/root`.
- Btrfs subvolumes with `rw,relatime,compress=zstd:3,ssd,space_cache=v2`:
  `@` → `/`, `@home` → `/home`, `@log` → `/var/log`, `@pkg` → `/var/cache/pacman/pkg`.
- Usage at capture: 241 GiB of 930 GiB (27%); data profile `single`, metadata `DUP`, system
  `DUP`; 512 MiB global reserve.
- Transient USB media were mounted at capture (a 23.9 GB iso9660 stick as `sda` with a 7.4 GB
  partition, and a 21.5 GB USB CD-ROM as `sr0`); they are not part of the installed system.
- `/tmp` is tmpfs (15.1 GiB limit); `/run/user/1000` is tmpfs.

### Networking and peripherals

- Wired: Realtek RTL8126 5 GbE (`enp7s0`), up, DHCP lease, route metric 100, default route.
- Wireless: Qualcomm WCN785x Wi-Fi 7 / FastConnect 7800 (`wlan0`), administratively up but
  `NO-CARRIER`; `iwd` running; both radios unblocked by rfkill.
- Bluetooth controller present and unblocked (Foxconn/Hon Hai `0489:e10a`); `bluetooth.service`
  running; `bolt.service` running for the ASM4242 USB4 / Thunderbolt 3 router.
- Docker bridge `docker0` present but down; no volumes.
- Display: LG ULTRAWIDE over DP-1, 3440×1440 at 99.997 Hz, scale 1, 800×330 mm, sRGB preset,
  VRR off, hardware cursors not in use; modes up to 3440×1440@100 and 1920×1080@119.88.
- USB peripherals: HyperX Alloy Origins Core keyboard, Razer DeathAdder V2 mouse, Yubico
  YubiKey 4/5 (OTP+U2F+CCID), Sony DualSense controller, MSI USB Audio, MSI MYSTIC LIGHT,
  and a generic "USB Disk 20" mass-storage device.
- Audio: PipeWire/WirePlumber `1.6.8`; sinks include the RTX 5070 HDMI output, the DualSense
  output, and a USB Audio device (S/PDIF, speakers, front headphones); the default sink is the
  HDMI stereo output, default source the USB Audio line input.

## Operating system and boot

- Arch Linux rolling release (`ID=arch`), `PRETTY_NAME="Arch Linux"`, kernel
  `7.2.3-arch1-3`, x86-64.
- Omarchy `3.8.3`, branch `master`, channel `stable`; last package update recorded as
  Friday, 2026-10-16 23:53.
- PACMAN: `core`, `extra`, `multilib`, plus the `omarchy` repository
  (`SigLevel = Optional TrustAll`) and an `openai-chatgpt` include; `ParallelDownloads = 5`,
  `DownloadUser = alpm`, `VerbosePkgLists`, `ILoveCandy`.
- Boot chain: UEFI → Limine `12.8.0` → unified kernel image
  `EFI/Linux/omarchy_linux.efi` (systemd-stub `261.2-1-arch`). `limine-entry-tool` owns the
  entry: `ENABLE_UKI=yes`, `CUSTOM_UKI_NAME=omarchy`, `ENABLE_VERIFICATION=yes`,
  `ENABLE_LIMINE_FALLBACK=yes`, `FIND_BOOTLOADERS=yes`, `MAX_SNAPSHOT_ENTRIES=5`,
  `BOOT_ORDER="*, *fallback, Snapshots"`. `limine.conf` uses `default_entry: 2`, the
  "Omarchy Bootloader" branding, a Tokyo Night palette, and `hash_mismatch_panic: no`.
- Kernel command line (sanitized): `resume=/dev/mapper/root resume_offset=3795013 quiet splash
  loglevel=0 systemd.show_status=false rd.udev.log_level=0 vt.global_cursor_default=0
  cryptdevice=PARTUUID=<uuid>:root root=/dev/mapper/root zswap.enabled=0 rootflags=subvol=@ rw
  rootfstype=btrfs`.
- initramfs (`/etc/mkinitcpio.conf`): `HOOKS=(base udev autodetect microcode modconf kms
  keyboard keymap consolefont block encrypt filesystems fsck)`; no extra `MODULES`, `BINARIES`,
  or `FILES`; compression left at the mkinitcpio default (zstd).
- EFI boot order: Limine (`Boot0000`), `UEFI OS` fallback (`Boot0004`), USB `ProductCode`
  (`Boot0003`); timeout 1 s.
- Encryption: root opened by the initramfs `encrypt` hook using
  `cryptdevice=PARTUUID=<uuid>:root`; `/etc/crypttab` defines no additional volumes.
- systemd is the init and service manager; `systemd-udevd`, `systemd-journald`,
  `systemd-logind`, `systemd-hostnamed`, `systemd-userdbd` all running.
- Networking: `systemd-networkd` (DHCP, `RouteMetric=100` for both DHCPv4 and IPv6 RA) +
  `systemd-resolved` (stub resolver, DNS-over-TLS off, DNSSEC unsupported, LLMNR on, mDNS off
  via `/etc/systemd/resolved.conf.d/10-disable-multicast.conf`; a Docker-specific DNS drop-in
  exists as well) + `iwd` for Wi-Fi + `systemd-timesyncd` (synchronized, NTP active).
- Firewall: UFW `0.36.2`, `ENABLED=yes`, logging `low`, default `deny (incoming),
  allow (outgoing), deny (routed)`. Rules: 53317/udp and 53317/tcp (LocalSend), plus UDP 53
  from the Docker bridge and Docker network ranges for container DNS.
- Display manager: SDDM `0.21.0` on Wayland
  (`CompositorCommand=start-hyprland -- --config /usr/share/sddm/hyprland.conf`), theme
  `omarchy`, autologin into session `omarchy` (the account name is written as `user`).
- Locale/time: `LANG=en_US.UTF-8`; console keymap `br-abnt2`, X11 layout `br` / model `abnt2`
  with `terminate:ctrl_alt_bksp`; time zone `America/Sao_Paulo` (-03), RTC in UTC, clock
  synchronized.
- Logind: `HandlePowerKey=ignore`; long-press suspend/hibernate keys left at systemd defaults.
  Journal: `SystemMaxUse=256M`, `RuntimeMaxUse=64M`. Coredumps: `MaxUse=512M`,
  `KeepFree=8G`. Shutdown grace: `DefaultTimeoutStopSec=5s`. File descriptors:
  `DefaultLimitNOFILE=65536:524288`; `fs.inotify.max_user_watches=524288`;
  `net.ipv4.tcp_mtu_probing=1`; USB autosuspend disabled (`usbcore autosuspend=-1`).
- `/etc/fstab` mounts the four Btrfs subvolumes by UUID and the ESP by its FAT volume ID; every
  volume identifier is written as `<uuid>` in the committed capture.

## Desktop and user experience

### Omarchy and Hyprland

- Hyprland `0.56.2` (tag `v0.56.2`, commit `efb5099…`, built 2026-08-05), Wayland session
  `wayland-1`, `XDG_CURRENT_DESKTOP=Hyprland`, `DESKTOP_SESSION=omarchy`.
- The user config sources Omarchy's defaults (autostart, media/clipboard/tiling-v2/utilities
  bindings, envs, looknfeel, input, windows), then `~/.config/omarchy/current/theme/hyprland.conf`,
  then five personal overlays — `monitors.conf`, `input.conf`, `bindings.conf`,
  `looknfeel.conf`, `autostart.conf` — then Omarchy state toggles, plus `ai-usage.conf` and
  `gkeep.conf`.
- Theme: "Matte Black" (`~/.config/omarchy/current/theme.name` = `matte-black`), with the active
  border color `rgb(e68e0d)` from the theme; look-and-feel overrides are present but commented,
  so Omarchy defaults supply gaps, borders, rounding, and animations.
- Monitor policy: `monitor = DP-1, 3440x1440@100, 0x0, 1`, `env = GDK_SCALE,1`.
- Input policy: `kb_layout = br`, `kb_options = compose:caps`, repeat rate 40/s with 250 ms
  delay, Num Lock on by default, touchpad clickfinger behavior and 0.4 scroll factor; terminal
  classes get `scroll_touchpad` tuning (1.5 for Alacritty/Kitty/Foot, 0.2 for Ghostty).
- Idle: Hypridle launches the screensaver at 150 s and locks at 152 s, locks before sleep,
  wakes the display after sleep, and waits up to 3 s for the lock before inhibiting sleep.
  Hyprlock blurs the theme background (3 passes) with a 650×100 input field, disabled
  fingerprint auth, and `ignore_empty_input`.
- Night light: Hyprsunset runs an identity profile at 07:00, so no tint is applied; the
  auto-warm profile is present only as a commented example. Autostart launches the Grok Bot
  AppImage with `--ozone-platform=x11`.
- Screen sharing: XDPH is configured with `allow_token_by_default = true` and the
  `hyprland-preview-share-picker` binary.

### Primary bindings

| Binding | Action |
|---|---|
| Super+Return | Terminal (`xdg-terminal-exec` in the current directory) |
| Super+Alt+Return | tmux session `Work` in a terminal |
| Super+Shift+Return / Super+Shift+B | Browser |
| Super+Shift+F | Nautilus |
| Super+Shift+N | Editor (Omarchy launcher) |
| Super+Shift+D | Lazydocker |
| Super+Shift+G | Signal |
| Super+Shift+O | Obsidian |
| Super+Shift+W | Typora with Wayland IME |
| Super+Shift+/ | 1Password |

Web-app bindings are configured for ChatGPT, Grok, HEY Calendar, HEY Mail, YouTube, WhatsApp,
Google Messages, Google Photos, and X (plus a compose-post variant). Media, brightness,
screenshot, notification, workspace, and tiling bindings come from the Omarchy defaults; the
full resolved binding table is in `snapshots/2026-10-19/system/desktop.txt`.

### Waybar

- Waybar `0.15.0`, top layer, 26 px high, spacing 0, style hot-reload enabled.
- Left: Omarchy menu, Hyprland workspaces (1–5 persistent).
- Center: clock (with a secondary `Asia/Shanghai` clock), weather, update indicator, dictation
  state, screen-recording, idle and notification-silencing indicators.
- Right: tray expander group, gkeep, AI-usage meter, Bluetooth, network, audio, CPU, battery.
- Click actions route to Omarchy menus/launchers (`omarchy-menu`, `omarchy-launch-wifi`,
  `omarchy-launch-audio`, `omarchy-launch-bluetooth`, btop, tz selector, power menu).

### Terminals and tmux

- Alacritty `0.17.0`: imports the current Omarchy theme, `TERM=xterm-256color`, OSC 52
  `CopyPaste`, JetBrainsMono Nerd Font 12.5 pt, 14 px padding, no decorations, explicit CSI-u
  encodings for Shift+Enter and Alt+Shift+Enter, Shift+Insert/Ctrl+Insert paste/copy.
- Ghostty: imports the theme file, same font and 14 px padding, block non-blinking cursor,
  `epoll` async backend, Shift+Enter/Alt+Shift+Enter CSI-u bindings, 0.95 mouse-scroll
  multiplier, shell integration with `no-cursor,ssh-env`.
- Kitty (`kitty.conf`) and Foot (`foot.ini`) configs are captured as well.
- tmux `3.7c`: the active file is `~/.config/tmux/tmux.conf` — prefix `C-Space` with `C-b`
  fallback, vi copy mode, mouse, RGB/truecolor overrides, OSC 52 clipboard, 50,000-line
  history, windows and panes numbered from 1, top status bar, extended keys in CSI-u. It
  sources the fleet overlay `~/.tmux.conf`, which turns on pane-border labels (with DEAD/COPY/
  SYNC flags), 100,000-line scrollback, stable window numbering, `detach-on-destroy off`, and
  vim-style pane movement.

### Shell, prompt, fonts

- Bash `5.3.15`. `~/.bashrc` puts `~/.local/bin`, `~/.opencode/bin`, and the fnm shim ahead of
  system paths, deduplicates `PATH`, initializes fnm before the interactive guard (so
  non-interactive `bash -lc` also resolves fnm's Node), re-asserts fnm after Omarchy's
  `mise activate`, and registers fnm's on-cd hook through zoxide's `chpwd_functions`.
- Node.js `24.21.0` comes from fnm; mise is installed but manages nothing (`[tools]` is empty).
- Starship `1.26.0` renders directory (truncated to 2 components), git branch/status, and a
  cyan `❯`/`✗` prompt with a 200 ms command timeout.
- Environment wiring in `.bashrc` exports `GHIDRA_INSTALL_DIR`, `JAVA_HOME` (JDK 21), and the
  REA tool paths (binwalk, unblob, apktool, adb, Wakaru, the JADX MCP jar, and a pwntools
  venv), and generates provider tokens from local helper commands at shell start — token
  values are not stored in the snapshot.
- Fonts: JetBrainsMono Nerd Font (12.5 pt in terminals), Noto families, Font Awesome 7,
  Liberation Sans/Serif/Mono; fontconfig maps `sans-serif` → Liberation Sans,
  `serif` → Liberation Serif, `monospace` → JetBrainsMono Nerd Font, with Noto Color Emoji as
  an accepted fallback for all three.
- Input method: Fcitx5 profile and `conf/` files are captured (`xcb`, clipboard,
  notifications); `environment.d/fcitx.conf` sets `INPUT_METHOD`, `QT_IM_MODULE`, `XMODIFIERS`,
  and `SDL_IM_MODULE` to fcitx, and `environment.d/ssh-agent.conf` points `SSH_AUTH_SOCK` at
  `$XDG_RUNTIME_DIR/ssh-agent.socket`, which is enabled as a user socket.

## Developer environment

### Core tools

| Tool | Version at capture |
|---|---|
| Bash | 5.3.15(1) |
| Git | 2.55.0 |
| GitHub CLI | 2.102.0 |
| Neovim | 0.12.5 |
| tmux | 3.7c |
| Docker | 29.7.2 (build a7dcaa6fdb) |
| Docker Compose | 5.5.1 |
| Make | 4.4.1 |
| GCC | 16.2.1 |
| Clang/LLVM | 22.1.8 |
| GDB | 17.2 |
| Java | OpenJDK 21.0.12.1 |
| Lua | 5.5.1 |
| LuaRocks | 3.13.0 |

CMake and Go are **not** installed on `PATH`; `bun` is not installed; `dotnet` fails to load
("The command could not be loaded…"); there is no .NET SDK. Reverse-engineering tooling is
present: Ghidra, radare2 6.2.0, rizin 0.8.2, apktool 3.0.3, binwalk 3.1.0, plus Android
platform tools and JADX in the package set.

### Language runtimes

| Runtime | Version / state |
|---|---|
| Node.js | 24.21.0 (fnm default) |
| npm | 11.19.0 |
| pnpm | 12.11.2 (global) |
| Deno | 2.9.6 (stable, x86_64-unknown-linux-gnu) |
| Python | 3.14.7 (system) |
| Ruby | 3.4.10 +PRISM |
| Rust | rustc/cargo 1.98.1 (Arch `rust 1:1.98.1-1`) |
| .NET | `dotnet-host 10.0.11.sdk111-1` with `dotnet-runtime-10.0` and `dotnet-runtime-9.0`; the `dotnet` command fails to load, and no SDK package is installed |
| CUDA | UMD 13.3 (driver-reported) |

No user-level Python packages (`pip-user.txt` → none) and no Cargo-installed binaries
(`cargo-installed.txt` → none); Ruby has only its default gem set.

### Global language packages

npm globals, all under the fnm Node 24.21.0 prefix:

```text
@gltf-transform/cli@4.5.1
@openai/codex@0.163.0
agent-browser@0.38.2
corepack@0.36.0
godot-mcp@0.1.0
npm@11.19.0
pixelmatch@8.0.0
playwright@1.64.0
pnpm@12.11.2
solc@0.8.37
wakaru@1.14.0
```

### Git policy

- `init.defaultBranch = master`; `pull.rebase = true`; `push.autoSetupRemote = true`.
- `diff.algorithm = histogram`, `diff.colorMoved = plain`, `diff.mnemonicPrefix = true`;
  `commit.verbose = true`; `column.ui = auto`.
- `branch.sort = -committerdate`; `tag.sort = -version:refname`; `rerere.enabled = true` with
  `rerere.autoupdate = true`.
- Aliases: `co`, `br`, `ci`, `st`.
- Identity is the sanitized placeholder `ci <ci@local>`; GitHub credentials are delegated to
  `gh auth git-credential`, and Cursor's origin helper is configured for
  `origin.cursor.com`. No credential value is stored in this repository.

### Neovim

- Neovim `0.12.5` with LazyVim (`install_version` 8) and the `editor.neo-tree` extra.
- `lazy-lock.json` pins 51 plugins, including LazyVim, lazy.nvim, neo-tree, blink.cmp,
  conform, nvim-lspconfig, Mason, Treesitter, snacks, noice, trouble, which-key, gitsigns, and
  a large set of theme packages.
- Custom Lua: `config/options`, `keymaps`, `autocmds`, `lazy`, `remote_clipboard`;
  `plugins/all-themes`, `theme` (pins `tahayvr/matteblack.nvim` with the `matteblack`
  colorscheme), `omarchy-theme-hotreload`, `snacks-animated-scrolling-off`,
  `disable-news-alert`; `plugin/after/transparency.lua`; `stylua.toml` and `.neoconf.json`.
- `init.lua` only bootstraps `config.lazy`, which clones lazy.nvim (stable) into the data dir
  when missing.

### Agent stack

- OMP (`~/.omp/agent/config.yml`, 5.5 KiB): 13 agent definitions, `approvalMode: yolo`,
  `maxConcurrency: 100`, `maxRecursionDepth: 2`, eager subagents, model fallback on,
  `autoqaConsent: granted`. Model roles include `default: anthropic/claude-opus-5-5:max`,
  `plan`/`m_fast: opencode-go/deepseek-v4.1-flash:max`, `m_strong/m_sol` (GPT-6.1 Sol),
  `m_glm53: zai/glm-5.3`, `m_grok: cursor/grok-4.7-fast`, `m_swe: devin/swe-2`,
  `m_k3: kimi-code/k3`, and `web: web/perplexity`.
- Devin (`~/.config/devin/`): 28 agent definitions, dark theme, default model `swe-2-max`,
  MCP config captured.
- Skills: `godspeed` and `reverse-engineer-anything` under `~/.agents/skills` (10 files).
- Other captured agent clients: OpenCode (`cli.json`, `opencode.json`), Codex
  (`~/.codex/config.toml`), Grok (`~/.grok/config.toml`), kimi-code (`~/.kimi-code/tui.toml`),
  Claude (`~/.claude/settings.json` = `{"theme":"dark"}`).

### Workspace

- 20 project directories under `~/Projects`: BTVREV, TPSnCONC, audio-shokunin-publish,
  burnerchrome, gamez, gkeep, godspeed-core, kimi-code, kimi-shokunin, myskills,
  omarchy-usage-tray, ompskills, opencodeufo, prymeagnt, prymeagnt-archive, shokunin,
  the-kimiraikkoner, tog, ufo-fsd-alpha, xsnapshot.
- Declared manifests found at capture: `kimi-code/package.json` (+ `docs/package.json`),
  `tog/package.json`, `ufo-fsd-alpha/Cargo.toml`, `ufo-fsd-alpha/package.json`. Source trees and
  lockfile bodies are not copied into the snapshot; the manifests remain authoritative.

## Services

### Enabled system units

`avahi-daemon.service` and `.socket`, `bluetooth.service`, `cups.path`, `cups.service` and
`.socket`, `cups-browsed.service`, `docker.socket`, `getty@.service`, `iwd.service`,
`limine-snapper-sync.service`, `linux-modules-cleanup.service`, `remote-fs.target`,
`sddm.service`, `systemd-network-generator.service`, `systemd-networkd.service` and its
`.socket`/varlink/resolve-hook sockets, `systemd-resolved.service` and its monitor/varlink
sockets, `systemd-timesyncd.service`, `systemd-userdbd.socket`, `ufw.service`.

### Running system services

`avahi-daemon`, `bluetooth`, `bolt`, `containerd`, `cups`, `cups-browsed`, `dbus-broker`,
`docker` (socket-activated), `iwd`, `polkit`, `power-profiles-daemon`, `sddm`, `snapperd`,
`systemd-hostnamed`, `systemd-journald`, `systemd-logind`, `systemd-networkd`,
`systemd-resolved`, `systemd-timesyncd`, `systemd-udevd`, `systemd-userdbd`, `upower`, and the
per-user manager for UID 1000 (`user@1000.service`). No failed system or user units at capture.

Maintenance timers scheduled: `shadow.timer`, `plocate-updatedb.timer`, `man-db.timer`,
`systemd-tmpfiles-clean.timer`, `archlinux-keyring-wkd-sync.timer`.

### Enabled user units

- Services: `antigravity-shim`, `claude-shim`, `codex-shim`, `cursor-shim`, `devin-shim`,
  `ds-flash-shim`, `elephant`, `glm-flash-shim`, `omarchy-recover-internal-monitor`,
  `swayosd-server`, `wireplumber`, `xai-shim`, `xdg-user-dirs`.
- Sockets: `gnome-keyring-daemon`, `p11-kit-server`, `pipewire`, `pipewire-pulse`,
  `ssh-agent`.
- Timers: `ai-usage.timer` (refresh every 5 minutes), `cursor-shim-healthcheck.timer`.

The shim services are local OpenAI-compatible translation proxies for agent clients
(Claude OAuth, Codex OAuth, Cursor backend, Devin Connect-RPC, xAI OAuth, and two cascade
shims); their endpoint credentials live outside the snapshot. Running session services also
include `xdg-desktop-portal` (GTK, Hyprland, document portal, permission store), `dconf`,
`gvfs-daemon`, `gvfs-metadata`, `at-spi-dbus-bus`, the Hyprland session unit, and the Walker
launcher.

## Repeatable capture

`bin/xsnapshot` forwards to `lib/xsnapshot.py` with the repository root pinned. Python 3 is the
only dependency.

```bash
# Capture a new snapshot into snapshots/<local date>/
./bin/xsnapshot collect

# Explicit id, custom output directory, or replace an existing capture
./bin/xsnapshot collect --snapshot 2026-11-02
./bin/xsnapshot collect --out /tmp/scratch-snapshot
./bin/xsnapshot collect --force            # required when the target exists

# Skip all root-only reads (no `sudo -n`); privileged files are then omitted
./bin/xsnapshot collect --no-sudo

# Verify the newest snapshot (or a named one): the ARTIFACTS.sha256 seal covers
# every file, the artifact index is an exact set, and config-index hashes and
# package counts agree
./bin/xsnapshot validate
./bin/xsnapshot validate snapshots/2026-10-19

# List snapshots newest-first with their capture timestamps
./bin/xsnapshot list
```

Behavior notes:

- `collect` stages the target directory itself and refuses to overwrite an existing snapshot
  unless `--force` is given (exit code 2). It prints the artifact count, redaction count, and
  the paths to `REPORT.md` and `data/snapshot.json` when finished.
- Root-owned files are read through `sudo -n` when passwordless sudo is available; otherwise
  they are recorded as missing in `REPORT.md`'s notes instead of being approximated.
- `validate` verifies the `ARTIFACTS.sha256` seal (exact file set and every hash), rejects
  unlisted or missing files, checks the artifact index for exact membership, size, and hash,
  re-hashes every `config_index` entry, and confirms the package counts against the captured
  lists; it prints the seal digest on success. It does not re-run privacy checks, so a passing
  `validate` is an integrity result, not a privacy review.
- `list` reads `captured_at` from each `data/snapshot.json`; an unparsable file is reported as
  `invalid-json` rather than hidden.
- A capture is written under the repository and never uploaded; review it before committing
  (see [`docs/PRIVACY.md`](docs/PRIVACY.md)).

## Explicit Arch package set

270 explicitly installed packages at capture; 1,348 packages installed in total, of which 16
are foreign. Versions are capture-time versions, reproduced verbatim from
`packages/pacman-explicit.txt`.

```text
1password-beta 8.12.42_34.BETA-1
1password-cli 2.41.0-1
7zip 26.03-1
aether 4.32.0-2
alacritty 0.17.0-1
alsa-utils 1.2.16-1
amd-ucode 20260810-2
android-apktool-bin 3.0.3-1
android-tools 37.0.0-5
asdcontrol 1:0.6.0-2
audacity 1:3.7.9-1
base 3-3
base-devel 1-2
bash-completion 2.18.0-1
bat 0.26.1-2
binwalk 3.1.0-1
blender 17:5.2.1-2
bluetui 0.8.1-2
bolt 0.9.11-3
brightnessctl 0.5.1-3
btop 1.4.7-1
btrfs-progs 7.1-1
chatgpt-bin 26.1013.40934-1
chromium 152.0.7977.82-1
clang 22.1.8-1
claude-code 2.1.302-1
cliamp 2.3.0-3
cmark 0.31.2-1
cups 2:2.4.19-1
cups-browsed 2.1.1-1
cups-filters 2.0.1-2
cups-pdf 3.0.3-1
dmidecode 3.7-1
docker 1:29.7.2-1
docker-buildx 0.37.0-1
docker-compose 5.5.1-1
dosfstools 4.2-5
dotnet-runtime-9.0 9.0.19.sdk120-1
dust 1.2.5-1
efibootmgr 18-4
evince 1:48.4-1
exfatprogs 1.4.3-1
expac 10-13
eza 0.23.5-2
fastfetch 2.68.1-1
fcitx5 5.1.22-1
fcitx5-gtk 5.1.7-1
fcitx5-qt 5.1.15-1
fd 10.5.0-3
ffmpegthumbnailer 2.3.1-1
fluidsynth 2.6.0-1
fontconfig 2:2.18.3-2
freerdp 2:3.31.1-1
fuse2 2.9.9-6
fzf 0.74.3-1
git 2.55.0-1
git-filter-repo 2.47.0-3
git-lfs 3.8.0-1
github-cli 2.100.0-1
gitleaks 8.30.1-1
gnome-calculator 50.0-1
gnome-disk-utility 46.1-3
gnome-keyring 1:50.0-1
gnome-themes-extra 1:3.28-1
godot 4.7.2-1
gpu-screen-recorder 6.1.0-1
grim 1.5.0-2
gst-plugin-pipewire 1:1.6.8-1
gum 2.0.0-1
gvfs-mtp 1.60.2-4
gvfs-nfs 1.60.2-4
gvfs-smb 1.60.2-4
hypridle 0.1.8-2
hyprland 0.56.2-2
hyprland-guiutils 0.2.2-3
hyprland-preview-share-picker 0.2.1-1
hyprlock 0.9.6-3
hyprpicker 0.4.7-4
hyprsunset 0.4.0-3
imagemagick 7.1.2.31-1
impala 0.9.0-1
imv 5.0.1-2
inetutils 2.8-1
inkscape 1.4.4-6
inxi 3.3.41.1-1
iwd 3.12-1
jadx 1.5.6-1
jdk21-openjdk 21.0.12.1.u1-1
jq 1.8.2-1
kdenlive 26.08.0-1
kernel-modules-hook 0.1.7-3
krita 6.0.3-2
kvantum-qt5 1.1.8-1
lazydocker 0.25.2-1
lazygit 0.65.0-1
less 1:704-1
lib32-nvidia-utils 610.57.04-1
lib32-vulkan-radeon 1:26.2.2-1
libpulse 17.0+r98+gb096704c0-1
libqalculate 5.12.0-1
libreoffice-fresh 26.8.0-2
libretro-beetle-pce 20260411.153115.gae99235c2139-1
libretro-beetle-pce-fast 20260828.151513.g2f623abd0332-1
libretro-beetle-psx 20260902.124635.gb4bca9f86817-1
libretro-beetle-psx-hw 20260902.124635.gb4bca9f86817-1
libretro-beetle-supergrafx 20260420.173343.g3c6fcd3deded-1
libretro-blastem 20260902.212710.gb4d75247ebad-1
libretro-bsnes 1:20260812.183208.g6d19eef5835a-1
libretro-bsnes-hd 20251205.215259.gfc26b25ea236-1
libretro-cap32-git 1:4.5.4.r51.g4abfb8b-1
libretro-core-info 1.22.2-1
libretro-database-git 1:1.22.1.r200.g9aec589-1
libretro-desmume 20260823.072757.g8f6b32cb9a5e-1
libretro-dolphin 20260902.223111.ge1e6d25fa139-1
libretro-fbneo-git 1:1.0.0.02.r8581.g074bf13-1
libretro-flycast 20260903.141123.g8f511f896042-1
libretro-gambatte 20260821.105908.gd9d6cd06382d-1
libretro-genesis-plus-gx 20260605.160836.gf2b40ca6c97b-1
libretro-kronos 20260901.155445.g3791ffb2221f-1
libretro-mame 20260820.100011.g24cffe763621-1
libretro-melonds 20260719.185838.g66b5d2634cd0-1
libretro-mesen 20241218.081837.ge1180957b319-1
libretro-mesen-s 20241218.084431.g1768b4fc83fa-1
libretro-mgba 20260403.212340.g6dce57eef127-1
libretro-mupen64plus-next 1:20260806.132731.gf275caf4b2bf-1
libretro-nestopia 1:20260830.234256.g50dd0651ab46-1
libretro-overlays 20260624.142726.gd89fb7f05d65-2
libretro-parallel-n64 20260903.191659.g2f3bf60dcd96-1
libretro-picodrive 20260402.125053.gf0d4a0118a97-1
libretro-play 20260903.184445.g83700b2c31e5-1
libretro-ppsspp 20260903.192221.g410939fc5eed-1
libretro-sameboy 20260722.225329.gaa158a889a48-1
libretro-scummvm 20260826.133028.g825fea130aba-1
libretro-shaders-slang 20260620.024025.g8ec4c82cf61a-1
libretro-snes9x 1:20260816.181733.g890b5d445538-1
libretro-uae-git 1720.232ec89b-1
libretro-vice-x128-git r21255.fdda9d0-1
libretro-vice-x64-git r21255.fdda9d0-1
libretro-vice-x64dtv-git r21255.fdda9d0-1
libretro-vice-x64sc-git r21255.fdda9d0-1
libretro-vice-xcbm2-git r21255.fdda9d0-1
libretro-vice-xcbm5x0-git r21255.fdda9d0-1
libretro-vice-xpet-git r21255.fdda9d0-1
libretro-vice-xplus4-git r21255.fdda9d0-1
libretro-vice-xscpu64-git r21255.fdda9d0-1
libretro-vice-xvic-git r21255.fdda9d0-1
libretro-yabause 20260530.083400.g8926b0c6c347-1
libva-nvidia-driver 0.0.18-1
libyaml 0.2.5-3
limine 12.8.0-1
limine-mkinitcpio-hook 1.38.0-1.1
limine-snapper-sync 1.31.0-1.1
linux 7.2.3.arch1-3
linux-firmware 20260810-2
linux-headers 7.2.3.arch1-3
llvm 22.1.8-2
localsend 1.18.2-1
love 11.5-3
luarocks 3.13.0-5
lychee 0.24.2-2
mako 1.11.0-1
man-db 2.13.1-2
mariadb-libs 12.3.3-2
mesa-utils 9.0.0-7
mise 2026.9.1-1
mkinitcpio 41.1-1
mpv 1:0.41.0-6
nautilus 50.3.1-1
nautilus-python 4.1.0-3
neovim 0.12.5-1
noto-fonts 1:2026.09.01-1
noto-fonts-cjk 20240730-1
noto-fonts-emoji 1:2.051-1
nss-mdns 0.15.1-2
nvidia-open-dkms 610.57.04-1
nvidia-utils 610.57.04-1
obs-studio 32.2.2-1
obsidian 1.13.7-2
obsidian-cli-inspector 1.0.3-1
omarchy-keyring 20251027-1
omarchy-nvim 2026.8.13-1
omarchy-walker 1.0.0-2
openbsd-netcat 1.238_1-1
oxipng 10.2.1-1
pamixer 1.6-4
pinta 3.1.2-2
pipewire 1:1.6.8-1
pipewire-alsa 1:1.6.8-1
pipewire-jack 1:1.6.8-1
pipewire-pulse 1:1.6.8-1
playerctl 2.4.1-5
plocate 1.1.25-1
plymouth 26.134.222-2
pngquant 3.0.3-3
polkit-gnome 0.105-12
postgresql-libs 18.6-1
power-profiles-daemon 0.30-1
python-gobject 3.56.3-1
python-poetry-core 2.4.1-1
python-pygame 2.6.1-6
python-terminaltexteffects 0.15.0-1
qt5-wayland 5.15.19+kde+r55-1
radare2 6.2.0-1
retroarch 1.22.2-5
retroarch-assets-glui 1:20260411.201626.gcd17f64cff4e-1
retroarch-assets-ozone 1:20260411.201626.gcd17f64cff4e-1
retroarch-assets-xmb 1:20260411.201626.gcd17f64cff4e-1
retroarch-joypad-autoconfig-git 1.22.0.r96.g0331510-1
ripgrep 15.2.0-1
rizin 0.8.2-2
ruby 3.4.10-1
rust 1:1.98.1-1
satty 0.22.0-1
sddm 0.21.0-7
shellcheck 0.11.0-158
shfmt 3.14.1-1
signal-desktop 8.26.0-1
slurp 1.5.0-2
snapper 0.13.1-3
socat 1.8.1.3-1
soundfont-fluid 3.1-5
sox 14.8.0.1-1
spotify 1:1.3.4.258-1
starship 1.26.0-1
steam 1.0.0.87-3
strace 7.0-1
sudo 1.9.17.p2-6
sushi 50.0-1
swaybg 1.2.2-1
swayosd 0.3.2-1
system-config-printer 1.5.18-7
tesseract 5.5.3-1
tesseract-data-eng 2:4.1.0-5
tiled 1.12.2-1
tinyxxd 1.3.16-1
tldr 3.4.4-1
tmux 3.7_c-1
tobi-try 1.10.1-3
tree-sitter-cli 0.26.9-1
ttf-dejavu 2.37+18+g9b5d1b2f-8
ttf-ia-writer 20261002.r63-3
ttf-jetbrains-mono-nerd 3.5.1-2
typora 1.14.9-2
tzupdate 3.1.0-2
ufw 0.36.2-7
ufw-docker 251123-2
unzip 6.0-23
upx 5.2.0-1
usage 5.1.0-1
uwsm 0.26.7-1
vulkan-radeon 1:26.2.2-1
vulkan-tools 1.4.357.0-1
waybar 0.15.0-3
wget 1.25.0-6
whois 5.6.6-1
wireless-regdb 2026.05.30-1
wiremix 0.11.0-1
wireplumber 0.5.17-1
wl-clipboard 1:2.3.0-1
woff2-font-awesome 7.3.1-1
xdg-desktop-portal-gtk 1.15.3-1
xdg-desktop-portal-hyprland 1.4.1-2
xdg-terminal-exec 0.14.3-1
xmlstarlet 1.6.1-6
xorg-server-xvfb 21.1.24-1
xournalpp 1.3.7-1
yaru-icon-theme 26.04.5.1ubuntu-1
yay 13.0.1-1
zoxide 0.10.0-1
zram-generator 1.2.1-1
```

Foreign (not in a configured pacman repository) — 16 packages:

```text
android-apktool-bin
elephant
elephant-bluetooth
elephant-calc
elephant-clipboard
elephant-desktopapplications
elephant-files
elephant-menus
elephant-providerlist
elephant-runner
elephant-symbols
elephant-todo
elephant-unicode
elephant-websearch
obsidian-cli-inspector
omarchy-walker
```

## Configuration footprint

218 allow-listed files were captured. Area names without an `etc/` prefix are `applied/`
subdirectories (user configuration); `etc/…` areas are system configuration. Sizes are
post-redaction file sizes.

| Area | Files | Bytes |
|---|---:|---:|
| etc/systemd | 29 | 22.1 KiB |
| omarchy | 20 | 21.7 KiB |
| devin | 18 | 26.3 KiB |
| nvim | 17 | 21.8 KiB |
| systemd | 17 | 5.6 KiB |
| omp | 14 | 19.7 KiB |
| hypr | 13 | 10.5 KiB |
| agents | 10 | 70.4 KiB |
| etc/ufw | 8 | 17.8 KiB |
| etc/sudoers.d | 6 | 539.0 B |
| fcitx5 | 4 | 314.0 B |
| home | 4 | 11.1 KiB |
| etc/bluetooth | 3 | 15.3 KiB |
| etc/cups | 3 | 35.4 KiB |
| etc/modprobe.d | 3 | 87.0 B |
| environment.d | 2 | 129.0 B |
| etc/default | 2 | 2.4 KiB |
| etc/sddm.conf.d | 2 | 181.0 B |
| etc/sysctl.d | 2 | 62.0 B |
| opencode | 2 | 258.0 B |
| swayosd | 2 | 459.0 B |
| waybar | 2 | 8.4 KiB |
| alacritty | 1 | 876.0 B |
| btop | 1 | 10.1 KiB |
| claude | 1 | 22.0 B |
| codex | 1 | 2.4 KiB |
| etc/X11 | 1 | 378.0 B |
| etc/crypttab | 1 | 692.0 B |
| etc/docker | 1 | 133.0 B |
| etc/environment | 1 | 97.0 B |
| etc/fstab | 1 | 856.0 B |
| etc/hostname | 1 | 9.0 B |
| etc/hosts | 1 | 117.0 B |
| etc/limine | 1 | 1.4 KiB |
| etc/limine-entry-tool | 1 | 8.5 KiB |
| etc/limine-entry-tool.d | 1 | 74.0 B |
| etc/locale | 1 | 17.0 B |
| etc/mkinitcpio | 1 | 3.3 KiB |
| etc/os-release | 1 | 382.0 B |
| etc/pacman | 1 | 750.0 B |
| etc/pacman.d | 1 | 58.0 B |
| etc/security | 1 | 2.4 KiB |
| etc/vconsole | 1 | 248.0 B |
| fastfetch | 1 | 4.0 KiB |
| fontconfig | 1 | 1.6 KiB |
| foot | 1 | 516.0 B |
| ghostty | 1 | 1.3 KiB |
| git | 1 | 1.5 KiB |
| grok | 1 | 934.0 B |
| gtk-3.0 | 1 | 142.0 B |
| kimi-code | 1 | 1.3 KiB |
| kitty | 1 | 954.0 B |
| mise | 1 | 169.0 B |
| starship.toml | 1 | 768.0 B |
| sudoers | 1 | 33.0 B |
| tmux | 1 | 3.2 KiB |
| walker | 1 | 1.3 KiB |

Notes on coverage:

- `home` is `applied/.bashrc`, `.bash_profile`, `.profile`, and `.tmux.conf`; `sudoers` is the
  user-owned `~/nvme1-scratch-sudoers` file; `systemd` is `applied/systemd/user` (14 service
  units and 3 timers), distinct from `etc/systemd`.
- `etc/systemd` carries 29 files because the capture keeps the stock unit-manager configuration
  it reads at boot: `system.conf`, `user.conf`, `networkd.conf`, `homed.conf`, `oomd.conf`,
  `pstore.conf`, `coredump.conf`, `journald/journal-remote/journal-upload`, and the three
  `/etc/systemd/network/*.network` files. `etc/ufw` (8 files) likewise includes the stock
  `before`/`before6`/`after`/`after6`/`user`/`user6` rule sets and `sysctl.conf`.
- The largest areas by size are `agents` (70.4 KiB, the two skills trees), `etc/cups` (35.4 KiB,
  mostly the stock `cups-browsed.conf`), `devin` (26.3 KiB), `etc/systemd` (22.1 KiB), `nvim`
  (21.8 KiB), and the Omarchy theme (21.7 KiB).
- `data/snapshot.json` (250,372 bytes, ~244.5 KiB) carries the same content plus the
  `config_index` (source label, path, size, post-redaction SHA-256, redaction count) and the
  `commands` record of every inventory command.
- `REPORT.md` (34,624 bytes) is the capture manifest and artifact index; its table excludes
  itself and `data/snapshot.json`, and `ARTIFACTS.sha256` (23,386 bytes) seals all 238 other
  files. `validate` checks the seal, the index, the config index, and the package counts.

## Reproduction notes

1. Install Arch Linux on UEFI hardware with a vfat ESP at `/boot`, LUKS2-encrypted Btrfs root,
   and the subvolume layout `@`, `@home`, `@log`, `@pkg`; mount `compress=zstd:3,ssd`.
2. Install the kernel/microcode/initramfs stack from the explicit list (`linux`, `linux-headers`,
   `amd-ucode`, `mkinitcpio`, `limine`, `limine-mkinitcpio-hook`, `limine-snapper-sync`,
   `plymouth`), then reproduce `mkinitcpio.conf`, `/etc/default/limine`,
   `/etc/limine-entry-tool.conf`, and the UKI naming (`omarchy`).
3. Reproduce the boot command line: LUKS via `cryptdevice=PARTUUID=…:root`, Btrfs
   `rootflags=subvol=@`, `zswap.enabled=0`, quiet/splash, and the hibernate
   `resume=/dev/mapper/root resume_offset=…` pair. Install Limine and register it in EFI.
4. Install Omarchy `3.8.3` (stable) and select the Matte Black theme with the
   JetBrainsMono Nerd Font; keep the Omarchy defaults, then overlay `~/.config/hypr/*`,
   `~/.config/waybar/*`, the theme directory, and the `~/.config/tmux` / `~/.tmux.conf` pair.
5. Restore only intentional user config from `applied/`: shell startup files, git/starship/mise,
   terminals, tmux, Neovim, Hyprland/Waybar/Walker/SwayOSD, Fcitx5, and the agent-client
   configs. Do not copy keyrings, browser state, caches, histories, or auth material — they are
   not in the snapshot anyway.
6. Reinstall npm globals from the list above (fnm is the Node manager; mise intentionally
   manages nothing). Cargo and pip user installs were empty, and Ruby had only default gems.
7. Recreate the service surface: enable the system units and timers listed above, the user
   shim/socket/timer units, and Docker socket activation; set UFW defaults and the LocalSend
   and Docker-DNS rules. Review the shim units before enabling them, since their endpoints and
   credentials are supplied outside the snapshot.
8. Re-authenticate external services interactively on the destination machine: `gh`, 1Password,
   browsers/web apps, and each agent provider. The snapshot records only that the integration
   exists, never the credential.
9. Re-capture with `./bin/xsnapshot collect --snapshot <date>`, run
   `./bin/xsnapshot validate` to confirm the new seal, artifact index, config index, and
   package counts, then diff the new tree against `snapshots/2026-10-19/` (`REPORT.md` plus
   `data/snapshot.json`) to see drift.

Because this document intentionally omits credentials, encrypted-volume keys, browser
sessions, and device identities, it can describe the machine but cannot restore it. Treat it as
an inventory and a diffing baseline, not a backup.

# Second opinion — memory, second NVMe, BIOS (2026-10-20)

> A first-principles review of [`PLAN.md`](PLAN.md), checked against
> [`snapshots/2026-10-19/`](../../snapshots/2026-10-19/) only. I had no access to the machine.
> Where the plan relies on something it saw live (journal OOM lines, `/dev/shm` contents, the
> pending-update list), I say so and give the command that settles it. Also asked for: BIOS tuning
> for maximum performance ([last section](#bios-for-maximum-performance)).

## Verdict

The diagnosis is right: this machine runs out of memory, not disk. Most of the mechanics are
sound too: PARTUUID-only random-key volumes, the key file in `/etc/cryptsetup-keys.d`, updating
before touching hardware, and Docker bind mounts guarded by `RequiresMountsFor`. I would change
five things:

1. **Cap demand, not only supply.** OMP allows `maxConcurrency: 100`. No swap layout survives that
   on 32 GB. A cgroup fence and a measured concurrency cap do (§1).
2. **Use one swap tier, not three.** zram, then `fast-swap`, then the swapfile adds up to about
   77 GiB of swap on a 30 GiB machine. That lengthens the thrash before an OOM, moves earlyoom's
   default trigger to about 70 GiB swapped, and pairs zram-only sysctls (`swappiness = 180`) with
   disk tiers. Use zswap in front of the existing swapfile and skip the swap partition (§2).
3. **Two runbook steps can misfire.** The very first `snapper` snapshot fails if `/swap` isn't its
   own subvolume (§3). The `/tmp` fstab line loses its boot ordering, and its 1777 mode isn't
   guaranteed (§4).
4. **The largest risk isn't on the list.** There is one disk and no backup, and the agents run in
   `yolo` mode with passwordless root. The second drive can hold a replica of `@home` (§5).
5. **Do the BIOS in two sessions, and test where Curve Optimizer actually fails.** Safe settings go
   in with the drive. PBO, Curve Optimizer and memory tuning go on a separate day, tested one core
   at a time, not only with `stress-ng --cpu 32`.

Ranked by size of effect: controlling memory demand matters far more than data safety measures,
which matter more than CPU tuning (single-digit %), which matters more than storage layout (about
0% speed; the layout's value is isolation).

## Axes

| Axis | What moves it | Size |
|---|---|---|
| Responsiveness under memory pressure | demand caps, swap policy, more RAM | a page faulted back from NVMe swap costs ~100 µs, from zram/zswap a few µs, from RAM ~0.1 µs |
| OOM / freeze risk | demand caps, early killer, more RAM | lost work vs none |
| Data safety | snapshots, a second copy | rare, but total |
| CPU throughput | PBO, Curve Optimizer, boost override, memory timings | ~5–10% all-core, ~3–5% single-core |
| Storage speed | — | ≈0: the SN8100 does over a million random IOPS and the OS disk is 27% full |
| Boot robustness | `nofail` done right, fallback kernel | — |

The rule used below: keep a move only if it improves one axis and costs none.

## Claim check

| The plan says | The snapshot shows | Verdict |
|---|---|---|
| `/tmp` is capped at 15 GB and 1,048,576 files | `findmnt`: `size=15860892k,nr_inodes=1048576` | ✔ |
| `/dev/shm` can grow to ~16 GB; ~3.7 GB is stale agent folders | mounted with no `size=` (kernel default: half of RAM); contents not captured | ✔ for the cap; the folders were seen live only |
| Swap is 8.7 GB deep | `free`: 9.1 GiB of swap used while 21 GiB is *available*; zram 3.3 of 4 GiB used | ✔. Swap that deep while RAM is free means it's mostly stale pages (runbook step 0) |
| OOM kills, one "triggered by Hyprland" | not captured | unverified. The `invoked oom-killer` line names whoever was allocating when the kernel gave up. The `Killed process` line names the victim, and the victim is what identifies the hog |
| zram is 4 GB, swappiness 60, no earlyoom or oomd | `zram-generator.conf` sets only `zstd`, so the size is the default `min(ram / 2, 4096)` MiB; no swap sysctls; stock `oomd.conf`; earlyoom not installed | ✔ |
| The OS disk is never trimmed | `cryptsetup status root` shows no `flags: discards`; no `fstrim.timer` | ✔. Once discards pass through, btrfs turns on `discard=async` by itself (kernel ≥ 6.2). `fstrim.timer` is then for the new XFS volumes |
| No snapper configs | `snapper list-configs` is empty, while `limine-snapper-sync` is enabled | ✔ |
| 96 GB of Docker, from one image | `wukakuki/unreal-engine:dev-slim-5.8.3` is 97.9 GB | ✔ |
| The iGPU is on and Hyprland doesn't depend on it | amdgpu device present; no `AQ_DRM_DEVICES` in any Hyprland config | ✔ |
| CPU tops out at the stock 5.756 GHz, so the old overclock isn't applied | `lscpu` max 5756 MHz | weak evidence. That number comes from the CPPC table that amd-pstate reads, not from a measured clock, and it says nothing about PBO limits or Curve Optimizer. Check in the BIOS |
| M2_2 shares lanes with USB4 | the ASM4242 USB4 router sits directly on a CPU root port (`00:02.2`) | consistent with that; confirm the option name in the manual |
| `~/nvme1-scratch-sudoers` grants passwordless sudo; rename it | the same line is already live in `/etc/sudoers.d/99-user-nopasswd` | the copy in `~` is moot. The live rule is the real decision, and `~/.agents/AGENTS.md` depends on it |

## What I'd change

### 1. Cap demand

`~/.omp/agent/config.yml` allows 100 concurrent subagents, with recursion depth 2. An agent that
drives Chromium (`agent-browser`, Playwright) or runs `node` costs hundreds of MB, and a 32-job
C++ or Rust build can want 1–4 GB per job. That doesn't fit in 32 GB, or in 96. Swap only decides
how long the desktop stalls before something dies.

- **Set `maxConcurrency` from a measurement.** Watch per-agent memory with `systemd-cgtop` or
  `ps -o rss`. The cap is your memory budget divided by that, for example 18 GiB ÷ ~0.75 GiB ≈ 24.
- **Run swarms and big builds inside a slice,** so the kernel throttles them and not Hyprland:

```ini
# ~/.config/systemd/user/agents.slice
[Unit]
Description=Agent swarms and heavy builds

[Slice]
MemoryHigh=18G
MemoryMax=22G
MemorySwapMax=8G
CPUWeight=50
```

```bash
systemctl --user daemon-reload
# a dedicated tmux server; every pane started in it inherits agents.slice
alias swarm='systemd-run --user --slice=agents.slice --scope --quiet -- tmux -L agents new -A -s swarm'
```

Above `MemoryHigh`, the kernel reclaims from that slice only and slows it down. At `MemoryMax`, the
OOM killer acts inside the slice only. `MemorySwapMax` stops the swarm from filling the swapfile,
and `CPUWeight=50` keeps the compositor ahead when CPUs are contended.

For containers, use `docker run -m 16g` (in compose, `deploy.resources.limits.memory`). During a
build, `systemd-cgls` shows which cgroup BuildKit's steps land in.

### 2. One swap tier

With the plan applied, swap runs zram (15 GiB), then `fast-swap` (32 GiB), then the swapfile
(30 GiB).

- **More swap doesn't prevent OOM.** It extends the thrash before one.
- **earlyoom fires late.** Its defaults act when available RAM is under 10% *and* free swap is
  under 10%. With 77 GiB of swap, that happens after about 70 GiB has been swapped. The plan's own
  "add `-s 50`" note is this conflict.
- **`swappiness = 180` is zram-only tuning.** With disk tiers behind zram, it sends anonymous memory
  to NVMe rather than dropping clean page cache, which costs nothing to drop.
- **zram in front of disk swap is LRU-inverted.** Whatever reached swap first (such as those stale
  `/dev/shm` files) holds compressed RAM indefinitely, and newer, warmer pages go to disk.

Instead, I'd put **zswap in front of the swapfile you already have: no zram and no swap
partition.** zswap compresses pages on their way to swap and, with the shrinker on, writes its
coldest entries through to disk. That's the zswap-plus-SSD design Meta runs fleet-wide and
published as TMO.

```ini
# /etc/tmpfiles.d/zswap.conf — runtime switch; supersedes zswap.enabled=0 on the Omarchy cmdline
w /sys/module/zswap/parameters/compressor       - - - - zstd
w /sys/module/zswap/parameters/max_pool_percent - - - - 25
w /sys/module/zswap/parameters/shrinker_enabled - - - - 1
w /sys/module/zswap/parameters/enabled          - - - - 1
```

```ini
# /etc/systemd/zram-generator.conf
# Intentionally no [zram0] section: zswap replaces zram. Never run both.
```

```ini
# /etc/sysctl.d/99-swap.conf
vm.swappiness = 100
vm.page-cluster = 0
vm.watermark_boost_factor = 0
vm.watermark_scale_factor = 125
```

With this, earlyoom's defaults (the plan's line, unchanged) mean under 10% of RAM available and
under 3 GiB of swap free. That's a true last resort behind the slice.

Hibernation keeps working: same swapfile, same `resume_offset`. zswap entries also hold swapfile
slots, so hibernate when swap use is low. When the UKI is next rebuilt, drop `zswap.enabled=0`
from `/etc/default/limine` so the cmdline and the runtime setting agree.

If you'd rather stay on Omarchy's zram: take the plan's `zram-size = ram / 2`, set swappiness to
about 100 because a disk tier sits behind it, and still skip `fast-swap`.

### 3. Snapshots: check first, then add `home`

Btrfs won't snapshot a subvolume that contains an active swapfile. If `/swap` is a plain directory
inside `@`, the plan's first command fails with "Text file busy", and so does every later root
snapshot.

```bash
sudo btrfs subvolume show /swap >/dev/null && echo "ok: /swap is its own subvolume"
```

If that errors, move the swapfile into its own subvolume first. This changes `resume_offset`:

```bash
sudo swapoff /swap/swapfile
sudo mv /swap /swap.old && sudo btrfs subvolume create /swap
sudo btrfs filesystem mkswapfile --size 31g /swap/swapfile
sudo swapon /swap/swapfile
sudo btrfs inspect-internal map-swapfile -r /swap/swapfile   # prints the new resume_offset
grep -rn resume_offset /etc/default/limine /etc/limine-entry-tool.d/   # replace it in each file
sudo limine-update                                                     # rebuild the UKI with the new cmdline
sudo rm -rf /swap.old
```

When creating the root config, turn its timeline off. Root wants pre- and post-update snapshots,
not hourly ones that pin package files and Docker data. Then add a `home` config: an hourly undo
for an agent's `rm -rf`.

```bash
sudo snapper -c root create-config /
sudo snapper -c root set-config TIMELINE_CREATE=no
sudo snapper -c home create-config /home
sudo snapper -c home set-config TIMELINE_CREATE=yes TIMELINE_LIMIT_HOURLY=24 TIMELINE_LIMIT_DAILY=7 \
  TIMELINE_LIMIT_WEEKLY=0 TIMELINE_LIMIT_MONTHLY=0 TIMELINE_LIMIT_YEARLY=0
sudo systemctl enable --now snapper-timeline.timer snapper-cleanup.timer
```

These snapshots live on the same disk, so they are not a backup (§5).

### 4. `/tmp`: keep the boot ordering, guarantee the mode

There are two problems with the plan's `/dev/mapper/fasttmp /tmp xfs …,nofail,…` line:

- **`nofail` drops the ordering.** It also removes the mount's ordering before `local-fs.target`
  (see systemd.mount(5)). Boot then continues while `/tmp` is still being created. Anything written
  to `/tmp` early, such as the socket directories tmpfiles makes, lands on the root filesystem and
  is hidden once the mount arrives.
- **The mode isn't guaranteed.** The filesystem is created fresh each boot with a 0755 root
  directory, and nothing guarantees 1777. The plan's `stat` check only catches it afterwards.

```
/dev/mapper/fasttmp  /tmp  xfs  noatime,nosuid,nodev,nofail,x-systemd.before=local-fs.target,x-systemd.device-timeout=10s,X-mount.mode=1777  0 0
```

`x-systemd.before=` restores the ordering while still letting the machine boot if the drive is
missing (at most a 10 s delay). `X-mount.mode=` needs util-linux 2.39 or later; you have 2.42.3.

When RAM is free, XFS-backed `/tmp` is slower than tmpfs for work that calls fsync a lot, such as
git. Here that's the right trade, but it's the reason if a job in `/tmp` feels slower.

### 5. Second drive: drop `fast-swap`, add a replica target

| # | Label | Size | Use | Encryption |
|---|---|---|---|---|
| 1 | `fast-tmp` | 128 GiB | `/tmp`, XFS, recreated every boot | new random key every boot (as in the plan) |
| 2 | `vault` | 256 GiB | btrfs target for `@home` replicas | LUKS2: key file plus backup passphrase |
| 3 | `fast-data` | the rest, ~547 GiB | `/fast`, XFS: Docker, scratch, build caches | LUKS2: key file plus backup passphrase (as in the plan) |

Snapper on `@home` gives instant undo, but it dies with the disk. A daily `btrfs send` of `@home`
to the second drive survives an OS-disk failure or a deleted `~/Projects`. Today `@home` is well
under 140 GiB (241 GiB used, 96 GiB of it Docker), so 256 GiB leaves room for history. The copy
won't survive theft, fire, or a root process that goes looking for it, so keep anything
irreplaceable pushed somewhere off the machine too. The commands are in runbook steps 5–6.

### 6. Smaller things

- **Check Docker's snapshotter before the rsync.** Run `docker info -f '{{.Driver}}'`. If it says
  `overlayfs`, copy as planned. If it says `btrfs`, don't copy: pull or rebuild onto `/fast`,
  because btrfs-snapshotter subvolumes don't survive a copy to XFS.
- **Format the new drive to 4 KiB sectors first.** If `nvme id-ns -H` lists a 4096-byte LBA
  format, switch to it before partitioning. It's free on an empty drive and matches the 4 KiB
  encryption sectors.
- **Give key files their own fast keyslot.** Add key files with
  `--key-slot 1 --pbkdf pbkdf2 --pbkdf-force-iterations 1000`, and put `key-slot=1` in their
  crypttab lines. A 512-bit random key gains nothing from argon2's deliberate slowness. Without
  `key-slot=`, each boot first spends the passphrase slot's ~2 s key derivation on the wrong slot.
  A manual `cryptsetup open` still accepts the passphrase.
- **Install `linux-lts` before the first reboot.** Do it right after `omarchy-update`, so the
  fallback kernel exists the first time a new kernel and NVIDIA pair might fail.
- **earlyoom's `--prefer node`** includes the Claude Code session you're typing in. That's fine,
  but expect it.
- **`allow-discards` leaks a little.** Someone holding the disk can see which blocks are free (not
  their contents). That's the standard trade, and fine here.
- **The collector won't capture the slice.** It doesn't read `~/.config/systemd/user/*.slice`. Add
  that glob to `collect_configs()` if you want `agents.slice` in the next snapshot.

## Revised runbook

The steps refer to the plan's numbered steps and to §1–§6 above.

### 0. Before anything (no reboot)

```bash
# tmpfs "Used" far above Shmem = tmpfs pages sitting in swap
df -h /tmp /dev/shm; grep -E '^(Shmem|SwapTotal|SwapFree):' /proc/meminfo
# who is in swap
for f in /proc/[0-9]*/status; do awk '/^Name:/{n=$2} /^VmSwap:/{print $2" kB", n}' "$f"; done 2>/dev/null | sort -n | tail
# stall time; "full avg10" above a few percent is real thrashing
cat /proc/pressure/memory
# past OOM victims, all boots (journalctl -k would limit this to the current boot)
journalctl _TRANSPORT=kernel -g 'Killed process' --no-pager | tail
# the two checks the later steps depend on
sudo btrfs subvolume show /swap >/dev/null && echo "/swap ok"   # §3
docker info -f '{{.Driver}}'                                    # §6
```

Delete the stale agent folders in `/dev/shm` now (check `lsof +D /dev/shm` first), not in step 7.
Swap use should drop right away.

### 1. Safety net

- Do the plan's LUKS header backup, to a USB stick.
- Run the §3 snapper commands, then the plan's `pre-nvme-baseline` snapshot.
- Push any uncommitted work you care about.

### 2. Update

Run `omarchy-update`. Then install `linux-lts linux-lts-headers`, the plan's tool list, and
`btrbk`. Only then reboot, and check `uname -r` and `nvidia-smi`.

### 3. OS disk and memory policy, one reboot

- **From the plan's step 3:** the TRIM and workqueue `refresh`, `fstrim.timer`, `noatime` and
  earlyoom.
- **From this review:** §2 instead of the plan's zram and sysctl blocks, plus the §1 slice and
  concurrency cap.
- **After the reboot, check:**
  - `lsblk -D` shows a non-zero DISC-MAX on `root`.
  - `swapon --show` lists only the swapfile.
  - `grep -r . /sys/module/zswap/parameters/` shows zswap enabled.
  - `systemctl is-active earlyoom` prints `active`.

### 4. BIOS session A

The safe settings, listed [below](#session-a-safe-do-it-with-the-drive-install).

### 5. Install, format, partition

Follow the plan's step 5, then:

```bash
sudo nvme id-ns -H "$NEW" | grep 'LBA Format'          # if one shows "Data Size: 4096 bytes":
sudo nvme format "$NEW" --lbaf=<its index>

sudo sfdisk --wipe always "$NEW" <<'EOF'
label: gpt
size=128GiB, type=linux, name=fast-tmp
size=256GiB, type=linux, name=vault
             type=linux, name=fast-data
EOF
lsblk -o NAME,SIZE,PARTLABEL,PARTUUID "$NEW"           # P1 fast-tmp, P2 vault, P3 fast-data

sudo install -d -m 0700 /etc/cryptsetup-keys.d
sudo dd if=/dev/urandom of=/etc/cryptsetup-keys.d/vault.key bs=64 count=1
sudo dd if=/dev/urandom of=/etc/cryptsetup-keys.d/fastdata.key bs=64 count=1
sudo chmod 0400 /etc/cryptsetup-keys.d/vault.key /etc/cryptsetup-keys.d/fastdata.key
P2=/dev/disk/by-partuuid/<P2>
P3=/dev/disk/by-partuuid/<P3>

sudo cryptsetup luksFormat --type luks2 --sector-size 4096 "$P2"   # backup passphrase → password manager
sudo cryptsetup luksAddKey --key-slot 1 --pbkdf pbkdf2 --pbkdf-force-iterations 1000 "$P2" /etc/cryptsetup-keys.d/vault.key
sudo cryptsetup open --key-file /etc/cryptsetup-keys.d/vault.key \
  --allow-discards --perf-no_read_workqueue --perf-no_write_workqueue --persistent "$P2" vault

sudo cryptsetup luksFormat --type luks2 --sector-size 4096 "$P3"   # backup passphrase → password manager
sudo cryptsetup luksAddKey --key-slot 1 --pbkdf pbkdf2 --pbkdf-force-iterations 1000 "$P3" /etc/cryptsetup-keys.d/fastdata.key
sudo cryptsetup open --key-file /etc/cryptsetup-keys.d/fastdata.key \
  --allow-discards --perf-no_read_workqueue --perf-no_write_workqueue --persistent "$P3" fastdata

sudo mkfs.btrfs -L vault /dev/mapper/vault
sudo mkfs.xfs -L fastdata /dev/mapper/fastdata
sudo mkdir /fast /vault /mnt/btr_pool
```

`/etc/crypttab`:

```
fasttmp   PARTUUID=<P1>  /dev/urandom  tmp=xfs,cipher=aes-xts-plain64,size=512,sector-size=4096,discard,no-read-workqueue,no-write-workqueue,nofail
vault     PARTUUID=<P2>  none          luks,discard,key-slot=1,nofail
fastdata  PARTUUID=<P3>  none          luks,discard,key-slot=1,nofail
```

Add to `/etc/fstab`. `<root-fs-uuid>` is the UUID on your existing `/` line.

```
/dev/mapper/fasttmp   /tmp           xfs    noatime,nosuid,nodev,nofail,x-systemd.before=local-fs.target,x-systemd.device-timeout=10s,X-mount.mode=1777  0 0
/dev/mapper/vault     /vault         btrfs  noatime,compress=zstd:3,nofail,x-systemd.device-timeout=10s  0 0
/dev/mapper/fastdata  /fast          xfs    noatime,nofail,x-systemd.device-timeout=10s  0 0
UUID=<root-fs-uuid>   /mnt/btr_pool  btrfs  noatime,subvolid=5  0 0
```

The plan's warning still applies: the `fasttmp` line erases its partition on every boot, so use a
PARTUUID there, never a `/dev/nvme…` path. Reboot, then run the plan's checks. Expect only the
swapfile in `swapon --show`.

### 6. Move workloads

Follow the plan's step 7 if the snapshotter check said `overlayfs`. Then set up the replica:

```
# /etc/btrbk/btrbk.conf
snapshot_preserve_min  latest
snapshot_preserve      no
target_preserve_min    no
target_preserve        14d 8w 6m

volume /mnt/btr_pool
  snapshot_dir btrbk_snapshots
  subvolume @home
    target /vault/home
```

```bash
sudo mkdir -p /mnt/btr_pool/btrbk_snapshots /vault/home
sudo btrbk -n run && sudo btrbk run      # dry run, then the first full send
sudo systemctl enable --now btrbk.timer  # daily and incremental from here on
```

Delete `pre-nvme-baseline` once everything is stable.

### 7. Live with it for a day, then do BIOS session B

## BIOS for maximum performance

### What limits a 9950X

- **All-core work** (builds, agent fan-out) is limited by power and temperature. The stock power
  limits (PPT, TDC, EDC) are hit before 95 °C in a 32-thread build. PBO raises them until the
  cooler is the limit. Curve Optimizer lowers the voltage each MHz needs, so the same watts buy more
  MHz.
- **Single-thread and lightly threaded work** (shell, linker, JS, editor) is limited by the boost
  ceiling (5.7 GHz) and the voltage/frequency curve. Boost Clock Override raises the ceiling, and
  Curve Optimizer makes it reachable. The CPU's reliability model (FIT) still caps voltage:
  override changes frequency, not the voltage limit. PBO Scalar is the knob that loosens FIT, which
  is why it's the one to skip.
- **Memory-latency-bound work** is limited by FCLK, the UCLK:MEMCLK ratio and DRAM timings. On
  DDR5, tREFI is the single largest timing.

### Session A (safe; do it with the drive install)

Nothing here changes the CPU's voltage/frequency curve.

1. **Firmware.** If there's anything newer than 2.AC3, read its notes (AGESA version, and skip
   betas). Flash it with M-Flash, then choose **Load Optimized Defaults**; the flash resets
   everything anyway.
2. **Memory.**
   - EXPO: Profile 1 (DDR5-6000 CL30).
   - UCLK DIV1 MODE: UCLK = MEMCLK.
   - FCLK: 2000 MHz. Auto may already pick 2000; setting it explicitly costs nothing.
   - Memory Context Restore: Enabled. It skips DDR5 retraining at every boot. If a boot ever
     hangs, it's the first thing to turn off.
3. **Integrated Graphics Controller: Disabled.** Hyprland doesn't reference the iGPU. If the NVIDIA
   module ever fails to load, the RTX's own firmware framebuffer still gives you a console, so the
   "no backup display" downside is smaller than it sounds.
4. **Leave on:** Re-Size BAR and Above 4G Decoding; Global C-State Control, CPPC and CPPC Preferred
   Cores; SMT. Leave CSM off.
5. **M2_2 lane mode: leave the default (x2, USB4 on).** Lane width only changes sequential
   bandwidth. Latency and random IOPS, which is what `/tmp`, Docker and scratch use, are set by
   the NAND and controller, and dm-crypt sits in the path as well. x2 also runs the drive cooler
   under the GPU.
6. **Boot order:** Limine first.
7. **Save.** Press F10, then save an OC profile to USB. F12 saves a screenshot of the current page
   to the same stick.
8. **Back in Linux, check:**
   - `nvidia-smi -q | grep -A3 -i bar1` shows a total of about 16 GiB, meaning Resizable BAR is
     active.
   - `efibootmgr` shows Limine first.

`systemctl reboot --firmware-setup` goes straight into the BIOS; the snapshot shows
"Boot into FW: supported".

### Session B (performance; separate days, one change per boot)

Test after every step, using the protocol below.

| Step | Setting | Then |
|---|---|---|
| 1 | Precision Boost Overdrive: Advanced. PBO Limits: Motherboard. PBO Scalar: Auto. Platform Thermal Throttle Limit: Auto (95 °C), or 90 °C if you want it quieter for ~1–2% | all-core test |
| 2 | Curve Optimizer: All Cores, Negative 15 | full protocol. On a pass, try 20, then 25. On the first failure, go back 5, or switch to Per Core and back off only the failing cores |
| 3 | CPU Boost Clock Override: Enabled, Positive +100, then +200 | per-core test. If +200 fails where +100 passed, keep +100 or give those cores less Curve Optimizer |
| 4 | MSI's memory presets: High-Efficiency Mode, Latency Killer (names vary by BIOS release) | memory tests |
| 5 | FCLK: 2100 | memory tests, plus a day of use. An unstable fabric shows up as MCEs, USB dropouts or resets |
| 6 | Optional: tREFI 65535, and tRFC for your DRAM die | only if `sensors` shows the DIMMs (`spd5118`) staying under ~50 °C under load; memory tests |

**Leave alone:**

- **PBO Scalar.** It raises the voltage the reliability model allows, for almost no gain.
- **Manual all-core ratios.** They turn off single-core boost.
- **VSOC above about 1.25 V.** AMD's ceiling is 1.30 V, and EXPO already sets about 1.20 V: the
  iGPU's `vddnb` sensor reads 1.20 V in the snapshot. Note that reading before you disable the iGPU.
- **Disabling C-states or CPPC.**
- **`mitigations=off`.** This machine runs untrusted agent code.

**Costs to know:**

- **Power and heat.** PBO adds about 40–60 W at the CPU, and the chip will sit at 95 °C under
  all-core load. That's by design, not damage, so the cooler decides the gain.
- **PSU.** With the 250 W RTX 5070, you want a PSU of 750 W or more.
- **Warranty.** AMD counts PBO as overclocking for warranty purposes.

**Linux side:** `powerprofilesctl set performance`. Omarchy runs power-profiles-daemon, and this
profile sets the amd-pstate EPP to performance: faster ramps to full boost, for a few watts more
at idle. It's the cheapest latency gain on this page.

### Test protocol (Linux only)

Curve Optimizer fails where the voltage margin is thinnest: one core boosting alone at light load.
It rarely fails under a 32-thread load, where clocks are lower. That's why the plan's
`stress-ng --cpu 32 --timeout 15m` tests the wrong regime.

1. **Per core, one at a time** (a poor man's CoreCycler). One pass is 16 × 5 minutes, about 80
   minutes. Do two or three passes before you settle on a value.

   ```bash
   #!/usr/bin/env bash
   # Run one thread on one physical core at a time: that core boosts to its maximum at its
   # thinnest voltage margin, which is where a negative Curve Optimizer value fails first.
   secs=${1:-300}
   for cpu in $(cut -d, -f1 /sys/devices/system/cpu/cpu[0-9]*/topology/thread_siblings_list | cut -d- -f1 | sort -un); do
     printf 'cpu %2d: ' "$cpu"
     taskset -c "$cpu" stress-ng --cpu 1 --cpu-method all --verify --timeout "${secs}s" --quiet && echo ok || echo FAIL
   done
   ```

2. **All-core.** Run `stress-ng --cpu 32 --cpu-method all --verify -t 30m`, then a real build
   (a large `cargo build --release`, or a kernel) in a loop.
3. **Memory.** After any memory change, boot memtest86+ from USB for two passes. In Linux, run
   `stress-ng --vm 8 --vm-bytes 2500m --vm-method all --verify -t 30m`.
4. **Daily use.** Run a normal day on the settings. A random reboot counts as a failure.
5. **After each stage, check:**

   ```bash
   journalctl -k -b -g 'mce|hardware error|machine check' --no-pager   # an MCE from a crash shows up early in the next boot's log
   journalctl --list-boots | tail -5                                    # a boot you didn't start = a crash or reset
   sudo btrfs scrub start -Bd /                                         # after memory tuning: checksum errors mean corruption
   ```

Memory errors matter more than usual here. RAM without ECC under btrfs can corrupt data before
it's checksummed. That's why every memory step ends with a scrub.

### What it adds up to

| Change | All-core | Single-core | Cost |
|---|---|---|---|
| PBO Limits: Motherboard | +3–6% | ~0 | +40–60 W; 95 °C under all-core load |
| Curve Optimizer −15 to −25 | +2–5% | +0–2% | testing time; intermittent crashes if pushed too far |
| Boost override +200 MHz (with Curve Optimizer) | ~0 | up to +3.5% | needs Curve Optimizer headroom; more testing |
| FCLK 2000 → 2100 | 0–1% | 0–1% | fabric errors if unstable |
| tREFI and MSI memory presets | +1–3% | +1–3% | memory errors corrupt data (no ECC, plus btrfs) |
| PBO Scalar 10X | ~0 | ~0 | higher voltage, faster wear: skip |

These figures are typical and vary by chip. Realistically, all of it adds up to about 5–10%
all-core and 3–5% single-core. For scale, a page faulted back from disk swap costs about 1000
times a RAM access, so the memory-pressure work above is worth more than everything in this
section.

## RAM

I agree with the plan: more RAM is the fix that dominates everything else here.

- **The sweet spot** is 2×48 GB DDR5-6000 CL30 (96 GB) on two sticks.
- **If the budget allows,** 2×64 GB. It may need help to run at 6000, with 5600 as the fallback.
- **If the budget is the limit,** add a second 2×16 GB of the same kit for 4×16 GB = 64 GB at about
  5600. That's still a large win: for this workload, capacity is worth far more than the 2–3% that
  dropping from 6000 to 5600 costs. Four sticks are where AM5 gets finicky, so prove them with
  memtest86+ before trusting them.

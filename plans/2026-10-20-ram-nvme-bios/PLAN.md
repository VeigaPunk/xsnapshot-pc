# Plan as received — memory, second NVMe, BIOS (2026-10-20)

> Stored as received from an earlier agent session on 2026-10-20. It is unedited except for one
> identity scrub that [`docs/PRIVACY.md`](../../docs/PRIVACY.md) requires: the local account name in
> the `/fast/scratch` command is written as `"$USER"`. The second opinion on this plan is
> [`REVIEW.md`](REVIEW.md).

---

I haven't changed anything on the machine. Everything below is a plan for tomorrow, based on your `xsnapshot-pc` snapshot from 2026-10-19. I also checked the live machine (read-only) and it matches.

**Short version:** your real bottleneck is RAM, not disk speed. You have 32 GB of RAM, and both `/tmp` and `/dev/shm` are RAM-backed and can each grow to about 16 GB. Swap is already 8.7 GB deep, and the system log shows out-of-memory kills, including system-wide ones (one triggered by Hyprland). The second SN8100 helps most as a place to move things out of RAM and off the OS disk:

- an encrypted swap partition,
- a disk-backed `/tmp` that's wiped every boot,
- a `/fast` volume for Docker and agent scratch.

Separately, the OS disk has problems you can fix without the new drive: it has never been trimmed, there's no snapshot to roll back to, and 415 updates are pending. I left out local-model setup, as you asked.

## What I found

- **The second NVMe isn't installed.** Only one NVMe controller is present. The 2026-08-23 `deathstart` setup (`/scratch` and its boot service) was lost in the reinstall. Don't re-run those scripts: they create an unencrypted disk and set a global `TMPDIR`.
- **`/tmp` limits:** it has a 15 GB size cap and a 1,048,576-file cap. The file cap means something like an `npm install` in `/tmp` can fail with "no space left" while gigabytes are free.
- **`/dev/shm`:** it has its own 16 GB cap, and about 3.7 GB of it is old agent folders (`v3-r38`, `rv1`, `cn1`…). Together the two caps add up to more than your RAM.
- **Why tmpfs hurts when RAM is tight:** its files first get compressed into zram, then pushed to the swapfile on the OS disk. Your "RAM disk" turns into a slow disk.
- **Swap tuning was lost in the reinstall:**
  - zram (compressed swap in RAM) is only 4 GB; it was half your RAM before.
  - `swappiness` is back to 60, and `page-cluster` to 3.
  - Nothing kills runaway processes early: `earlyoom` isn't installed and `systemd-oomd` is off.
- **The OS disk is never trimmed** (trim tells the SSD which blocks are free, which keeps writes fast). The encryption layer blocks trim requests, and `fstrim.timer` is off.
- **No snapper configs**, so there's no rollback point before updates and the Limine boot menu has no snapshots.
- **Docker:** 96 GB in `/var/lib/containerd`, almost all from one image, `wukakuki/unreal-engine:dev-slim-5.8.3`.
- **Pending updates:**
  - kernel 7.2.3 → 7.2.11
  - `nvidia-open-dkms` 610 → 615
  - systemd 262, mkinitcpio 42, limine 12.9.3
  - firmware and AMD microcode 20260916
  - cryptsetup 2.8.8, docker 29.9.1
- **BIOS state:**
  - Memory profile (EXPO 6000) and Resizable BAR are on.
  - The integrated GPU is on and reserves 512 MiB of RAM, even though your monitor is on the RTX.
  - The CPU boosts to the stock 5.756 GHz, so the overclock settings in `deathstart` are not applied.
- **Nothing is plugged into the USB4 ports.** This matters for the slot-speed choice below.

## How to use the second NVMe

M2_2 is a Gen5 slot wired to the CPU, but it shares lanes with the rear USB4 ports:

- **Default x2:** about 7.9 GB/s, roughly a Gen4 drive. The USB4 ports keep working.
- **x4 (set in BIOS):** full Gen5 speed, but the rear 40 Gbps USB-C ports turn off.

Since nothing uses USB4, I'd pick x4. Honestly, for `/tmp`, swap and Docker you won't feel the difference.

| Partition | Size | Use | Encryption |
|---|---|---|---|
| `fast-swap` | 32 GiB | swap, used after zram and before the root swapfile | new random key every boot |
| `fast-tmp` | 128 GiB | `/tmp` (XFS), recreated every boot | new random key every boot |
| `fast-data` | ~770 GiB | `/fast` (XFS): Docker, `/fast/scratch` | LUKS2, unlocked by a key file stored on the encrypted root |

Why this layout:

- **`/tmp` behaves like now** (empty after each reboot, unreadable afterwards because the key is thrown away), but uses no RAM and has no size or file-count caps.
- **Swap and Docker stop competing with the OS disk.**
- **XFS instead of btrfs:** scratch space doesn't need snapshots, and XFS copes better with lots of small files written by many threads (node_modules, cargo builds, agent swarms).
- **Missing-drive safety:** if the drive is missing, the machine still boots. Every new mount is `nofail`, and no environment variable points into `/fast` (that's what broke `CARGO_HOME` in `deathstart`).

What I wouldn't do:

- **RAID0 across both disks:** two chances to lose everything, for no real desktop gain.
- **Moving `/home`:** the OS disk still has 684 GB free.
- **Moving small caches like `~/.npm`:** both drives are the same model, so there's no speed gain.

## Tomorrow, in order

### 1. Safety net

```bash
sudo snapper -c root create-config /
sudo snapper -c root create -d "pre-nvme-baseline"
sudo cryptsetup luksHeaderBackup /dev/nvme0n1p2 --header-backup-file ~/luks-root-header.img
# copy the .img to a USB stick, then delete it from ~
```

Back up the encryption header before installing the new drive, while `nvme0n1` can only mean the OS disk. Make sure you know your disk passphrase. The disk isn't unlocked through the TPM, so flashing the BIOS won't lock you out.

### 2. Update and install packages, then reboot

```bash
omarchy-update
# reboot; check: uname -r → 7.2.11+, nvidia-smi → 615.x
sudo pacman -S --needed nvme-cli smartmontools fio xfsprogs pacman-contrib earlyoom iotop-c sysstat stress-ng
sudo pacman -S --needed linux-lts linux-lts-headers   # backup boot entry if an NVIDIA update breaks the main kernel
sudo systemctl enable --now paccache.timer            # package cache is 7 GB
pacman -Qdtq   # orphans: electron39, mbedtls, webp-pixbuf-loader → sudo pacman -Rns $(pacman -Qdtq) if unused
```

Optional, for faster Rust builds: `mold` and `sccache`.

### 3. OS disk and memory fixes, then reboot

```bash
sudo cryptsetup --allow-discards --perf-no_read_workqueue --perf-no_write_workqueue --persistent refresh root
sudo systemctl enable fstrim.timer
sudoedit /etc/fstab   # change relatime → noatime on the 4 btrfs lines
```

`/etc/systemd/zram-generator.conf`:

```ini
[zram0]
zram-size = ram / 2
compression-algorithm = zstd
swap-priority = 100
```

`/etc/sysctl.d/99-swap.conf`:

```ini
vm.swappiness = 180
vm.page-cluster = 0
vm.watermark_boost_factor = 0
vm.watermark_scale_factor = 125
```

Put this in `/etc/default/earlyoom`, then run `sudo systemctl enable earlyoom`:

```bash
EARLYOOM_ARGS="-r 3600 --avoid '(^|/)(Hyprland|Xwayland|sddm|systemd|pipewire|wireplumber|waybar)$' --prefer '(^|/)(java|node|chromium|python3?)$'"
```

After the reboot:

- `lsblk -D` should show a non-zero DISC-MAX on `root`, which means trim now works.
- `swapon --show` should list about 15 GB of zram.

earlyoom only steps in when free memory and free swap are both under 10%. If you get long freezes before it acts, add `-s 50`.

### 4. BIOS (press DEL at boot, then F7)

1. **Firmware:** check MSI's site for anything newer than 2.AC3 (June 2026). If there is a newer version, flash it first with M-Flash, because flashing resets all the settings below.
2. **M2_2 / USB4 lane sharing** (under PCIe settings; the exact name varies): x4. Leave it at x2 if you'll use the rear 40 Gbps USB-C ports.
3. **Integrated Graphics: Disabled.** This gives back 512 MiB of RAM, and nothing in your Hyprland config depends on it. The downside is no backup display output if the RTX dies.
4. **Memory:**
   - Keep EXPO 1 with UCLK = MEMCLK.
   - Set FCLK to 2000 (try 2100 only if you'll stress-test it).
   - Turn on Memory Context Restore, which skips memory training on every boot. Turn it back off if you ever get a boot hang.
5. **CPU:** keep SMT, Global C-States, CPPC and CPPC Preferred Cores on; Linux's CPU frequency driver uses them.
   - For more speed: PBO Advanced with Curve Optimizer at All Cores, Negative 10. Test it, then try Negative 15.
   - I'd skip the +200 MHz boost and the 10X scalar from the old notes: more heat and voltage for a gain under 10%.
   - Use PBO Limits = Motherboard only if you have a 280 or 360 mm AIO cooler.
6. **Leave as is:** Resizable BAR and Above 4G on, CSM off, NVMe RAID off, Secure Boot off, PCIe speeds on Auto.
7. **Boot order:** OS disk / Limine first.
8. **Save:** press F10, then save the settings as an OC Profile to USB.

To test CPU stability from Linux, run `stress-ng --cpu 32 --timeout 15m` and a big compile. Afterwards, `journalctl -k | grep -iE 'mce|hardware error'` should print nothing.

### 5. Install the drive

- **Shut down completely.** Don't hibernate across a hardware change.
- **Install it in M2_2** under the board's M.2 heatsink, and **peel the plastic film off the thermal pad**.
- **Boot the normal entry.**

The drive names `nvme0` and `nvme1` may swap. Your current config uses fixed IDs, so that's harmless, but never use `/dev/nvmeX` names in new config.

```bash
cat /sys/class/nvme/nvme*/device/current_link_{speed,width}   # expect 32.0 GT/s and 4 (or 2)
ls -l /dev/disk/by-id/ | grep -i sn8100 | grep -v part        # the new drive is the one with no partitions
NEW=/dev/disk/by-id/nvme-WD_BLACK_SN8100_1000GB_<new-serial>
```

### 6. Partition, encrypt, mount

```bash
sudo sfdisk --wipe always "$NEW" <<'EOF'
label: gpt
size=32GiB,  type=swap,  name=fast-swap
size=128GiB, type=linux, name=fast-tmp
             type=linux, name=fast-data
EOF
lsblk -o NAME,SIZE,PARTLABEL,PARTUUID "$NEW"   # write down the three PARTUUIDs

sudo install -d -m 0700 /etc/cryptsetup-keys.d
sudo dd if=/dev/urandom of=/etc/cryptsetup-keys.d/fastdata.key bs=64 count=1
sudo chmod 0400 /etc/cryptsetup-keys.d/fastdata.key
P3=/dev/disk/by-partuuid/<P3>
sudo cryptsetup luksFormat --type luks2 --sector-size 4096 "$P3"   # set a backup passphrase
sudo cryptsetup luksAddKey "$P3" /etc/cryptsetup-keys.d/fastdata.key
sudo cryptsetup open --key-file /etc/cryptsetup-keys.d/fastdata.key \
  --allow-discards --perf-no_read_workqueue --perf-no_write_workqueue --persistent "$P3" fastdata
sudo mkfs.xfs -L fastdata /dev/mapper/fastdata
sudo mkdir /fast
```

`/etc/crypttab`:

```
fastswap  PARTUUID=<P1>  /dev/urandom  swap,cipher=aes-xts-plain64,size=512,sector-size=4096,discard,no-read-workqueue,no-write-workqueue,nofail
fasttmp   PARTUUID=<P2>  /dev/urandom  tmp=xfs,cipher=aes-xts-plain64,size=512,sector-size=4096,discard,no-read-workqueue,no-write-workqueue,nofail
fastdata  PARTUUID=<P3>  none          luks,discard,nofail
```

**The swap and tmp lines erase their partition on every boot.** Always use PARTUUIDs there. If the drive names swap, a `/dev/nvme…` path could end up pointing at your OS disk.

Add to `/etc/fstab`:

```
/dev/mapper/fastswap  none   swap  defaults,pri=10,discard,nofail                                    0 0
/dev/mapper/fasttmp   /tmp   xfs   defaults,noatime,nosuid,nodev,nofail,x-systemd.device-timeout=10s  0 0
/dev/mapper/fastdata  /fast  xfs   defaults,noatime,nofail,x-systemd.device-timeout=10s              0 0
```

Don't run `systemctl mask tmp.mount` (the old `deathstart` script did). The fstab line already replaces the RAM-backed `/tmp`, and masking would block the new one too.

After rebooting, check:

- `swapon --show` lists zram first, then `fastswap`, then the root swapfile.
- `findmnt /tmp /fast` shows both mounted.
- `stat -c %a /tmp` prints `1777`.

If you use hibernate, test it once.

### 7. Move workloads onto it

**Docker:** a plain copy is safe with your Docker storage setup. If you don't need the Unreal image, remove it first (`docker image rm wukakuki/unreal-engine:dev-slim-5.8.3`); the move drops from about 100 GB to about 6 GB.

```bash
sudo systemctl stop docker.socket docker.service containerd.service
sudo rsync -aHAX --numeric-ids --info=progress2 /var/lib/containerd/ /fast/containerd/
sudo rsync -aHAX --numeric-ids --info=progress2 /var/lib/docker/ /fast/docker/
sudo mv /var/lib/containerd /var/lib/containerd.old && sudo mkdir /var/lib/containerd
sudo mv /var/lib/docker /var/lib/docker.old && sudo mkdir /var/lib/docker
```

Add to fstab:

```
/fast/containerd  /var/lib/containerd  none  bind,nofail,x-systemd.requires-mounts-for=/fast  0 0
/fast/docker      /var/lib/docker      none  bind,nofail,x-systemd.requires-mounts-for=/fast  0 0
```

Create `/etc/systemd/system/containerd.service.d/fast.conf` and the same file under `docker.service.d/`. Your existing `no-block-boot.conf` lets Docker start before disks are mounted, and this stops it:

```ini
[Unit]
RequiresMountsFor=/var/lib/containerd /var/lib/docker
```

Then run `sudo systemctl daemon-reload && sudo mount -a && sudo systemctl start docker`. Check that `docker images` lists everything, then delete the `.old` folders.

**Agent scratch:**

- Run `sudo install -d -o "$USER" -g "$USER" /fast/scratch`.
- Move `~/tmp`, `~/scratch-r104`, `~/r9d04-scratch` and `~/x02-scratch` into it.
- Delete the old `/dev/shm` folders.
- Add a rule to `~/.agents/AGENTS.md`: throwaway files go in `/tmp`, multi-day work goes in `/fast/scratch/<task>`, and never `/dev/shm` or `$HOME`.
- Optional: cap shared memory at 8 GB with `tmpfs /dev/shm tmpfs defaults,nosuid,nodev,size=8G 0 0` in fstab.

**Last step:** once everything is stable, delete the `pre-nvme-baseline` snapshot. It keeps the old 96 GB of Docker data on the OS disk.

## Bigger fix, if you're open to buying hardware

Replacing the 2×16 GB RAM with a 2×32 GB (or 2×48 GB) DDR5-6000 CL30 kit would fix the out-of-memory problem more than anything above. Use two sticks, not four: four sticks on AM5 usually force lower memory speeds.

One small cleanup: `~/nvme1-scratch-sudoers` looks like a limited sudo rule, but it actually grants passwordless sudo for everything. Rename or delete it so it doesn't get installed by mistake.

I can save this as a checklist file (for example in `xsnapshot-pc`) if you want it handy tomorrow.

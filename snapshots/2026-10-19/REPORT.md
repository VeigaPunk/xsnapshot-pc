# Snapshot report: 2026-10-19

> Captured **2026-10-19T21:13:22-03:00** on `plazir27`.
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
| Hostname | `plazir27` |
| Chassis | desktop |
| Board | MAG X870E TOMAHAWK WIFI (MS-7E59) (2.0) |
| Firmware | 2.AC3 dated 06/25/2026 |
| OS | Arch Linux |
| Kernel | `7.2.3-arch1-3` |
| Architecture | x86_64 |
| CPU | AMD Ryzen 9 9950X 16-Core Processor (32 threads) |
| Memory | 30.3 GiB |
| GPU | NVIDIA GeForce RTX 5070 (12227 MiB, driver 610.57.04) |
| Omarchy | 3.8.3 (master/stable) |
| Desktop | Hyprland 0.56.2 |
| Theme | Matte Black |
| Pacman packages | 1348 total / 270 explicit / 16 foreign |
| Config files captured | 218 |
| Redactions applied | 170 |

## Configuration footprint

| Area                    | Files | Bytes    |
|-------------------------|-------|----------|
| etc/systemd             | 29    | 22.1 KiB |
| omarchy                 | 20    | 21.7 KiB |
| devin                   | 18    | 26.3 KiB |
| nvim                    | 17    | 21.8 KiB |
| systemd                 | 17    | 5.6 KiB  |
| omp                     | 14    | 19.7 KiB |
| hypr                    | 13    | 10.5 KiB |
| agents                  | 10    | 70.4 KiB |
| etc/ufw                 | 8     | 17.8 KiB |
| etc/sudoers.d           | 6     | 539.0 B  |
| fcitx5                  | 4     | 314.0 B  |
| home                    | 4     | 11.1 KiB |
| etc/bluetooth           | 3     | 15.3 KiB |
| etc/cups                | 3     | 35.4 KiB |
| etc/modprobe.d          | 3     | 87.0 B   |
| environment.d           | 2     | 129.0 B  |
| etc/default             | 2     | 2.4 KiB  |
| etc/sddm.conf.d         | 2     | 181.0 B  |
| etc/sysctl.d            | 2     | 62.0 B   |
| opencode                | 2     | 258.0 B  |
| swayosd                 | 2     | 459.0 B  |
| waybar                  | 2     | 8.4 KiB  |
| alacritty               | 1     | 876.0 B  |
| btop                    | 1     | 10.1 KiB |
| claude                  | 1     | 22.0 B   |
| codex                   | 1     | 2.4 KiB  |
| etc/X11                 | 1     | 378.0 B  |
| etc/crypttab            | 1     | 692.0 B  |
| etc/docker              | 1     | 133.0 B  |
| etc/environment         | 1     | 97.0 B   |
| etc/fstab               | 1     | 856.0 B  |
| etc/hostname            | 1     | 9.0 B    |
| etc/hosts               | 1     | 117.0 B  |
| etc/limine              | 1     | 1.4 KiB  |
| etc/limine-entry-tool   | 1     | 8.5 KiB  |
| etc/limine-entry-tool.d | 1     | 74.0 B   |
| etc/locale              | 1     | 17.0 B   |
| etc/mkinitcpio          | 1     | 3.3 KiB  |
| etc/os-release          | 1     | 382.0 B  |
| etc/pacman              | 1     | 750.0 B  |
| etc/pacman.d            | 1     | 58.0 B   |
| etc/security            | 1     | 2.4 KiB  |
| etc/vconsole            | 1     | 248.0 B  |
| fastfetch               | 1     | 4.0 KiB  |
| fontconfig              | 1     | 1.6 KiB  |
| foot                    | 1     | 516.0 B  |
| ghostty                 | 1     | 1.3 KiB  |
| git                     | 1     | 1.5 KiB  |
| grok                    | 1     | 934.0 B  |
| gtk-3.0                 | 1     | 142.0 B  |
| kimi-code               | 1     | 1.3 KiB  |
| kitty                   | 1     | 954.0 B  |
| mise                    | 1     | 169.0 B  |
| starship.toml           | 1     | 768.0 B  |
| sudoers                 | 1     | 33.0 B   |
| tmux                    | 1     | 3.2 KiB  |
| walker                  | 1     | 1.3 KiB  |

## Package inventory

- Full explicit package set: `packages/pacman-explicit.txt`
- Full installed package set: `packages/pacman-all.txt`
- Foreign/AUR package set: `packages/pacman-foreign.txt`
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
- **Not a backup:** this is a descriptive inventory. It cannot restore
  credentials, encrypted volumes, browser sessions, or application state.
- **Privilege:** root-owned files are read through `sudo -n` when available.
  If passwordless sudo is unavailable, those files are reported as missing in
  the notes instead of being approximated.

## Artifact index

The table below lists every captured artifact except this report and
`data/snapshot.json`; both are covered by `ARTIFACTS.sha256`, which seals every
file in the snapshot except itself.

| Path                                                                                  | Size     | SHA-256       |
|---------------------------------------------------------------------------------------|----------|---------------|
| applied/.bash_profile                                                                 | 174.0 B  | a21bfd7d2c89… |
| applied/.bashrc                                                                       | 3.9 KiB  | 2d66f2b1db7e… |
| applied/.profile                                                                      | 736.0 B  | 6c6be761d3b1… |
| applied/.tmux.conf                                                                    | 6.4 KiB  | b0643df5eb5d… |
| applied/agents/AGENTS.md                                                              | 667.0 B  | 5ded7f1f7622… |
| applied/agents/skills/godspeed/SKILL.md                                               | 869.0 B  | 1d6167238784… |
| applied/agents/skills/godspeed/directive.md                                           | 429.0 B  | db88963cbdf5… |
| applied/agents/skills/reverse-engineer-anything/SKILL.md                              | 22.0 KiB | c86398238b2a… |
| applied/agents/skills/reverse-engineer-anything/references/android-applications.md    | 1.9 KiB  | 412d9cb462d8… |
| applied/agents/skills/reverse-engineer-anything/references/connection-and-recovery.md | 8.6 KiB  | a33760c84ae1… |
| applied/agents/skills/reverse-engineer-anything/references/evidence-workflows.md      | 4.3 KiB  | 2bdee98a843d… |
| applied/agents/skills/reverse-engineer-anything/references/javascript-applications.md | 9.7 KiB  | b3e5e999833b… |
| applied/agents/skills/reverse-engineer-anything/references/native-and-artifacts.md    | 17.3 KiB | 1d2ac5f64feb… |
| applied/agents/skills/reverse-engineer-anything/references/runtime-observation.md     | 4.7 KiB  | fea85e2005a8… |
| applied/alacritty/alacritty.toml                                                      | 876.0 B  | 695301c86577… |
| applied/btop/btop.conf                                                                | 10.1 KiB | 4e17dd28c439… |
| applied/claude/settings.json                                                          | 22.0 B   | 27dafb2742d0… |
| applied/codex/config.toml                                                             | 2.4 KiB  | 3abd707e1b2d… |
| applied/devin/AGENTS.md                                                               | 667.0 B  | 5ded7f1f7622… |
| applied/devin/agents/kaidoku-shokunin.md                                              | 1019.0 B | 56b49237d2c4… |
| applied/devin/agents/ufo-critic-ds.md                                                 | 1.2 KiB  | 6032f3ce42ac… |
| applied/devin/agents/ufo-critic-glm.md                                                | 1.2 KiB  | 9785d67c5a3d… |
| applied/devin/agents/ufo-distiller-ds.md                                              | 1.4 KiB  | 63f55531b945… |
| applied/devin/agents/ufo-executor-ds.md                                               | 2.5 KiB  | fd1c7b78d7e0… |
| applied/devin/agents/ufo-executor-glm.md                                              | 2.5 KiB  | 07f3ebf18f21… |
| applied/devin/agents/ufo-executor-swe.md                                              | 2.5 KiB  | e84f8ed3133c… |
| applied/devin/agents/ufo-reviewer-ds.md                                               | 1.9 KiB  | 4ac8f6aafe4b… |
| applied/devin/agents/ufo-reviewer-glm.md                                              | 1.9 KiB  | 361e14e37c30… |
| applied/devin/agents/ufo-scout-ds.md                                                  | 1.4 KiB  | 658ec6984122… |
| applied/devin/agents/ufo-scribe-ds.md                                                 | 1.2 KiB  | 715c5ea36467… |
| applied/devin/agents/ufo-scribe-glm.md                                                | 1.2 KiB  | da1571a73467… |
| applied/devin/agents/ufo-sentinel-swe.md                                              | 1.4 KiB  | 17161eac0c08… |
| applied/devin/agents/ufo-simplifier-ds.md                                             | 1.6 KiB  | bfd1d9583843… |
| applied/devin/agents/ufo-simplifier-glm.md                                            | 1.6 KiB  | 0929648cbecc… |
| applied/devin/config.json                                                             | 525.0 B  | 28c080f8d55f… |
| applied/devin/mcp_config.json                                                         | 404.0 B  | 0f1d64895a81… |
| applied/environment.d/fcitx.conf                                                      | 79.0 B   | 8b077b6ea259… |
| applied/environment.d/ssh-agent.conf                                                  | 50.0 B   | d621f4cfa11d… |
| applied/fastfetch/config.jsonc                                                        | 4.0 KiB  | c909b43ba000… |
| applied/fcitx5/conf/clipboard.conf                                                    | 29.0 B   | 2d53b40811ee… |
| applied/fcitx5/conf/notifications.conf                                                | 46.0 B   | e4075dbcb45b… |
| applied/fcitx5/conf/xcb.conf                                                          | 43.0 B   | f5cf059182c4… |
| applied/fcitx5/profile                                                                | 196.0 B  | 6e966046df5b… |
| applied/fontconfig/fonts.conf                                                         | 1.6 KiB  | 6dec98b53938… |
| applied/foot/foot.ini                                                                 | 516.0 B  | 3e88354476f2… |
| applied/ghostty/config                                                                | 1.3 KiB  | cb828c044b07… |
| applied/git/config                                                                    | 1.5 KiB  | c1ee282e9121… |
| applied/grok/config.toml                                                              | 934.0 B  | 923dfb937400… |
| applied/gtk-3.0/bookmarks                                                             | 142.0 B  | e2f1aabde359… |
| applied/hypr/ai-usage.conf                                                            | 319.0 B  | 21e76af98ce7… |
| applied/hypr/autostart.conf                                                           | 209.0 B  | cbe0548c2dad… |
| applied/hypr/bindings.conf                                                            | 2.8 KiB  | e574a1ed0853… |
| applied/hypr/envs.conf                                                                | 133.0 B  | 04af5cdf028b… |
| applied/hypr/gkeep.conf                                                               | 263.0 B  | d318f899fc87… |
| applied/hypr/hypridle.conf                                                            | 765.0 B  | e7d3b8dd9835… |
| applied/hypr/hyprland.conf                                                            | 1.3 KiB  | ce7483f35ab5… |
| applied/hypr/hyprlock.conf                                                            | 742.0 B  | b8d173dcff55… |
| applied/hypr/hyprsunset.conf                                                          | 363.0 B  | 3042e4a92303… |
| applied/hypr/input.conf                                                               | 1.5 KiB  | 3769c92ab766… |
| applied/hypr/looknfeel.conf                                                           | 1000.0 B | 777a4fdc8b61… |
| applied/hypr/monitors.conf                                                            | 1012.0 B | 69c9d8996dfd… |
| applied/hypr/xdph.conf                                                                | 106.0 B  | 2fded88a27b8… |
| applied/kimi-code/tui.toml                                                            | 1.3 KiB  | 02cc238f3f54… |
| applied/kitty/kitty.conf                                                              | 954.0 B  | f875291ecfe6… |
| applied/mise/config.toml                                                              | 169.0 B  | 65bce5c3b5a3… |
| applied/nvim/.neoconf.json                                                            | 183.0 B  | 1819a5b64b71… |
| applied/nvim/init.lua                                                                 | 72.0 B   | 3b2d6e9976a5… |
| applied/nvim/lazy-lock.json                                                           | 4.7 KiB  | 1a4bb48e02a0… |
| applied/nvim/lazyvim.json                                                             | 147.0 B  | 27b7649110de… |
| applied/nvim/lua/config/autocmds.lua                                                  | 424.0 B  | ccb2b3a99fe0… |
| applied/nvim/lua/config/keymaps.lua                                                   | 209.0 B  | 660a7d9a603a… |
| applied/nvim/lua/config/lazy.lua                                                      | 1.8 KiB  | 14653a615b10… |
| applied/nvim/lua/config/options.lua                                                   | 311.0 B  | d38b75ce4a15… |
| applied/nvim/lua/config/remote_clipboard.lua                                          | 2.5 KiB  | bac8268c3dde… |
| applied/nvim/lua/plugins/all-themes.lua                                               | 1.5 KiB  | 4ad5aeb20615… |
| applied/nvim/lua/plugins/disable-news-alert.lua                                       | 100.0 B  | 5e27ebfe7735… |
| applied/nvim/lua/plugins/example.lua                                                  | 5.2 KiB  | 63cab8b37a31… |
| applied/nvim/lua/plugins/omarchy-theme-hotreload.lua                                  | 3.2 KiB  | d4f74ba06eec… |
| applied/nvim/lua/plugins/snacks-animated-scrolling-off.lua                            | 117.0 B  | e3dc59bf119a… |
| applied/nvim/lua/plugins/theme.lua                                                    | 151.0 B  | 40734698e8a6… |
| applied/nvim/plugin/after/transparency.lua                                            | 1.1 KiB  | 6e31b917f13e… |
| applied/nvim/stylua.toml                                                              | 59.0 B   | b45819d91dbd… |
| applied/omarchy/branding/about.txt                                                    | 2.7 KiB  | 5fe8adced2fe… |
| applied/omarchy/branding/screensaver.txt                                              | 1.5 KiB  | f98c966b1670… |
| applied/omarchy/theme.name                                                            | 12.0 B   | 48749715228b… |
| applied/omarchy/theme/alacritty.toml                                                  | 772.0 B  | 8c3d1457c09d… |
| applied/omarchy/theme/colors.toml                                                     | 461.0 B  | dbdd13a629aa… |
| applied/omarchy/theme/foot.ini                                                        | 378.0 B  | d9c2e20e079a… |
| applied/omarchy/theme/ghostty.conf                                                    | 454.0 B  | 418636f99922… |
| applied/omarchy/theme/gum.env.conf                                                    | 5.3 KiB  | 618f801c6435… |
| applied/omarchy/theme/helix.toml                                                      | 4.5 KiB  | c7f85d447f48… |
| applied/omarchy/theme/hyprland-preview-share-picker.css                               | 1.8 KiB  | 24474e34a4ed… |
| applied/omarchy/theme/hyprland.conf                                                   | 143.0 B  | 79126bec8c28… |
| applied/omarchy/theme/hyprlock.conf                                                   | 176.0 B  | 3ef010e72b5f… |
| applied/omarchy/theme/kitty.conf                                                      | 444.0 B  | e8795b49ff5b… |
| applied/omarchy/theme/mako.ini                                                        | 119.0 B  | 95bf0c86c955… |
| applied/omarchy/theme/neovim.lua                                                      | 151.0 B  | 40734698e8a6… |
| applied/omarchy/theme/obsidian.css                                                    | 2.5 KiB  | d195eeaf760f… |
| applied/omarchy/theme/swayosd.css                                                     | 166.0 B  | f88118e98b44… |
| applied/omarchy/theme/vscode.json                                                     | 65.0 B   | 18171ea89a57… |
| applied/omarchy/theme/walker.css                                                      | 191.0 B  | f44cb4506349… |
| applied/omarchy/theme/waybar.css                                                      | 68.0 B   | a1807a176659… |
| applied/omp/agents/connector.md                                                       | 948.0 B  | 7dfbc4cfc0d8… |
| applied/omp/agents/critic.md                                                          | 826.0 B  | f64c5324f865… |
| applied/omp/agents/distiller.md                                                       | 957.0 B  | f9b98dd3c9d1… |
| applied/omp/agents/executor.md                                                        | 2.0 KiB  | 25e33184063a… |
| applied/omp/agents/labrat.md                                                          | 751.0 B  | a0f5e9dcec76… |
| applied/omp/agents/mutation-tester.md                                                 | 936.0 B  | 90b968c59b2e… |
| applied/omp/agents/planner.md                                                         | 1.4 KiB  | 08795872e08c… |
| applied/omp/agents/revenger.md                                                        | 1.0 KiB  | 4a08e745218b… |
| applied/omp/agents/reviewer.md                                                        | 1.5 KiB  | 8ed0911126aa… |
| applied/omp/agents/scout.md                                                           | 1021.0 B | 70795d6a21de… |
| applied/omp/agents/scribe.md                                                          | 826.0 B  | 886a80c15415… |
| applied/omp/agents/sentinel.md                                                        | 1.0 KiB  | 4d3b30ed5abe… |
| applied/omp/agents/simplifier.md                                                      | 1.2 KiB  | d774cd3c6f75… |
| applied/omp/config.yml                                                                | 5.5 KiB  | deb4caa273c5… |
| applied/opencode/cli.json                                                             | 163.0 B  | 4199dd4a6a35… |
| applied/opencode/opencode.json                                                        | 95.0 B   | fb067af03925… |
| applied/starship.toml                                                                 | 768.0 B  | b17c9b5f096f… |
| applied/sudoers/nvme1-scratch-sudoers                                                 | 33.0 B   | 94675a0ec851… |
| applied/swayosd/config.toml                                                           | 87.0 B   | a8a09212a32f… |
| applied/swayosd/style.css                                                             | 372.0 B  | 6e3ba08fd929… |
| applied/systemd/user/ai-usage.service                                                 | 257.0 B  | f09c68e5928c… |
| applied/systemd/user/ai-usage.timer                                                   | 202.0 B  | 62a77a83a304… |
| applied/systemd/user/antigravity-shim.service                                         | 630.0 B  | 6e19c21dff04… |
| applied/systemd/user/claude-shim.service                                              | 305.0 B  | dd31dc79299c… |
| applied/systemd/user/codex-shim.service                                               | 575.0 B  | cbd128ff0cb8… |
| applied/systemd/user/cursor-shim-healthcheck.service                                  | 166.0 B  | f08f79bb7d56… |
| applied/systemd/user/cursor-shim-healthcheck.timer                                    | 152.0 B  | faa6ce957135… |
| applied/systemd/user/cursor-shim.service                                              | 471.0 B  | 279803ad1cc0… |
| applied/systemd/user/devin-shim.service                                               | 285.0 B  | 04d080d790b2… |
| applied/systemd/user/ds-flash-shim.service                                            | 542.0 B  | eeeb2cb4fdd1… |
| applied/systemd/user/elephant.service                                                 | 166.0 B  | d495f1cc9dc7… |
| applied/systemd/user/glm-flash-shim.service                                           | 527.0 B  | 2661c89a4abf… |
| applied/systemd/user/omarchy-battery-monitor.service                                  | 209.0 B  | 74bbe7637c74… |
| applied/systemd/user/omarchy-battery-monitor.timer                                    | 188.0 B  | ce3d2e2af9b5… |
| applied/systemd/user/omarchy-recover-internal-monitor.service                         | 363.0 B  | b9b92cedc44c… |
| applied/systemd/user/swayosd-server.service                                           | 227.0 B  | 9886887fc96c… |
| applied/systemd/user/xai-shim.service                                                 | 440.0 B  | cc3c06c3afb2… |
| applied/tmux/tmux.conf                                                                | 3.2 KiB  | b673c18bf891… |
| applied/walker/config.toml                                                            | 1.3 KiB  | fecf71fa4253… |
| applied/waybar/config.jsonc                                                           | 6.2 KiB  | a408a33df48a… |
| applied/waybar/style.css                                                              | 2.2 KiB  | 8f335ca01da5… |
| etc/X11/xorg.conf.d/00-keyboard.conf                                                  | 378.0 B  | 42578d594670… |
| etc/bluetooth/input.conf                                                              | 1.0 KiB  | d85aa14cab44… |
| etc/bluetooth/main.conf                                                               | 14.2 KiB | b4d2d6a88d84… |
| etc/bluetooth/network.conf                                                            | 120.0 B  | 266ef88b3b6e… |
| etc/crypttab                                                                          | 692.0 B  | a8a631f75ac0… |
| etc/cups/cups-browsed.conf                                                            | 28.8 KiB | fccad4c9ced7… |
| etc/cups/cupsd.conf                                                                   | 6.6 KiB  | 3f64d45a0434… |
| etc/cups/printers.conf                                                                | 1.0 B    | 01ba4719c80b… |
| etc/default/limine                                                                    | 593.0 B  | 9fd127cde679… |
| etc/default/ufw                                                                       | 1.9 KiB  | 07db07bb07e5… |
| etc/docker/daemon.json                                                                | 133.0 B  | dd0d5f3a647c… |
| etc/environment                                                                       | 97.0 B   | 7097db24de0d… |
| etc/fstab                                                                             | 856.0 B  | 7cd8af3b1082… |
| etc/hostname                                                                          | 9.0 B    | 694cd433b421… |
| etc/hosts                                                                             | 117.0 B  | 74179b40600e… |
| etc/limine-entry-tool.conf                                                            | 8.5 KiB  | 5cb2e8c2a112… |
| etc/limine-entry-tool.d/resume.conf                                                   | 74.0 B   | eb69ca1cae7d… |
| etc/limine.conf                                                                       | 1.4 KiB  | cee84c5792d1… |
| etc/locale.conf                                                                       | 17.0 B   | 033252d5100c… |
| etc/locale.gen.active                                                                 | 18.0 B   | 7f3a0f6684ad… |
| etc/mkinitcpio.conf                                                                   | 3.3 KiB  | 08eb95ba2946… |
| etc/modprobe.d/disable-usb-autosuspend.conf                                           | 31.0 B   | 52c54cf62584… |
| etc/modprobe.d/hid_apple.conf                                                         | 27.0 B   | 963f859855c5… |
| etc/modprobe.d/nvidia.conf                                                            | 29.0 B   | c5e6709bc89f… |
| etc/os-release                                                                        | 382.0 B  | 71ff7a6e248d… |
| etc/pacman.conf                                                                       | 750.0 B  | 47c7aa33c5fd… |
| etc/pacman.d/mirrorlist                                                               | 58.0 B   | 6c4a944bed4b… |
| etc/sddm.conf.d/10-wayland.conf                                                       | 118.0 B  | 7e4984b912c2… |
| etc/sddm.conf.d/autologin.conf                                                        | 63.0 B   | 3727396ea221… |
| etc/security/limits.conf                                                              | 2.4 KiB  | 3219740266b4… |
| etc/sudoers.d/00_user                                                                 | 19.0 B   | 4af95b235f0a… |
| etc/sudoers.d/50-asdcontrol                                                           | 353.0 B  | 70d6838f91cf… |
| etc/sudoers.d/99-omarchy-installer-reboot                                             | 41.0 B   | a6664a134257… |
| etc/sudoers.d/99-user-nopasswd                                                        | 33.0 B   | 94675a0ec851… |
| etc/sudoers.d/omarchy-tzupdate                                                        | 68.0 B   | 880287229002… |
| etc/sudoers.d/passwd-tries                                                            | 25.0 B   | fb2225f7f666… |
| etc/sysctl.d/90-omarchy-file-watchers.conf                                            | 35.0 B   | e70681a232f1… |
| etc/sysctl.d/99-sysctl.conf                                                           | 27.0 B   | 47893370cdaf… |
| etc/systemd/coredump.conf                                                             | 1.0 KiB  | 5312d42f451c… |
| etc/systemd/coredump.conf.d/limit.conf                                                | 111.0 B  | 80b5c1ac84a9… |
| etc/systemd/homed.conf                                                                | 890.0 B  | 4ec3ffcb5776… |
| etc/systemd/journal-remote.conf                                                       | 1.1 KiB  | 2c08c407f38b… |
| etc/systemd/journal-upload.conf                                                       | 1.1 KiB  | 740dd524fc64… |
| etc/systemd/journald.conf                                                             | 1.4 KiB  | 995877ef4f57… |
| etc/systemd/journald.conf.d/size.conf                                                 | 46.0 B   | fc53f1e609f9… |
| etc/systemd/logind.conf                                                               | 1.8 KiB  | 8f6188df9249… |
| etc/systemd/network/20-ethernet.network                                               | 799.0 B  | 957057614c90… |
| etc/systemd/network/20-wlan.network                                                   | 569.0 B  | 64ae878092a5… |
| etc/systemd/network/20-wwan.network                                                   | 552.0 B  | 99a55148b4c6… |
| etc/systemd/networkd.conf                                                             | 1.4 KiB  | e1811ee807a3… |
| etc/systemd/oomd.conf                                                                 | 928.0 B  | c4aafc5d0125… |
| etc/systemd/pstore.conf                                                               | 879.0 B  | a7ed0c51fc52… |
| etc/systemd/resolved.conf                                                             | 2.0 KiB  | 58b1d4e1b581… |
| etc/systemd/resolved.conf.d/10-disable-multicast.conf                                 | 26.0 B   | 9e1d19e154bb… |
| etc/systemd/resolved.conf.d/20-docker-dns.conf                                        | 36.0 B   | d644e10c851c… |
| etc/systemd/sleep.conf                                                                | 1.1 KiB  | bc861767b30e… |
| etc/systemd/system.conf                                                               | 2.6 KiB  | b18682e8b608… |
| etc/systemd/system.conf.d/10-faster-shutdown.conf                                     | 35.0 B   | dbd88d8f4f55… |
| etc/systemd/system.conf.d/99-omarchy-nofile.conf                                      | 42.0 B   | 8818b84990ce… |
| etc/systemd/system/docker.service.d/no-block-boot.conf                                | 30.0 B   | 4b7c99e5e5d5… |
| etc/systemd/system/limine-snapper-watcher.service                                     | 857.0 B  | f6482bed9e73… |
| etc/systemd/system/plocate-updatedb.service.d/ac-only.conf                            | 29.0 B   | 15a1b7ccb585… |
| etc/systemd/system/user@.service.d/faster-shutdown.conf                               | 28.0 B   | 1dd0343bcd5a… |
| etc/systemd/timesyncd.conf                                                            | 1.0 KiB  | 7ef75a269fc8… |
| etc/systemd/user.conf                                                                 | 2.0 KiB  | bc49fb1e16bd… |
| etc/systemd/user.conf.d/99-omarchy-nofile.conf                                        | 42.0 B   | 8818b84990ce… |
| etc/systemd/zram-generator.conf                                                       | 37.0 B   | da096917b851… |
| etc/ufw/after.rules                                                                   | 1.8 KiB  | 102d8740442c… |
| etc/ufw/after6.rules                                                                  | 1.5 KiB  | 6acc00909910… |
| etc/ufw/before.rules                                                                  | 2.5 KiB  | 91bcfbeaeb78… |
| etc/ufw/before6.rules                                                                 | 6.5 KiB  | 341ef50f269f… |
| etc/ufw/sysctl.conf                                                                   | 1.9 KiB  | b80b0ab606a2… |
| etc/ufw/ufw.conf                                                                      | 313.0 B  | 254cb3ad232c… |
| etc/ufw/user.rules                                                                    | 1.7 KiB  | 0bf8eb165a05… |
| etc/ufw/user6.rules                                                                   | 1.5 KiB  | 2c706c585145… |
| etc/vconsole.conf                                                                     | 248.0 B  | 1b3030d5e6d1… |
| packages/cargo-installed.txt                                                          | 7.0 B    | 5dfecbf35de3… |
| packages/gem-local.txt                                                                | 1.3 KiB  | 1c1e5a2ceb76… |
| packages/largest-installed.txt                                                        | 1.5 KiB  | b5edc56890a0… |
| packages/npm-global.txt                                                               | 299.0 B  | d6197789550b… |
| packages/pacman-all.txt                                                               | 28.3 KiB | c8f02e21e4c8… |
| packages/pacman-explicit.txt                                                          | 6.7 KiB  | 68774f46da21… |
| packages/pacman-foreign.txt                                                           | 283.0 B  | 21443a6919a4… |
| packages/pip-user.txt                                                                 | 7.0 B    | 5dfecbf35de3… |
| system/agents.txt                                                                     | 1.4 KiB  | 08d18bd04cf6… |
| system/boot.txt                                                                       | 3.6 KiB  | 0308273e6aea… |
| system/desktop.txt                                                                    | 40.0 KiB | 1303e1785652… |
| system/dev.txt                                                                        | 5.0 KiB  | 2c4ca26a2d7b… |
| system/docker.txt                                                                     | 662.0 B  | 86d099c8240c… |
| system/hardware.txt                                                                   | 25.0 KiB | f4c697265ef3… |
| system/network.txt                                                                    | 5.0 KiB  | 08eaf61dbed2… |
| system/services.txt                                                                   | 9.0 KiB  | 2439d9cfe0fe… |
| system/storage.txt                                                                    | 5.6 KiB  | f30615c8a9df… |

## Notes

- none

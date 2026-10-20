# ~/.local/bin must precede /usr/bin so user-local tool builds (fd, gh, jj,
# jq, rg, bat, delta) shadow older system packages.
export PATH="$HOME/.local/bin:$PATH"

# Collapse duplicate PATH entries (nested shells re-prepend the same dirs).
# First occurrence wins, so command lookup order is unchanged.
__path_dedupe() { PATH="$(printf '%s' "$PATH" | awk -v RS=: -v ORS=: '!seen[$0]++' | sed 's/:$//')"; export PATH; }

# opencode v2 (standalone installer) must shadow the v1 npx wrapper in
# ~/.local/bin for every shell, including non-interactive `bash -lc`.
export PATH="$HOME/.opencode/bin:$PATH"

# fnm (user-local) must take precedence over mise's node on PATH.
# Placed above the interactive guard on purpose: non-interactive `bash -lc`
# shells (how agent tooling invokes commands) must also resolve node -> fnm 24.
export PATH="$HOME/.local/share/fnm:$PATH"
if command -v fnm >/dev/null 2>&1; then
  eval "$(fnm env --use-on-cd --shell bash)"
  # Drop fnm's `alias cd=__fnmcd`: interactive shells never use it (see the zoxide
  # note below) and agent harnesses that snapshot aliases without functions end up
  # with a `cd` that fails silently and runs the rest of a command in the wrong
  # directory. The on-cd hook stays available through chpwd_functions.
  unalias cd 2>/dev/null || true
fi

# REA (Ghidra analysis engine). Above the interactive guard so agent shells
# (`bash -lc`, MCP launchers) see it too.
export GHIDRA_INSTALL_DIR="$HOME/.local/opt/ghidra_12.1.4_PUBLIC"
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk

__path_dedupe

# If not running interactively, don't do anything (leave this at the top of this file)
[[ $- != *i* ]] && return

# All the default Omarchy aliases and functions
# (don't mess with these directly, just overwrite them here!)
source ~/.local/share/omarchy/default/bash/rc

# The omarchy rc above runs `mise activate bash`, which prepends mise's node
# ahead of fnm. Re-assert fnm's paths so Node 24 from fnm stays first.
export PATH="${FNM_MULTISHELL_PATH:-$HOME/.local/share/fnm}/bin:$HOME/.local/share/fnm:$PATH"

# fnm's `--use-on-cd` installs its hook as `alias cd=__fnmcd`, but omarchy's
# zoxide init defines `cd` as a *readonly* function, so that alias can never win.
# zoxide's `__zsh_like_cd` runs the `chpwd_functions` hooks after every cd, which
# is the supported extension point — register fnm's on-cd check there instead.
if declare -F __zsh_like_cd >/dev/null 2>&1 && declare -F __fnm_use_if_file_found >/dev/null 2>&1; then
  chpwd_functions+=(__fnm_use_if_file_found)
fi

# Add your own exports, aliases, and functions here.
#
# Make an alias for invoking commands you use constantly
# alias p='python'

# kimi-code
export PATH="/home/user/.kimi-code/bin:$PATH"

__path_dedupe

# REA provider wiring (shokunin training, installed 2026-10-13)
export REA_PWNTOOLS_PYTHON="$HOME/.local/share/kaidoku-pwnenv/bin/python"
export REA_BINWALK_COMMAND=/usr/bin/binwalk
export REA_UNBLOB_COMMAND="$HOME/.local/bin/unblob"
export REA_APKTOOL_COMMAND=/usr/bin/apktool
export REA_ADB_PATH=/usr/bin/adb
export REA_WAKARU_COMMAND="$(find "$(npm root -g)/wakaru/node_modules/@wakaru/cli-linux-x64" -maxdepth 1 -name wakaru -type f 2>/dev/null | head -n1)"
export REA_JADX_MCP_JAR="$HOME/.local/opt/jadx-headless-mcp/jadx-headless-mcp-0.7.1-all.jar"
alias oci="obsidian-cli-inspector"

# OpenAI Codex OAuth token for kimi-code's openai-codex provider
# (extracted from codex CLI's auth store; auto-refreshes when near expiry)
export OPENAI_CODEX_TOKEN="$(~/.local/bin/openai-codex-token 2>/dev/null)"

# xAI (Grok) OAuth token for kimi-code's xai-oauth provider
# (sourced from the hermes xai-oauth pool; auto-refreshes when near expiry)
export XAI_OAUTH_TOKEN="$(~/.local/bin/xai-oauth-token 2>/dev/null)"


# >>> grok installer >>>
export PATH="$HOME/.grok/bin:$PATH"
[[ -r "$HOME/.grok/completions/bash/grok.bash" ]] && source "$HOME/.grok/completions/bash/grok.bash"
# <<< grok installer <<<

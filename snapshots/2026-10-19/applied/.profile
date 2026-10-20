# ~/.profile — POSIX login environment for non-bash login shells.
# Bash login shells read ~/.bash_profile (which sources ~/.bashrc) instead.
export GHIDRA_INSTALL_DIR="$HOME/.local/opt/ghidra_12.1.4_PUBLIC"
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk

# REA provider wiring
export REA_PWNTOOLS_PYTHON="$HOME/.local/share/kaidoku-pwnenv/bin/python"
export REA_BINWALK_COMMAND=/usr/bin/binwalk
export REA_UNBLOB_COMMAND="$HOME/.local/bin/unblob"
export REA_APKTOOL_COMMAND=/usr/bin/apktool
export REA_ADB_PATH=/usr/bin/adb
export REA_JADX_MCP_JAR="$HOME/.local/opt/jadx-headless-mcp/jadx-headless-mcp-0.7.1-all.jar"

# Hermes Agent command
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) export PATH="$HOME/.local/bin:$PATH" ;; esac

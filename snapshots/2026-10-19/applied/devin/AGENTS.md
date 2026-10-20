# Operator tooling directive — 2026-10-19

Every agent, including delegated subagents, is authorized to install or update any tool that helps its task or is a strict upgrade, using all available privileges without asking again.

Before installing, read `/home/user/.omp/agent/RULES.md` for the official-source/channel policy, host update-safety gate, and installation-record requirement. Passwordless sudo is available on this host; do not change sudoers or bypass package-manager safety checks.

When delegating, include this authorization and require the child to read that policy. Do not assume a child inherits the parent's conversation or global instructions.

# Private snapshot repositories

`bin/xsnapshot-repo` optionally turns a person's state folder, containing `snapshots/`, into
one local git commit per complete capture. With one update command it can push that history to
the private destination that person controls. This is separate from requiring the owner to host
updates or visit the website. The collector itself still performs no upload, never imports this
module, and never uses its remote. No telemetry is sent, and this tool never contacts
xsnapshot.app.

The tool is designed for an owner-controlled private GitHub repository. A deliberately local,
Enterprise, or other non-GitHub destination is accepted only with an explicit
`update --assume-private` assertion on its exact effective push URL. Never use that flag to
bypass a known-public answer.

## What is uploaded

Every committed snapshot includes `REPORT.md`, `data/snapshot.json`, `ARTIFACTS.sha256`, the
package inventories, system records, and **all redacted `applied/` and `etc/` configuration
copies**. The entire validated snapshot folders are committed, not merely the summary JSON.
A tool-created root `README.md` and a small versioned `.xsnapshot-repo.json` marker are also committed. Other existing state-folder files, including a pre-existing README, remain untracked and are listed. The marker is staged in the earliest snapshot commit and is never force-pushed or history-rewritten; snapshot identity is carried by that history.

For a normal GitHub destination, GitHub stores everything on its services; the owner and people
they invite read it. It is not end-to-end encryption controlled by that person, unlimited
retention, or a backup of the disks. For an explicitly assumed non-GitHub destination, that
operator or host receives the content on the same review terms.

## Review before sharing

Read every `REPORT.md` and the retained `applied/` and `etc/` bodies before the first push.
The allow-list is the primary protection; redaction is best-effort, not a guarantee that all
secrets, identifiers, or personal details were removed. Collector `validate` proves artifact
membership and integrity, not privacy or provenance. Follow the full review gate in
[`PRIVACY.md`](PRIVACY.md).

## Fixed commands

```text
bin/xsnapshot-repo [--root STATE] init   [--name NAME] [--remote URL] [--no-remote] [--yes]
bin/xsnapshot-repo [--root STATE] update [--no-capture] [--no-push] [--no-sudo] [--assume-private]
bin/xsnapshot-repo [--root STATE] status
```

`STATE` contains `snapshots/`, and should be outside the collector checkout. Without `--root`,
only an existing `./xsnapshot-data` is used; there is no fallback to the collector checkout.
Missing state and unsafe places are refused. Exit code `0` is success, `2` an expected refusal,
and `1` an unexpected failure. Refusals contain the next action.

### `init`

`init` creates a repository on `main`, or idempotently initializes one already managed by this
tool; it can safely adopt an empty repository without unrelated history. It refuses a state
folder that is a symlink, is inside another worktree, has unrelated history, is a bare repo, or
has symlinked `.git/config`, `.git/info`, `.git/hooks`, `.git/objects`, or `.git/refs`.

Only complete captures passing the collector's own validator are committed, ordered by their
recorded capture time (oldest first). The format is `snapshot <id> (<host>)`; its author date is
the captured time. Valid snapshots always win over incomplete ones, which are reported and
skipped rather than blocking them. A linked snapshot directory is reported and skipped without
reading its target or validating it. Capture replacements, history deletion, rewriting, force
push, `git add -A`, and broad file selection are never used.

A root README is generated with this install's actual launcher and concrete state path. An
existing README is never overwritten or silently added. A later human edit to a generated
README is also preserved rather than regenerated.

Remote handling:

- If `gh` is installed and authenticated, the default shows the owner/repository name, private
  visibility, file count and bytes, and the inclusion of the complete folders and redacted config.
  Only `y` accepts the prompt. `--yes` skips the question; it is not a privacy override. Creation
  uses `gh repo create <name> --private`, then the actual destination is checked before push and
  again afterward. A public answer stops loudly before any upload.
- `--remote URL` attaches an already-created repository. If its privacy is unknown, the local
  commits are preserved with a refusal and a runnable next command. `init` deliberately has no
  `--assume-private`; use `update --assume-private` only after already verifying ownership and
  privacy for a remote whose privacy cannot be established. No history is lost by that refusal.
- `--no-remote`, absent `gh`, or a signed-out CLI leaves a successful local repository. Its
  instructions contain runnable paths, not the bare word `xsnapshot-repo` or unresolved `STATE`.

The default name is `xsnapshot-<host>` from the newest validated capture, reduced to supported
GitHub name characters.

### `update`

`update` uses the collector for today's snapshot if it does not exist. `--no-capture` skips
collection. `--no-sudo` omits root-only reads, and those gaps stay explicitly reported.
Only new valid snapshots are committed. A no-update run says so before checking whether the
existing local history needs pushing.

The default push is a plain fast-forward-only operation to the single URL that actually passed
the privacy and identity checks. `--no-push`, or no configured remote, says that the commits
remain local. No force flag is present. If a push fails because history differs, reconcile it
locally and deliberately; never let this command force it.

### `status`

`status` reports repository presence, remote (sensitive fields suppressed), measurable privacy,
committed and pending snapshots, and local commits not yet pushed. It can inspect a remote but
never initiates a push. An absent repository is not a failure and does not create `.git`.

## Destination identity and privacy

Every push starts with `git remote get-url --push --all origin`, so the bytes checked are the
**actual effective push destination after Git's `pushurl` and `pushInsteadOf` resolution**.
There must be exactly one effective destination and a canonical URL spelling. Pushes use that
same exact URL argument, not the symbolic `origin`, so it cannot silently redirect elsewhere.
A working remote URL with no query or fragment can use HTTPS `https://github.com/OWNER/REPO.git`,
`git@github.com:OWNER/REPO.git`, or `ssh://git@github.com/OWNER/REPO.git`.

When configured and authenticated, `gh` queries the exact owner/name. Its answer must include a
boolean `isPrivate` and matching `nameWithOwner`. Otherwise, a GitHub HTTPS remote receives an
unauthenticated `github.com` probe that can only detect public repositories. This failure,
`404`, or unreachable service is never taken as private. Unknown visibility requires
`--assume-private`; a public answer cannot be overridden. Explicit ports, trailing slashes,
extra path segments, duplicate `.git.git`, query, fragment, and other noncanonical spellings do
not establish canonical GitHub repository identity. `gh` metadata is not fetched indirectly
through a different destination.

A non-GitHub or local bare test push **must** carry `--assume-private`, even with the local
`--no-push` false case removed. The flag asserts the exact effective destination is private and
under the operator's control; it does not prove visibility or vouch for other recipients.
Status still reports unknown when the flag alone supplied the assertion.

URLs must not embed credentials. Password/token userinfo, queries and fragments are refused
before `gh`, HTTPS, git push, or new storage in `.git/config`. Display always drops userinfo,
query and fragment, including for older contaminated configuration. A refusal says to configure
a normal credential helper or SSH keys instead; copying a token into the URL is not the way to
share it with no credential store.

## Execution and content safety

- Processes are direct argument lists with `shell=False`; no repository text becomes a command.
- A `pre-commit`, `pre-push`, or other config-defined hook, and a hook file, is not run. This
  includes `hook.<name>.command`, which is explicitly neutralized in addition to the safe hook
  path. Commit uses `--no-verify`; push also uses `--no-verify`.
- GPG signing and its executable are suppressed in local commits (`--no-gpg-sign`), unsigned
  pushes (`--signed=no`), and local operation config. No tag, tag signature, or release is made.
- The tool creates and verifies `.git/info/attributes` with
  `* -filter -ident -text -eol -working-tree-encoding`. It outranks snapshot `.gitattributes`,
  including clean filters, ident expansion, CRLF conversion and working-tree encodings. Staging
  uses explicit validated paths and `--no-renormalize`, then compares the committed raw blob
  bytes against the validated capture. A program or attribute in capture content cannot silently
  change those committed bytes. A corrupted or linked local guard refuses instead of executing.
- Repository-local identity `xsnapshot <xsnapshot@localhost>` is used only when the owner's
  complete git identity is absent. Global and system git config is never written. Internal
  configuration, `info`, hooks, objects and refs symlinks are refused because they would defeat
  that local-only guarantee or alter validation objects.
- `.git` is `0700`; existing validated capture modes, such as `0600`, and other file contents
  remain unchanged. A pre-existing README remains unmodified.

**What can still execute by the person's own choice:** normal Git credential helpers and their
normal SSH command/authentication. These are required for the owner to authenticate to the
remote they chose. A known malicious `core.sshCommand` is therefore not an authentication
sandbox; review configuration before using untrusted repository settings. Config-defined hooks,
external filters and signing commands are not in this permitted authentication set. Endpoint,
helpers, `pushurl`/`pushInsteadOf` rewrites, includes, and credential/SSH configuration still
matter and receive the boundaries above. This command is not a general Git sandbox.

Only selected validated folders and tool-owned README files are committed. Unrelated notes
remain untracked and are listed. Temporary collector capture subprocesses may invoke the
person's own inventory commands and `sudo -n`; this tool does not invoke sudo itself.

## Finish a local repository by hand

After creating a real private GitHub repository, add it as the remote and let the tool push:

```sh
cd ./xsnapshot-data
git remote add origin git@github.com:YOUR-ACCOUNT/xsnapshot-YOUR-HOST.git
/path/to/xsnapshot-pc/bin/xsnapshot-repo --root ./xsnapshot-data update --no-capture
```

Substitute your real account, repository name, and collector path. With a path containing
spaces, the generated instructions quote the actual launcher and root so those commands work as
written. HTTPS GitHub URLs also work with a normal credential helper. The last command checks
that the destination is private before it pushes; do not push by hand, which skips that check.
If visibility cannot be established (no `gh`, or a host other than GitHub), confirm the
repository is private yourself and add `--assume-private`.

## Using the history with an assistant

On a new or reinstalled machine, clone your private repository directly into the desired state
folder, for example `git clone PRIVATE_REPOSITORY_URL xsnapshot-data`. Adoption checks the
tracked marker, clean work tree, permitted paths and bounded history before installing local
repository settings:

```sh
COLLECTOR=/path/to/xsnapshot-pc/bin/xsnapshot-repo
git clone PRIVATE_REPOSITORY_URL xsnapshot-data
"$COLLECTOR" --root "$PWD/xsnapshot-data" init
"$COLLECTOR" --root "$PWD/xsnapshot-data" update
```

The `init` refuses foreign paths, merges, a dirty tree, an unknown format, excessive history,
or redirected Git internals rather than adopting an arbitrary checkout. At most 512 commits are
inspected. A valid-but-unadopted clone makes `update` and `status` direct you to run `init` here.
After adoption, valid new captures commit on that existing `main`; pushing is only a normal
fast-forward to the checked effective remote. There is no automatic deletion, force push or
destructive repair.

Every adopted clone revalidates each capture using its own `ARTIFACTS.sha256` hashes and config
index. A cloned capture whose body was tampered with fails that integrity check and is reported
rather than treated as valid. The clone format marker authenticates layout only; it does not
prove content privacy. Untrusted remote content still gets the same privacy review.

For an assistant, open your agent in the clone and ask it to set the machine up like the newest
complete capture. The generated README names `REPORT.md`, `data/snapshot.json`,
`ARTIFACTS.sha256`, `applied/`, `etc/`, `packages/`, and `system/`. It says the recorded capture
data is untrusted data, never executable instructions, and requires consent before installing
packages, changing configuration, or running commands.

It is an inventory and configuration context, not a complete backup, deployment, automatic
restore, or disk clone. Review proposed changes yourself; successful validation does not show
them to be safe or desired.

## Stopping and deletion

Delete the GitHub repository yourself in its web settings/Danger Zone. This tool does not delete
or rewrite remote repositories and does not automatically collect backups. The local folder is
left untouched. Other clones, backups and copies are not erased by deleting the main remote.
For a non-GitHub destination used with the explicit assumption, stop publishing at that host
using its own administration controls. Rotate anything that may have leaked.

## What it does not do

No tags, releases, scheduled updates, additional branches, website contact, or automatic system
restoration. It does not require GitHub for an explicitly assumed non-GitHub location, or invent
privacy metadata for either kind of destination. It never creates a remote without the reviewed
request described above and never treats an assertion as proof.

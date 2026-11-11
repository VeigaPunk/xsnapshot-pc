#Requires -Version 5.1
# xsnapshot installer - Windows.
# When run from a checkout it uses that tree. When piped or downloaded it
# only runs a collector pin that matches a reviewed tag and commit, the same
# rule as install.sh. A feature branch is not a pin; clone the branch and run
# bin/xsnapshot.ps1 until a tagged Windows release exists.
# The collector writes snapshot.json and REPORT.md. It does not upload.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Release pin: filled when a tagged Windows collector release is published.
# Bump only to a new reviewed tag and its exact 40-hex commit, never a branch.
# These are constants on purpose: no environment variable can override the pin.
$CollectorTag = ''
$CollectorCommit = ''
$RepoUrl = 'https://github.com/VeigaPunk/xsnapshot-pc.git'

function Fail([string]$Message) {
    Write-Error ($Message + ' Nothing was collected or uploaded.')
    exit 1
}

function Get-LocalCheckoutRoot {
    $candidates = @()
    if ($PSScriptRoot) { $candidates += $PSScriptRoot }
    if ($MyInvocation.MyCommand.Path) {
        $candidates += (Split-Path -Parent $MyInvocation.MyCommand.Path)
    }
    $candidates += (Get-Location).Path
    foreach ($c in $candidates) {
        if ([string]::IsNullOrWhiteSpace($c)) { continue }
        $entry = Join-Path $c 'bin\xsnapshot.ps1'
        $lib = Join-Path $c 'lib\XSnapshot.ps1'
        if ((Test-Path -LiteralPath $entry) -and (Test-Path -LiteralPath $lib)) { return $c }
    }
    return $null
}

$local = Get-LocalCheckoutRoot
if ($local) {
    Write-Host "Running the Windows collector from this checkout (not a pinned release): $local"
    $state = $env:XSNAPSHOT_STATE_DIR
    if ([string]::IsNullOrWhiteSpace($state)) { $state = Join-Path (Get-Location).Path 'xsnapshot-data' }
    $snapId = $env:XSNAPSHOT_SNAPSHOT
    $forceArgs = @()
    if ($env:XSNAPSHOT_FORCE -eq '1') { $forceArgs = @('--force') }
    $argsList = @('--root', $state, 'collect')
    if ($snapId) { $argsList += @('--snapshot', $snapId) }
    $argsList += $forceArgs
    $entry = Join-Path $local 'bin\xsnapshot.ps1'
    & $entry @argsList
    exit $LASTEXITCODE
}

if ([string]::IsNullOrWhiteSpace($CollectorTag) -or $CollectorCommit -notmatch '^[0-9a-f]{40}$') {
    Write-Host @'
Installer unavailable: a verified tagged Windows collector release has not been pinned.

The official one-liner will work once a reviewed tag is published and this
script's CollectorTag / CollectorCommit constants are set to it. Until then:

  git clone https://github.com/VeigaPunk/xsnapshot-pc.git
  cd xsnapshot-pc
  git checkout <branch-or-tag>
  powershell -NoProfile -ExecutionPolicy Bypass -File .\bin\xsnapshot.ps1 --root $env:USERPROFILE\xsnapshot-data collect --snapshot YYYY-MM-DD-label

Nothing was downloaded, executed, or uploaded.
'@
    exit 1
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Fail 'git is required to fetch the collector.' }
$dest = $env:XSNAPSHOT_DIR
if ([string]::IsNullOrWhiteSpace($dest)) { $dest = Join-Path (Get-Location).Path 'xsnapshot-pc' }
$stateDir = $env:XSNAPSHOT_STATE_DIR
if ([string]::IsNullOrWhiteSpace($stateDir)) { $stateDir = Join-Path (Get-Location).Path 'xsnapshot-data' }
$snapId = Get-Date -Format 'yyyy-MM-dd'

Get-ChildItem Env:GIT_* -ErrorAction SilentlyContinue | ForEach-Object { Remove-Item "Env:$($_.Name)" }
$env:GIT_CONFIG_NOSYSTEM = '1'
$env:GIT_CONFIG_GLOBAL = 'NUL'
$env:GIT_TERMINAL_PROMPT = '0'
$env:GIT_ALLOW_PROTOCOL = 'https'
$env:GIT_NO_REPLACE_OBJECTS = '1'
$gitArgs = @('-c','core.fsmonitor=false','-c','core.hooksPath=NUL','-c','init.templateDir=','-c','core.attributesFile=NUL')

if (Test-Path -LiteralPath (Join-Path $dest '.git')) {
    # verify below
} elseif (Test-Path -LiteralPath $dest) {
    Fail "Refusing to use ${dest}: it exists and is not a git checkout. Set XSNAPSHOT_DIR to a new, nonexistent path."
} else {
    & git @gitArgs -c advice.detachedHead=false clone --depth 1 --branch $CollectorTag -- $RepoUrl $dest
    if ($LASTEXITCODE -ne 0) { Fail 'Cannot clone the pinned collector.' }
}
$origin = (& git @gitArgs -C $dest remote get-url origin).Trim()
if ($origin -ne $RepoUrl) { Fail 'Collector origin differs from the official repository.' }
$head = (& git @gitArgs -C $dest rev-parse --verify HEAD).Trim()
if ($head -ne $CollectorCommit) { Fail 'Collector checkout does not match the pinned commit. Nothing was executed.' }
$tagRef = "refs/tags/${CollectorTag}^{commit}"
$tagCommit = (& git @gitArgs -C $dest rev-parse --verify $tagRef).Trim()
if ($tagCommit -ne $CollectorCommit) { Fail 'Collector tag does not match the pinned commit. Nothing was executed.' }
$status = (& git @gitArgs -C $dest status --porcelain --untracked-files=all)
if ($status) { Fail 'Refusing to execute a dirty collector checkout. Preserve your changes and use a new XSNAPSHOT_DIR.' }

$entry = Join-Path $dest 'bin\xsnapshot.ps1'
$lib = Join-Path $dest 'lib\XSnapshot.ps1'
if (-not (Test-Path -LiteralPath $entry) -or -not (Test-Path -LiteralPath $lib)) {
    Fail 'Pinned collector is missing the Windows entry point.'
}
$forceArgs = @()
if ($env:XSNAPSHOT_FORCE -eq '1') { $forceArgs = @('--force') }
& $entry --root $stateDir collect --snapshot $snapId @forceArgs
exit $LASTEXITCODE

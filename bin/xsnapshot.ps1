#Requires -Version 5.1
# Windows entry point for xsnapshot-pc. Pins the library beside this script.
# Privileged mode is not used; the collector never requires elevation.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not $PSScriptRoot) {
    Write-Error 'xsnapshot.ps1 must be run as a file so it can locate lib/XSnapshot.ps1'
    exit 2
}
$lib = Join-Path (Split-Path -Parent $PSScriptRoot) 'lib\XSnapshot.ps1'
if (-not (Test-Path -LiteralPath $lib)) {
    Write-Error "missing collector library: $lib"
    exit 2
}
. $lib
$code = Invoke-XsnapshotMain -Argv @($args)
if ($null -eq $code) { $code = 0 }
exit [int]$code

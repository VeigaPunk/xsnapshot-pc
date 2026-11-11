#Requires -Version 5.1
# Redaction unit tests for the Windows collector. Safe synthetic fixtures only.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $root) { $root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path }
. (Join-Path $root 'lib\XSnapshot.ps1')

$script:Failures = 0
$script:Passes = 0

function Assert-True([bool]$Condition, [string]$Name) {
    if ($Condition) { $script:Passes++; Write-Host "ok - $Name" }
    else { $script:Failures++; Write-Host "not ok - $Name" }
}

# Synthetic identity, not a real account.
$script:UserName = 'AdaTestUser'
$script:HomePath = 'C:\Users\AdaTestUser'
$script:HomeSlash = 'C:/Users/AdaTestUser'
$script:HomeAlt = 'C:\Users\AdaTestUser'

$uuid = '8f1c2d3e-4a5b-4c6d-8e9f-0a1b2c3d4e5f'
$r = Invoke-XsnapshotRedact -Text ('disk ' + $uuid)
Assert-True ($r.Text -notmatch $uuid) 'uuid is removed'
Assert-True ($r.Text -match '<uuid>') 'uuid becomes <uuid>'

$r = Invoke-XsnapshotRedact -Text 'link/ether 00:00:5e:00:53:0a and 00-00-5E-00-53-0B'
Assert-True ($r.Text -notmatch '00:00:5e:00:53:0a') 'colon mac is removed'
Assert-True ($r.Text -notmatch '00-00-5E-00-53-0B') 'hyphen mac is removed'
Assert-True ($r.Text -match '<mac>') 'mac becomes <mac>'

$r = Invoke-XsnapshotRedact -Text 'nameserver 192.0.2.53'
Assert-True ($r.Text -notmatch '192.0.2.53') 'documentation IPv4 is removed'
Assert-True ($r.Text -match '<ip>') 'IPv4 becomes <ip>'

$r = Invoke-XsnapshotRedact -Text 'contact ops@example.com'
Assert-True ($r.Text -notmatch 'ops@example.com') 'email is removed'
Assert-True ($r.Text -match '<email>') 'email becomes <email>'

$r = Invoke-XsnapshotRedact -Text 'Authorization: Bearer abcdefghijklmnopqr'
Assert-True ($r.Text -match 'Bearer <redacted>') 'bearer token is redacted'

$r = Invoke-XsnapshotRedact -Text '{"password": "literal-secret-value"}'
Assert-True ($r.Text -notmatch 'literal-secret-value') 'json password is redacted'
Assert-True ($r.Text -match '<redacted>') 'json password becomes <redacted>'

$r = Invoke-XsnapshotRedact -Text 'API_TOKEN=0123456789abcdef0123'
Assert-True ($r.Text -notmatch '0123456789abcdef0123') 'env token is redacted'

$r = Invoke-XsnapshotRedact -Text 'organization: org-1a2b3c4d5e6f708192a3b4c5d6e7f809'
Assert-True ($r.Text -match 'org-<redacted>') 'org id is redacted'

$r = Invoke-XsnapshotRedact -Text 'account S-1-5-21-1000000000-2000000000-3000000000-1001'
Assert-True ($r.Text -match '<sid>') 'windows SID is redacted'
Assert-True ($r.Text -notmatch '1000000000') 'SID digits are removed'

$id = Invoke-XsnapshotRedactIdentity -Text 'copied from C:\Users\AdaTestUser\Documents\profile.ps1 by AdaTestUser'
Assert-True ($id.Text -notmatch 'AdaTestUser') 'account name is removed'
Assert-True ($id.Text -match 'C:\\Users\\user') 'profile path becomes C:\Users\user'
Assert-True ($id.Count -ge 1) 'identity redaction counts at least once'

$slash = Invoke-XsnapshotRedactIdentity -Text 'path=C:/Users/AdaTestUser/file'
Assert-True ($slash.Text -eq 'path=C:/Users/user/file') 'slash profile path is redacted in kind'

$json = ConvertTo-XsnapshotJson -Value ([ordered]@{ schema = 'xsnapshot/v1'; ok = $true; n = 2; missing = $null; list = @('a','b') })
Assert-True ($json -match '"schema": "xsnapshot/v1"') 'json encoder writes schema'
Assert-True ($json -match '"ok": true') 'json encoder writes lowercase true'
Assert-True ($json -notmatch 'NaN|Infinity') 'json encoder has no non-finite numbers'

if ($script:Failures -gt 0) {
    Write-Host "$script:Passes passed, $script:Failures failed"
    exit 1
}
Write-Host "$script:Passes passed"
exit 0

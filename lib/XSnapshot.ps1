#Requires -Version 5.1
# xsnapshot-pc Windows collector. Schema xsnapshot/v1.
# Allow-listed, redacted, local-only inventory. Nothing is uploaded.
# Compatible with Windows PowerShell 5.1 and PowerShell 7.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:Schema = 'xsnapshot/v1'
$script:CollectorVersion = '1.2.0-windows'
$script:MaxConfigBytes = 1MB
$script:MaxSnapshotBytes = 64MB
$script:MaxSnapshotFiles = 4096
$script:RedactionTotal = 0
$script:Artifacts = [System.Collections.Generic.List[object]]::new()
$script:ConfigIndex = [System.Collections.Generic.List[object]]::new()
$script:Notes = [System.Collections.Generic.List[string]]::new()
$script:Commands = [System.Collections.Generic.List[object]]::new()
$script:OutDir = $null
$script:SnapshotId = $null
$script:CapturedAt = $null
$script:Data = $null
$script:HomePath = $null
$script:UserName = $null
$script:HomeSlash = $null
$script:HomeAlt = $null

function Get-XsnapshotIsWindows {
    return ($env:OS -eq 'Windows_NT') -or ([System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT)
}


function New-XsnapshotBag {
    $bag = New-Object System.Collections.Specialized.OrderedDictionary
    $argsLocal = $args
    if ($argsLocal.Count % 2 -ne 0) { throw 'New-XsnapshotBag requires name/value pairs' }
    for ($i = 0; $i -lt $argsLocal.Count; $i += 2) {
        $bag[[string]$argsLocal[$i]] = $argsLocal[$i + 1]
    }
    return $bag
}

function Initialize-XsnapshotIdentity {
    $script:UserName = [Environment]::UserName
    $script:HomePath = [Environment]::GetFolderPath('UserProfile')
    if ([string]::IsNullOrWhiteSpace($script:HomePath)) {
        $script:HomePath = $env:USERPROFILE
    }
    $script:HomeSlash = $script:HomePath -replace '\\', '/'
    $homeDrive = $env:HOMEDRIVE
    $homePathEnv = $env:HOMEPATH
    if ($homeDrive -and $homePathEnv) {
        $script:HomeAlt = ($homeDrive + $homePathEnv)
    } else {
        $script:HomeAlt = $script:HomePath
    }
}

function ConvertTo-XsnapshotJson {
    param($Value, [int]$Level = 0)
    $nl = "`n"
    $pad = '  ' * $Level
    $inner = '  ' * ($Level + 1)
    if ($null -eq $Value) { return 'null' }
    $t = $Value.GetType()
    if ($Value -is [bool] -or $t.FullName -eq 'System.Boolean') {
        if ($Value) { return 'true' } else { return 'false' }
    }
    if ($Value -is [int] -or $Value -is [long] -or $Value -is [int16] -or $Value -is [uint16] -or $Value -is [uint32] -or $Value -is [uint64] -or $t.IsEnum) {
        return [string][int64]$Value
    }
    if ($Value -is [double] -or $Value -is [decimal] -or $Value -is [float] -or $Value -is [single]) {
        if ([double]::IsNaN([double]$Value) -or [double]::IsInfinity([double]$Value)) {
            throw 'non-finite JSON constants are not permitted'
        }
        return (([double]$Value).ToString('G17', [CultureInfo]::InvariantCulture))
    }
    if ($Value -is [string] -or $Value -is [char]) {
        return ('"' + (Escape-XsnapshotJsonString ([string]$Value)) + '"')
    }
    if ($Value -is [System.Collections.IDictionary]) {
        $keys = @($Value.Keys)
        if ($keys.Count -eq 0) { return '{}' }
        $parts = New-Object System.Collections.Generic.List[string]
        foreach ($k in $keys) {
            $ks = Escape-XsnapshotJsonString ([string]$k)
            $vs = ConvertTo-XsnapshotJson -Value $Value[$k] -Level ($Level + 1)
            $parts.Add(('{0}"{1}": {2}' -f $inner, $ks, $vs)) | Out-Null
        }
        return ('{' + $nl + ($parts -join (',' + $nl)) + $nl + $pad + '}')
    }
    if ($Value -is [System.Collections.IEnumerable] -and -not ($Value -is [string])) {
        $items = @($Value)
        if ($items.Count -eq 0) { return '[]' }
        $parts = New-Object System.Collections.Generic.List[string]
        foreach ($item in $items) {
            $parts.Add($inner + (ConvertTo-XsnapshotJson -Value $item -Level ($Level + 1))) | Out-Null
        }
        return ('[' + $nl + ($parts -join (',' + $nl)) + $nl + $pad + ']')
    }
    return ('"' + (Escape-XsnapshotJsonString ([string]$Value)) + '"')
}

function Escape-XsnapshotJsonString {
    param([string]$Text)
    if ($null -eq $Text) { return '' }
    $sb = New-Object System.Text.StringBuilder
    foreach ($ch in $Text.ToCharArray()) {
        $c = [int]$ch
        switch ($ch) {
            '"' { [void]$sb.Append('\"') }
            '\' { [void]$sb.Append('\\') }
            "`b" { [void]$sb.Append('\b') }
            "`f" { [void]$sb.Append('\f') }
            "`n" { [void]$sb.Append('\n') }
            "`r" { [void]$sb.Append('\r') }
            "`t" { [void]$sb.Append('\t') }
            default {
                if ($c -lt 32) {
                    [void]$sb.Append(('\u{0:x4}' -f $c))
                } else {
                    [void]$sb.Append($ch)
                }
            }
        }
    }
    return $sb.ToString()
}

function Protect-XsnapshotMatches {
    param([string]$Text, [string]$Pattern, [string]$Label, [System.Collections.IDictionary]$Store)
    return [regex]::Replace($Text, $Pattern, {
        param($m)
        $key = '__XS_{0}_{1}__' -f $Label, $Store.Count
        $Store[$key] = $m.Value
        return $key
    })
}

function Invoke-XsnapshotRedact {
    param(
        [string]$Text,
        [switch]$ProtectVersions
    )
    if ($null -eq $Text) { $Text = '' }
    $n = 0
    $protected = @{}
    $s = $Text
    if ($ProtectVersions) {
        $s = Protect-XsnapshotMatches -Text $s -Pattern '\b\d+\.\d+\.\d+(?:\.\d+)?\b' -Label 'VER' -Store $protected
    }

    $subs = @(
        @{ p = '(?im)^(\s*(?:Machine ID|Boot ID|machine-id|boot-id|MachineGuid|ProductId)\s*[:=]\s*)[0-9a-fA-F-]{16,}\s*$'; r = '${1}<redacted>' },
        @{ p = '(?i)(machine-id=)[0-9a-f]{16,}'; r = '${1}<redacted>' },
        @{ p = '(?i)(PARTUUID=)[0-9A-Fa-f-]{4,}'; r = '${1}<uuid>' },
        @{ p = '(?i)(UUID=)[0-9A-Fa-f-]{4,}'; r = '${1}<uuid>' },
        @{ p = '\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b'; r = '<uuid>' },
        @{ p = '\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b'; r = '<mac>' },
        @{ p = '\b(?:[0-9A-Fa-f]{2}-){5}[0-9A-Fa-f]{2}\b'; r = '<mac>' },
        @{ p = '(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])'; r = '<ip>' },
        @{ p = '(?<![\w:])(?:::1|::)(?![\w:])'; r = '<ipv6>' },
        @{ p = '\[[0-9A-Fa-f]*:[0-9A-Fa-f:]*:[0-9A-Fa-f:.]*\]'; r = '<ipv6>' }
    )
    foreach ($rule in $subs) {
        $new = [regex]::Replace($s, $rule.p, $rule.r)
        if ($new -cne $s) {
            $n += [regex]::Matches($s, $rule.p).Count
            $s = $new
        }
    }

    $ipv6Re = [regex]'(?<![\w:])(?:[0-9A-Fa-f]{0,4}:){2,}[0-9A-Fa-f]{0,4}(?:%[A-Za-z0-9_.-]+)?(?![\w:])'
    $s = $ipv6Re.Replace($s, {
        param($m)
        $token = $m.Value
        $addr = ($token -split '%')[0]
        try {
            [void][System.Net.IPAddress]::Parse($addr)
            $script:IPv6Hit = $true
            return '<ipv6>'
        } catch {
            return $token
        }
    })
    # Count IPv6 replacements approximately via marker later.

    $more = @(
        @{ p = '\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b'; r = '<email>' },
        @{ p = '(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}'; r = 'Bearer <redacted>' },
        @{ p = '(?i)("(?:password|passwd|secret|token|api[_-]?key|access[_-]?key|refresh[_-]?token|client[_-]?secret|private[_-]?key|auth[_-]?token|org_id)"\s*:\s*")[^"]{4,}(")'; r = '${1}<redacted>${2}' },
        @{ p = '(?im)^(\s*(?:password|passwd|secret|token|api[_-]?key|access[_-]?key|refresh[_-]?token|client[_-]?secret|private[_-]?key|auth[_-]?token)\s*[:=]\s*)([''"]?)(?!\$)([A-Za-z0-9._~+/=-]{16,})\2\s*$'; r = '${1}${2}<redacted>${2}' },
        @{ p = '(?i)(\b[A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|API_KEY|ACCESS_KEY|PRIVATE_KEY|AUTH_KEY)\b\s*=\s*)([''"]?)(?!\$)([A-Za-z0-9._~+/=-]{16,})\2'; r = '${1}${2}<redacted>${2}' },
        @{ p = '(?im)(\b[A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|ACCESS_KEY|PRIVATE_KEY|AUTH_KEY|_KEY)\b\s*[:=]\s*)([''"]?)(?!\$)([A-Za-z0-9._~+/=-]{12,})\2'; r = '${1}${2}<redacted>${2}' },
        @{ p = '(?im)^(\s*Serial Number:\s*)(?!To be filled)(.+)$'; r = '${1}<redacted>' },
        @{ p = '(?im)^(\s*UUID:\s*)(.+)$'; r = '${1}<redacted>' },
        @{ p = '(?im)^(\s*serial:\s*).+$'; r = '${1}<redacted>' },
        @{ p = '(?im)^(\s*(?:SerialNumber|SerialNumberId|BIOSSerialNumber|BaseBoardSerialNumber|ChassisSerialNumber)\s*[:=]\s*).+$'; r = '${1}<redacted>' },
        @{ p = '\bS-1-5-21-(?:\d+-){2}\d+(?:-\d+)?\b'; r = '<sid>' },
        @{ p = '(?m)(#[0-9a-f]{64,})'; r = '#<redacted-hash>' },
        @{ p = '\borg-[0-9a-f]{16,}\b'; r = 'org-<redacted>' }
    )
    foreach ($rule in $more) {
        $matchesFound = [regex]::Matches($s, $rule.p)
        if ($matchesFound.Count -gt 0) {
            $n += $matchesFound.Count
            $s = [regex]::Replace($s, $rule.p, $rule.r)
        }
    }

    $idResult = Invoke-XsnapshotRedactIdentity -Text $s
    $s = $idResult.Text
    $n += $idResult.Count

    foreach ($key in @($protected.Keys)) {
        $s = $s.Replace($key, $protected[$key])
    }
    return @{ Text = $s; Count = $n }
}

function Invoke-XsnapshotRedactIdentity {
    param([string]$Text)
    if ($null -eq $Text) { $Text = '' }
    if (-not $script:HomePath) { Initialize-XsnapshotIdentity }
    $n = 0
    $s = $Text
    $forms = New-Object System.Collections.Generic.List[string]
    foreach ($homeDir in @($script:HomePath, $script:HomeSlash, $script:HomeAlt)) {
        if ([string]::IsNullOrWhiteSpace($homeDir) -or $homeDir.Length -lt 3) { continue }
        foreach ($form in @($homeDir, ($homeDir -replace '\\', '/'))) {
            if (-not $forms.Contains($form)) { $forms.Add($form) | Out-Null }
        }
    }
    # Longer forms first so drive+path wins over a short fragment.
    $ordered = $forms | Sort-Object { $_.Length } -Descending
    $homeDirReplaced = $false
    foreach ($form in $ordered) {
        if ($s.IndexOf($form, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) { continue }
        $replacement = 'C:\Users\user'
        if ($form -match '/') { $replacement = 'C:/Users/user' }
        $s = [regex]::Replace($s, [regex]::Escape($form), $replacement, 'IgnoreCase')
        $homeDirReplaced = $true
    }
    if ($homeDirReplaced) { $n += 1 }
    if ($script:UserName -and $script:UserName.Length -ge 2) {
        $pattern = '(?i)(?<![A-Za-z0-9])' + [regex]::Escape($script:UserName) + '(?![A-Za-z0-9])'
        $found = [regex]::Matches($s, $pattern)
        if ($found.Count -gt 0) {
            $n += $found.Count
            $s = [regex]::Replace($s, $pattern, 'user')
        }
    }
    return @{ Text = $s; Count = $n }
}

function ConvertFrom-XsnapshotRedact {
    param([string]$Text, [switch]$ProtectVersions)
    $r = Invoke-XsnapshotRedact -Text $Text -ProtectVersions:$ProtectVersions
    $script:RedactionTotal += [int]$r.Count
    return $r.Text
}

function Test-XsnapshotReparsePoint {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    try {
        $item = Get-Item -LiteralPath $Path -Force
        return [bool]($item.Attributes -band [IO.FileAttributes]::ReparsePoint)
    } catch { return $true }
}

function Set-XsnapshotOwnerOnlyAcl {
    param([string]$Path)
    $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $item = Get-Item -LiteralPath $Path -Force
    $acl = New-Object System.Security.AccessControl.DirectorySecurity
    $isDir = $item.PSIsContainer
    if (-not $isDir) { $acl = New-Object System.Security.AccessControl.FileSecurity }
    $acl.SetAccessRuleProtection($true, $false)
    $inherit = [System.Security.AccessControl.InheritanceFlags]::None
    $prop = [System.Security.AccessControl.PropagationFlags]::None
    if ($isDir) {
        $inherit = [System.Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [System.Security.AccessControl.InheritanceFlags]::ObjectInherit
    }
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($user, 'FullControl', $inherit, $prop, 'Allow')
    $acl.SetAccessRule($rule)
    if ($isDir) { [System.IO.Directory]::SetAccessControl($Path, $acl) }
    else { [System.IO.File]::SetAccessControl($Path, $acl) }
}

function New-XsnapshotPrivateDirectory {
    param([string]$Path)
    if (Test-Path -LiteralPath $Path) {
        if (Test-XsnapshotReparsePoint -Path $Path) { throw "refusing a symlink snapshot destination: $Path" }
        $item = Get-Item -LiteralPath $Path -Force
        if (-not $item.PSIsContainer) { throw "capture state must use directories, not files: $Path" }
        if (Get-XsnapshotIsWindows) { Set-XsnapshotOwnerOnlyAcl -Path $Path }
        return
    }
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-XsnapshotPrivateDirectory -Path $parent
    }
    if ($parent -and (Test-XsnapshotReparsePoint -Path $parent)) { throw "refusing a symlink parent: $parent" }
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
    if (Get-XsnapshotIsWindows) { Set-XsnapshotOwnerOnlyAcl -Path $Path }
}

function Write-XsnapshotPrivateFile {
    param([string]$Rel, [byte[]]$Body)
    $relNorm = ConvertTo-XsnapshotRelPath -Path $Rel
    $dest = Join-Path $script:OutDir ($relNorm -replace '/', [IO.Path]::DirectorySeparatorChar)
    $parent = Split-Path -Parent $dest
    New-XsnapshotPrivateDirectory -Path $parent
    if (Test-Path -LiteralPath $dest) {
        if (Test-XsnapshotReparsePoint -Path $dest) { throw "refusing to write through a reparse point: $relNorm" }
        Remove-Item -LiteralPath $dest -Force
    }
    $fs = [System.IO.File]::Open($dest, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    try { $fs.Write($Body, 0, $Body.Length) } finally { $fs.Dispose() }
    if (Get-XsnapshotIsWindows) { Set-XsnapshotOwnerOnlyAcl -Path $dest }
    return $dest
}

function ConvertTo-XsnapshotRelPath {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path) -or $Path.Contains('\') -or $Path.Contains('..') -or $Path.StartsWith('/')) {
        throw "invalid snapshot-relative path: $Path"
    }
    foreach ($ch in $Path.ToCharArray()) {
        if ([int]$ch -lt 32) { throw "control character in snapshot path" }
    }
    return $Path
}

function ConvertTo-XsnapshotUtf8Body {
    param([string]$Text)
    if ($null -eq $Text) { $Text = '' }
    $normalized = $Text.TrimEnd() + "`n"
    return [System.Text.Encoding]::UTF8.GetBytes($normalized)
}

function Add-XsnapshotArtifact {
    param([string]$Rel, [byte[]]$Body)
    $relNorm = ConvertTo-XsnapshotRelPath -Path $Rel
    $sha = Get-XsnapshotSha256 -Body $Body
    $script:Artifacts.Add([ordered]@{
        path = $relNorm
        bytes = [int]$Body.Length
        sha256 = $sha
    }) | Out-Null
}

function Get-XsnapshotSha256 {
    param([byte[]]$Body)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hash = $sha.ComputeHash($Body)
        return ([BitConverter]::ToString($hash) -replace '-', '').ToLowerInvariant()
    } finally { $sha.Dispose() }
}

function Write-XsnapshotText {
    param([string]$Rel, [string]$Text, [switch]$Sanitize, [switch]$SkipArtifact)
    if ($Sanitize) { $Text = ConvertFrom-XsnapshotRedact -Text $Text }
    $body = ConvertTo-XsnapshotUtf8Body -Text $Text
    Write-XsnapshotPrivateFile -Rel $Rel -Body $body | Out-Null
    if (-not $SkipArtifact) { Add-XsnapshotArtifact -Rel $Rel -Body $body }
}

function Write-XsnapshotSection {
    param([string]$Rel, [object[]]$Sections)
    $chunks = New-Object System.Collections.Generic.List[string]
    foreach ($sec in $Sections) {
        $title = [string]$sec[0]
        $body = [string]$sec[1]
        if ($null -eq $body) { $body = '' }
        $chunks.Add(("## {0}`n`n{1}`n" -f $title, $body.TrimEnd())) | Out-Null
    }
    $text = ConvertFrom-XsnapshotRedact -Text ($chunks -join "`n")
    Write-XsnapshotText -Rel $Rel -Text $text
}

function Copy-XsnapshotAllowlistedFile {
    param([string]$Source, [string]$Rel)
    if ([string]::IsNullOrWhiteSpace($Source) -or -not (Test-Path -LiteralPath $Source)) {
        return $false
    }
    if (Test-XsnapshotReparsePoint -Path $Source) {
        $script:Notes.Add("skipped symlink: $Source") | Out-Null
        return $false
    }
    $item = Get-Item -LiteralPath $Source -Force
    if ($item.PSIsContainer) {
        $script:Notes.Add("skipped directory (not recursively copied unless allow-listed): $Source") | Out-Null
        return $false
    }
    if ($item.Length -gt $script:MaxConfigBytes) {
        $script:Notes.Add("skipped oversized allow-listed file (${item.Length} bytes): $Source") | Out-Null
        return $false
    }
    $bytes = [System.IO.File]::ReadAllBytes($Source)
    $text = [System.Text.Encoding]::UTF8.GetString($bytes)
    # Reject obviously binary files (NUL).
    if ($text.Contains([char]0)) {
        $script:Notes.Add("skipped binary allow-listed file: $Source") | Out-Null
        return $false
    }
    $red = Invoke-XsnapshotRedact -Text $text
    $script:RedactionTotal += [int]$red.Count
    $body = ConvertTo-XsnapshotUtf8Body -Text $red.Text
    Write-XsnapshotPrivateFile -Rel $Rel -Body $body | Out-Null
    $sha = Get-XsnapshotSha256 -Body $body
    $sourceDisplay = $Source
    $id = Invoke-XsnapshotRedactIdentity -Text $sourceDisplay
    $sourceDisplay = $id.Text
    $script:ConfigIndex.Add([ordered]@{
        source = $sourceDisplay
        path = $Rel
        bytes = [int]$body.Length
        snapshot_sha256 = $sha
        redactions = [int]$red.Count
    }) | Out-Null
    $script:Artifacts.Add([ordered]@{
        path = $Rel
        bytes = [int]$body.Length
        sha256 = $sha
    }) | Out-Null
    return $true
}

function Invoke-XsnapshotRecordedCommand {
    param([scriptblock]$Script, [string]$Name, [int]$TimeoutSec = 30)
    $started = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss')
    $stdout = ''
    $stderr = ''
    $code = 0
    try {
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        $out = & $Script 2>&1
        $ErrorActionPreference = $prevEap
        $lines = New-Object System.Collections.Generic.List[string]
        $errLines = New-Object System.Collections.Generic.List[string]
        foreach ($item in @($out)) {
            if ($item -is [System.Management.Automation.ErrorRecord]) {
                $errLines.Add([string]$item) | Out-Null
            } else {
                $lines.Add([string]$item) | Out-Null
            }
        }
        $stdout = ($lines -join "`n").TrimEnd()
        $stderr = ($errLines -join "`n").TrimEnd()
    } catch {
        $code = 1
        $stderr = [string]$_
    }
    $script:Commands.Add([ordered]@{
        command = $Name
        started_at = $started
        returncode = [int]$code
        stdout_bytes = [int][System.Text.Encoding]::UTF8.GetByteCount($stdout)
        stderr_bytes = [int][System.Text.Encoding]::UTF8.GetByteCount($stderr)
    }) | Out-Null
    if ($code -ne 0 -and $stderr) {
        $suffix = "[exit $code]: " + (($stderr -split "`n")[-1].Trim())
        if ($suffix.Length -gt 220) { $suffix = $suffix.Substring(0, 220) }
        if ($stdout) { return ($stdout + "`n" + $suffix) }
        return $suffix
    }
    return $stdout
}

function Get-XsnapshotNativeOutput {
    param([string]$FileName, [string[]]$ArgumentList, [string]$Name, [int]$TimeoutSec = 30)
    $cmd = Get-Command $FileName -ErrorAction SilentlyContinue
    if (-not $cmd) {
        $script:Notes.Add("tool not on PATH: $FileName") | Out-Null
        return $null
    }
    $started = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss')
    $stdout = ''
    $stderr = ''
    $code = 0
    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $cmd.Source
        if ($ArgumentList) { $psi.Arguments = ($ArgumentList -join ' ') }
        $psi.UseShellExecute = $false
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.CreateNoWindow = $true
        $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
        $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8
        $proc = New-Object System.Diagnostics.Process
        $proc.StartInfo = $psi
        [void]$proc.Start()
        $stdout = $proc.StandardOutput.ReadToEnd()
        $stderr = $proc.StandardError.ReadToEnd()
        if (-not $proc.WaitForExit($TimeoutSec * 1000)) {
            try { $proc.Kill() } catch {}
            $code = 124
            $stderr = "timed out after ${TimeoutSec}s"
        } else {
            $code = $proc.ExitCode
        }
        $stdout = $stdout.TrimEnd()
        $stderr = $stderr.TrimEnd()
    } catch {
        $code = 1
        $stderr = [string]$_
    }
    $script:Commands.Add([ordered]@{
        command = $Name
        started_at = $started
        returncode = [int]$code
        stdout_bytes = [int][System.Text.Encoding]::UTF8.GetByteCount($stdout)
        stderr_bytes = [int][System.Text.Encoding]::UTF8.GetByteCount($stderr)
    }) | Out-Null
    if ($code -ne 0) { return $null }
    return $stdout
}


function Get-XsnapshotProperty {
    param($Object, [string]$Name, $Default = $null)
    if ($null -eq $Object) { return $Default }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -eq $prop) { return $Default }
    return $prop.Value
}

function Get-XsnapshotFirst {
    param([string[]]$Values, [string]$Default = 'unknown')
    foreach ($v in $Values) {
        if (-not [string]::IsNullOrWhiteSpace($v) -and $v -ne 'unknown') { return $v.Trim() }
    }
    return $Default
}

function Get-XsnapshotCim {
    param([string]$ClassName, [string]$Name, [string]$Namespace = 'root/cimv2', [string]$Filter)
    return Invoke-XsnapshotRecordedCommand -Name $Name -Script {
        if ($Filter) { Get-CimInstance -Namespace $Namespace -ClassName $ClassName -Filter $Filter -ErrorAction Stop }
        else { Get-CimInstance -Namespace $Namespace -ClassName $ClassName -ErrorAction Stop }
    }
}

function Format-XsnapshotBytes {
    param([Int64]$Value)
    if ($Value -lt 0) { return 'unknown' }
    $units = @('B','KiB','MiB','GiB','TiB','PiB')
    $n = [double]$Value
    $i = 0
    while ($n -ge 1024 -and $i -lt ($units.Count - 1)) { $n = $n / 1024; $i++ }
    return ('{0:N1} {1}' -f $n, $units[$i])
}

function Invoke-XsnapshotCim {
    param([string]$ClassName, [string]$Name, [string]$Filter)
    $started = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss')
    $errorText = ''
    $code = 0
    $result = @()
    try {
        if ($Filter) { $result = @(Get-CimInstance -ClassName $ClassName -Filter $Filter -ErrorAction Stop) }
        else { $result = @(Get-CimInstance -ClassName $ClassName -ErrorAction Stop) }
    } catch {
        $code = 1
        $errorText = [string]$_
        $script:Notes.Add("CIM query failed ($ClassName): $errorText") | Out-Null
    }
    $script:Commands.Add([ordered]@{
        command = $Name
        started_at = $started
        returncode = [int]$code
        stdout_bytes = [int]$result.Count
        stderr_bytes = [int][System.Text.Encoding]::UTF8.GetByteCount($errorText)
    }) | Out-Null
    return $result
}

function Get-XsnapshotOsInventory {
    $cs = @(Invoke-XsnapshotCim -ClassName Win32_ComputerSystem -Name 'Win32_ComputerSystem')
    $os = @(Invoke-XsnapshotCim -ClassName Win32_OperatingSystem -Name 'Win32_OperatingSystem')
    $cs0 = $null; if ($cs.Count -gt 0) { $cs0 = $cs[0] }
    $os0 = $null; if ($os.Count -gt 0) { $os0 = $os[0] }
    $caption = Get-XsnapshotFirst @($(if ($os0) { $os0.Caption }), $env:OS) 'Windows'
    $version = Get-XsnapshotFirst @($(if ($os0) { $os0.Version }), [Environment]::OSVersion.Version.ToString())
    $build = Get-XsnapshotFirst @($(if ($os0) { [string]$os0.BuildNumber }))
    $display = 'unknown'
    try {
        $nv = Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion' -ErrorAction Stop
        if ($nv.DisplayVersion) { $display = [string]$nv.DisplayVersion }
        elseif ($nv.ReleaseId) { $display = [string]$nv.ReleaseId }
        if ($nv.CurrentBuild -and $build -eq 'unknown') { $build = [string]$nv.CurrentBuild }
        if ($nv.UBR) { $build = "$build.$($nv.UBR)" }
        if ($nv.ProductName -and $caption -eq 'Windows') { $caption = [string]$nv.ProductName }
    } catch {}
    $arch = Get-XsnapshotFirst @($env:PROCESSOR_ARCHITECTURE, $(if ($os0) { $os0.OSArchitecture }), [Environment]::Is64BitOperatingSystem.ToString())
    $hostname = Get-XsnapshotFirst @($(if ($cs0) { $cs0.Name }), $env:COMPUTERNAME, [System.Net.Dns]::GetHostName())
    $chassis = 'unknown'
    if ($cs0 -and $cs0.PCSystemType) {
        switch ([int]$cs0.PCSystemType) {
            1 { $chassis = 'desktop' }
            2 { $chassis = 'laptop' }
            3 { $chassis = 'desktop' }
            4 { $chassis = 'server' }
            default { $chassis = 'type ' + [string]$cs0.PCSystemType }
        }
    }
    $domainRole = 'unknown'
    if ($cs0 -and $null -ne $cs0.DomainRole) { $domainRole = [string]$cs0.DomainRole }
    $hostObj = [ordered]@{
        hostname = $hostname
        chassis = $chassis
        machine = Get-XsnapshotFirst @($(if ($cs0) { $cs0.Manufacturer }), $(if ($cs0) { $cs0.Model }))
        kernel = $version
        architecture = $arch
        os = $caption
        os_id = 'windows'
        os_version = $display
    }
    $osObj = [ordered]@{
        name = 'Microsoft Windows'
        pretty_name = $caption
        id = 'windows'
        build_id = $build
        home_url = 'https://www.microsoft.com/windows'
        documentation_url = 'https://learn.microsoft.com/windows'
        kernel = $version
        arch = $arch
        display_version = $display
        install_date = 'redacted'
        domain_role = $domainRole
    }
    $lines = @(
        "hostname=$hostname",
        "chassis=$chassis",
        "os=$caption",
        "version=$version",
        "build=$build",
        "display_version=$display",
        "arch=$arch",
        "domain_role=$domainRole"
    )
    return @{ Host = $hostObj; Os = $osObj; Text = ($lines -join "`n") }
}

function Get-XsnapshotHardwareInventory {
    $cpu = @(Invoke-XsnapshotCim -ClassName Win32_Processor -Name 'Win32_Processor')
    $board = @(Invoke-XsnapshotCim -ClassName Win32_BaseBoard -Name 'Win32_BaseBoard')
    $bios = @(Invoke-XsnapshotCim -ClassName Win32_BIOS -Name 'Win32_BIOS')
    $cs = @(Invoke-XsnapshotCim -ClassName Win32_ComputerSystem -Name 'Win32_ComputerSystem.hardware')
    $mem = @(Invoke-XsnapshotCim -ClassName Win32_PhysicalMemory -Name 'Win32_PhysicalMemory')
    $gpu = @(Invoke-XsnapshotCim -ClassName Win32_VideoController -Name 'Win32_VideoController')
    $cpu0 = $null; if ($cpu.Count -gt 0) { $cpu0 = $cpu[0] }
    $board0 = $null; if ($board.Count -gt 0) { $board0 = $board[0] }
    $bios0 = $null; if ($bios.Count -gt 0) { $bios0 = $bios[0] }
    $cs0 = $null; if ($cs.Count -gt 0) { $cs0 = $cs[0] }

    $cpuName = Get-XsnapshotFirst @($(if ($cpu0) { $cpu0.Name }), $env:PROCESSOR_IDENTIFIER)
    $cores = 0; $threads = 0
    foreach ($c in $cpu) {
        if ($c.NumberOfCores) { $cores += [int]$c.NumberOfCores }
        if ($c.NumberOfLogicalProcessors) { $threads += [int]$c.NumberOfLogicalProcessors }
    }
    $cpuMax = 'unknown'
    if ($cpu0 -and $cpu0.MaxClockSpeed) { $cpuMax = "$($cpu0.MaxClockSpeed) MHz" }

    $modules = New-Object System.Collections.Generic.List[string]
    $totalMem = [int64]0
    foreach ($m in $mem) {
        $cap = 0
        if ($m.Capacity) { $cap = [int64]$m.Capacity; $totalMem += $cap }
        $speed = Get-XsnapshotFirst @($(if ($m.ConfiguredClockSpeed) { [string]$m.ConfiguredClockSpeed }), $(if ($m.Speed) { [string]$m.Speed })) 'unknown'
        $part = Get-XsnapshotFirst @($(if ($m.PartNumber) { $m.PartNumber.Trim() })) 'unknown-part'
        $bank = Get-XsnapshotFirst @($m.BankLabel, $m.DeviceLocator) 'unknown-slot'
        $modules.Add(("{0} {1} {2} MT/s {3}" -f (Format-XsnapshotBytes $cap), $part, $speed, $bank)) | Out-Null
    }
    if ($totalMem -eq 0 -and $cs0 -and $cs0.TotalPhysicalMemory) { $totalMem = [int64]$cs0.TotalPhysicalMemory }
    $avail = [int64]0
    try {
        $os = @(Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop)
        if ($os.Count -gt 0 -and $os[0].FreePhysicalMemory) { $avail = [int64]$os[0].FreePhysicalMemory * 1024 }
    } catch {}

    $gpuName = 'unknown'
    $gpuDriver = 'unknown'
    $gpuVram = 'unknown'
    $gpuLines = New-Object System.Collections.Generic.List[string]
    foreach ($g in $gpu) {
        $name = Get-XsnapshotFirst @($g.Name)
        if ($gpuName -eq 'unknown') { $gpuName = $name }
        $drv = Get-XsnapshotFirst @($g.DriverVersion)
        if ($gpuDriver -eq 'unknown') { $gpuDriver = $drv }
        $gpuLines.Add(("$name driver=$drv")) | Out-Null
    }
    $smi = Get-XsnapshotNativeOutput -FileName 'nvidia-smi' -ArgumentList @('--query-gpu=name,memory.total,driver_version','--format=csv,noheader') -Name 'nvidia-smi --query-gpu' -TimeoutSec 15
    if ($smi) {
        $first = ($smi -split "`n")[0]
        $parts = @($first -split ',')
        if ($parts.Count -ge 3) {
            $gpuName = $parts[0].Trim()
            $gpuVram = $parts[1].Trim()
            $gpuDriver = $parts[2].Trim()
        }
        $gpuLines.Add($smi) | Out-Null
    }

    $boardModel = Get-XsnapshotFirst @($(if ($board0) { $board0.Product }), $(if ($cs0) { $cs0.Model }))
    $boardVendor = Get-XsnapshotFirst @($(if ($board0) { $board0.Manufacturer }), $(if ($cs0) { $cs0.Manufacturer }))
    $boardVer = Get-XsnapshotFirst @($(if ($board0) { $board0.Version }))
    $biosVer = Get-XsnapshotFirst @($(if ($bios0) { $bios0.SMBIOSBIOSVersion }), $(if ($bios0) { $bios0.Version }))
    $biosDate = Get-XsnapshotFirst @($(if ($bios0) { $bios0.ReleaseDate }))
    if ($biosDate -match '^(\d{8})') { $biosDate = $Matches[1] }
    $systemProduct = Get-XsnapshotFirst @($(if ($cs0) { $cs0.Model }))

    $hw = [ordered]@{
        cpu = [ordered]@{
            name = $cpuName
            cores = [int]$cores
            threads = [int]$threads
            max_clock = $cpuMax
        }
        memory = [ordered]@{
            total_bytes = [int64]$totalMem
            used_bytes = [int64]([Math]::Max([int64]0, [int64]($totalMem - $avail)))
            available_bytes = [int64]$avail
            total_human = Format-XsnapshotBytes $totalMem
            modules = @($modules)
        }
        gpu = [ordered]@{
            name = $gpuName
            vram = $gpuVram
            driver = $gpuDriver
            power_limit = 'unknown'
        }
        board = [ordered]@{
            model = "$boardVendor $boardModel".Trim()
            version = $boardVer
            bios = $biosVer
            bios_date = $biosDate
            system_product = $systemProduct
        }
        devices = 'not collected on Windows (no lspci equivalent in the allow-list)'
        usb = 'not collected on Windows (device instance IDs omitted)'
    }
    $text = @(
        "cpu=$cpuName cores=$cores threads=$threads max=$cpuMax",
        "memory=$(Format-XsnapshotBytes $totalMem)",
        ($modules -join "`n"),
        "gpu=$gpuName vram=$gpuVram driver=$gpuDriver",
        "board=$boardVendor $boardModel version=$boardVer",
        "bios=$biosVer date=$biosDate"
    ) -join "`n"
    return @{ Hardware = $hw; Text = $text }
}

function Get-XsnapshotStorageInventory {
    $disks = @(Invoke-XsnapshotCim -ClassName Win32_DiskDrive -Name 'Win32_DiskDrive')
    $vols = @()
    try { $vols = @(Get-Volume -ErrorAction Stop) } catch { $script:Notes.Add("Get-Volume failed: $_") | Out-Null }
    $script:Commands.Add([ordered]@{ command = 'Get-Volume'; started_at = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss'); returncode = 0; stdout_bytes = $vols.Count; stderr_bytes = 0 }) | Out-Null
    $diskLines = New-Object System.Collections.Generic.List[string]
    $diskObjs = New-Object System.Collections.Generic.List[object]
    foreach ($d in $disks) {
        $model = Get-XsnapshotFirst @($d.Model)
        $bus = Get-XsnapshotFirst @($d.InterfaceType)
        $media = Get-XsnapshotFirst @($d.MediaType)
        $size = 0; if ($d.Size) { $size = [int64]$d.Size }
        $diskLines.Add(("{0} {1} {2} {3}" -f $model, (Format-XsnapshotBytes $size), $bus, $media)) | Out-Null
        $diskObjs.Add([ordered]@{
            model = $model
            size_bytes = $size
            size_human = Format-XsnapshotBytes $size
            bus = $bus
            media = $media
            serial = '<redacted>'
        }) | Out-Null
    }
    $volLines = New-Object System.Collections.Generic.List[string]
    $volObjs = New-Object System.Collections.Generic.List[object]
    foreach ($v in $vols) {
        $letter = ''
        $driveLetter = Get-XsnapshotProperty $v 'DriveLetter'
        if ($driveLetter) { $letter = [string]$driveLetter }
        $fs = Get-XsnapshotFirst @((Get-XsnapshotProperty $v 'FileSystemType'), (Get-XsnapshotProperty $v 'FileSystem'))
        $type = Get-XsnapshotFirst @((Get-XsnapshotProperty $v 'DriveType'))
        $size = 0; $free = 0
        $sizeVal = Get-XsnapshotProperty $v 'Size'
        $freeVal = Get-XsnapshotProperty $v 'SizeRemaining'
        if ($sizeVal) { $size = [int64]$sizeVal }
        if ($freeVal) { $free = [int64]$freeVal }
        $label = Get-XsnapshotFirst @((Get-XsnapshotProperty $v 'FileSystemLabel')) ''
        $volLines.Add(("{0}: {1} {2} {3} free={4}" -f $letter, $fs, $type, (Format-XsnapshotBytes $size), (Format-XsnapshotBytes $free))) | Out-Null
        $volObjs.Add([ordered]@{
            drive_letter = $letter
            file_system = $fs
            drive_type = [string]$type
            size_bytes = $size
            size_human = Format-XsnapshotBytes $size
            free_bytes = $free
            label = $label
            unique_id = '<redacted>'
        }) | Out-Null
    }
    $storage = [ordered]@{
        disks = @($diskObjs.ToArray())
        volumes = @($volObjs.ToArray())
        df = ($volLines -join "`n")
        swap = 'not applicable (Windows page file; path and identifiers omitted)'
        encryption = 'BitLocker identifiers omitted; presence not attested'
    }
    $storage['lsblk_json'] = $null
    $storage['zram'] = $null
    $storage['snapper'] = $null
    $text = (("DISKS`n" + ($diskLines -join "`n") + "`n`nVOLUMES`n" + ($volLines -join "`n")))
    return @{ Storage = $storage; Text = $text }
}

function Get-XsnapshotNetworkInventory {
    $adapters = @()
    try { $adapters = @(Get-NetAdapter -ErrorAction Stop) } catch { $script:Notes.Add("Get-NetAdapter failed: $_") | Out-Null }
    $script:Commands.Add([ordered]@{ command = 'Get-NetAdapter'; started_at = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss'); returncode = 0; stdout_bytes = $adapters.Count; stderr_bytes = 0 }) | Out-Null
    $lines = New-Object System.Collections.Generic.List[string]
    $objs = New-Object System.Collections.Generic.List[object]
    foreach ($a in $adapters) {
        $name = Get-XsnapshotFirst @($a.Name)
        $status = Get-XsnapshotFirst @($a.Status)
        $ifType = Get-XsnapshotFirst @($a.MediaType, $a.InterfaceDescription)
        $speed = Get-XsnapshotFirst @($(if ($a.LinkSpeed) { [string]$a.LinkSpeed }))
        $lines.Add(("{0} status={1} type={2} speed={3} mac=<mac>" -f $name, $status, $ifType, $speed)) | Out-Null
        $objs.Add([ordered]@{
            name = $name
            status = $status
            type = $ifType
            speed = $speed
            mac = '<mac>'
        }) | Out-Null
    }
    $fw = 'unknown'
    try {
        $profiles = @(Get-NetFirewallProfile -ErrorAction Stop)
        $fw = ($profiles | ForEach-Object { '{0} enabled={1}' -f $_.Name, $_.Enabled }) -join '; '
    } catch { $fw = "unavailable: $_" }
    $network = [ordered]@{
        links = @($objs.ToArray())
        routes = 'route destinations and gateways omitted (identifiers)'
        listeners = 'listening addresses omitted (identifiers)'
        dns = 'DNS server addresses omitted (identifiers)'
        firewall = $fw
    }
    $network['rfkill'] = $null
    return @{ Network = $network; Text = (($lines -join "`n") + "`n`nfirewall: $fw") }
}

function Get-XsnapshotBootInventory {
    $secure = 'unknown'
    try {
        $sb = Confirm-SecureBootUEFI -ErrorAction Stop
        if ($sb) { $secure = 'enabled' } else { $secure = 'disabled' }
    } catch { $secure = "unavailable: $_" }
    $firmware = 'unknown'
    try {
        $val = Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\SecureBoot\State' -ErrorAction SilentlyContinue
        $cs = Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction SilentlyContinue
        # Firmware type via env
        $pe = $env:firmware_type
        if ($pe) { $firmware = $pe }
        else {
            $info = Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction SilentlyContinue
            $firmware = 'UEFI or BIOS (exact type may be unavailable without firmware identifiers)'
        }
    } catch {}
    try {
        $fwType = (Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control' -Name 'PEFirmwareType' -ErrorAction SilentlyContinue).PEFirmwareType
        if ($fwType -eq 2) { $firmware = 'UEFI' }
        elseif ($fwType -eq 1) { $firmware = 'BIOS' }
    } catch {}
    $tpm = 'unknown'
    try {
        $t = Get-CimInstance -Namespace 'root/cimv2/Security/MicrosoftTpm' -ClassName Win32_Tpm -ErrorAction Stop
        if ($t) {
            $present = $t.IsEnabled_InitialValue
            $ver = Get-XsnapshotFirst @($t.SpecVersion)
            $tpm = "present enabled=$present spec=$ver (identifiers omitted)"
        } else { $tpm = 'not present' }
    } catch { $tpm = "unavailable: $_" }
    $boot = [ordered]@{
        bootctl = 'not applicable'
        efibootmgr = 'EFI boot entry identifiers omitted'
        secure_boot = $secure
        tpm = $tpm
        firmware = $firmware
    }
    $boot['cmdline'] = $null
    $text = "firmware=$firmware`nsecure_boot=$secure`ntpm=$tpm"
    return @{ Boot = $boot; Text = $text }
}

function Get-XsnapshotDesktopInventory {
    $session = Get-XsnapshotFirst @($env:SESSIONNAME) 'unknown'
    $theme = 'unknown'
    try {
        $personalize = Get-ItemProperty -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize' -ErrorAction Stop
        if ($null -ne $personalize.AppsUseLightTheme) {
            if ([int]$personalize.AppsUseLightTheme -eq 0) { $theme = 'dark' } else { $theme = 'light' }
        }
        if ($personalize.SystemUsesLightTheme -eq 0 -and $theme -eq 'light') { $theme = 'light-apps/dark-system' }
    } catch {}
    $locale = Get-XsnapshotFirst @([System.Globalization.CultureInfo]::CurrentCulture.Name)
    $uiLocale = Get-XsnapshotFirst @([System.Globalization.CultureInfo]::CurrentUICulture.Name)
    $tz = [TimeZoneInfo]::Local.Id
    $tzOffset = (Get-Date).ToString('zzz')
    $scale = 'unknown'
    try {
        $dpi = Get-ItemProperty -LiteralPath 'HKCU:\Control Panel\Desktop\WindowMetrics' -ErrorAction SilentlyContinue
        # AppliedDPI is more reliable when present
        $dpiKey = Get-ItemProperty -LiteralPath 'HKCU:\Control Panel\Desktop' -ErrorAction SilentlyContinue
        if ($dpiKey.LogPixels) { $scale = '{0} dpi' -f $dpiKey.LogPixels }
    } catch {}
    $monitors = New-Object System.Collections.Generic.List[string]
    try {
        $screens = [System.Windows.Forms.Screen]::AllScreens
        foreach ($s in @($screens)) {
            $bounds = $s.Bounds
            $monitors.Add(("{0} {1}x{2} primary={3}" -f $s.DeviceName, $bounds.Width, $bounds.Height, $s.Primary)) | Out-Null
        }
    } catch {
        try {
            Add-Type -AssemblyName System.Windows.Forms
            foreach ($s in [System.Windows.Forms.Screen]::AllScreens) {
                $bounds = $s.Bounds
                $monitors.Add(("{0} {1}x{2} primary={3}" -f $s.DeviceName, $bounds.Width, $bounds.Height, $s.Primary)) | Out-Null
            }
        } catch {
            $script:Notes.Add("monitor enumeration unavailable: $_") | Out-Null
        }
    }
    $desktop = [ordered]@{
        env = "SESSIONNAME=$session"
        session = $session
        monitors = @($monitors.ToArray())
        theme = $theme
        locale = "culture=$locale ui=$uiLocale"
        time = "timezone=$tz offset=$tzOffset"
        audio = 'Windows audio device names omitted'
    }
    $desktop['hyprland'] = $null
    $desktop['bindings'] = $null
    $desktop['waybar'] = $null
    $text = @(
        "session=$session",
        "theme=$theme",
        "locale=$locale ui=$uiLocale",
        "timezone=$tz offset=$tzOffset",
        "scale=$scale",
        "monitors:",
        ($monitors -join "`n")
    ) -join "`n"
    return @{ Desktop = $desktop; Text = $text }
}

function Get-XsnapshotServiceInventory {
    $svcs = @(Invoke-XsnapshotCim -ClassName Win32_Service -Name 'Win32_Service')
    $lines = New-Object System.Collections.Generic.List[string]
    $objs = New-Object System.Collections.Generic.List[object]
    foreach ($s in $svcs) {
        $startName = Get-XsnapshotFirst @($s.StartName) ''
        if ($startName) { $startName = (Invoke-XsnapshotRedactIdentity -Text $startName).Text }
        $line = '{0} state={1} start={2} account={3}' -f $s.Name, $s.State, $s.StartMode, $startName
        $lines.Add($line) | Out-Null
        $objs.Add([ordered]@{
            name = [string]$s.Name
            state = [string]$s.State
            start_mode = [string]$s.StartMode
            account = $startName
        }) | Out-Null
    }
    $serviceResult = New-Object System.Collections.Specialized.OrderedDictionary
    $serviceResult.Add('Services', $objs.ToArray()) | Out-Null
    $serviceResult.Add('Text', ($lines -join "`n")) | Out-Null
    $serviceResult.Add('Count', [int]$objs.Count) | Out-Null
    return $serviceResult
}

function Get-XsnapshotUninstallEntries {
    $paths = @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall',
        'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'
    )
    $rows = New-Object System.Collections.Generic.List[object]
    $seen = @{}
    foreach ($root in $paths) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        $keys = @()
        try { $keys = @(Get-ChildItem -LiteralPath $root -ErrorAction Stop) } catch { continue }
        foreach ($k in $keys) {
            try { $p = Get-ItemProperty -LiteralPath $k.PSPath -ErrorAction Stop } catch { continue }
            $name = Get-XsnapshotProperty $p 'DisplayName'
            if ([string]::IsNullOrWhiteSpace($name)) { continue }
            $ver = Get-XsnapshotFirst @((Get-XsnapshotProperty $p 'DisplayVersion')) ''
            $pub = Get-XsnapshotFirst @((Get-XsnapshotProperty $p 'Publisher')) ''
            $line = ($name.Trim() + ' ' + $ver + ' (' + $pub + ')').Trim()
            $line = (Invoke-XsnapshotRedactIdentity -Text $line).Text
            $key = $line.ToLowerInvariant()
            if ($seen.ContainsKey($key)) { continue }
            $seen[$key] = $true
            $rows.Add($line) | Out-Null
        }
    }
    return @($rows | Sort-Object)
}

function Get-XsnapshotWingetPackages {
    $out = Get-XsnapshotNativeOutput -FileName 'winget' -ArgumentList @('list','--disable-interactivity','--accept-source-agreements') -Name 'winget list' -TimeoutSec 60
    if ($null -eq $out) { return @() }
    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($line in ($out -split "`r?`n")) {
        $t = $line.TrimEnd()
        if ([string]::IsNullOrWhiteSpace($t)) { continue }
        if ($t -match '^[-\\]+$') { continue }
        if ($t -match '^\s*Name\s+Id\s+Version') { continue }
        if ($t -match '^The `msstore` source') { continue }
        if ($t -match '^\s*\d+\s+package') { continue }
        $t = (Invoke-XsnapshotRedactIdentity -Text $t).Text
        $t = (Invoke-XsnapshotRedact -Text $t).Text
        $lines.Add($t) | Out-Null
    }
    return [string[]]@($lines)
}

function Get-XsnapshotAppxPackages {
    $pkgs = @()
    try { $pkgs = @(Get-AppxPackage -ErrorAction Stop) } catch {
        $script:Notes.Add("Get-AppxPackage failed: $_") | Out-Null
        return @()
    }
    $script:Commands.Add([ordered]@{ command = 'Get-AppxPackage'; started_at = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss'); returncode = 0; stdout_bytes = $pkgs.Count; stderr_bytes = 0 }) | Out-Null
    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($p in ($pkgs | Sort-Object Name)) {
        $line = '{0} {1}' -f $p.Name, $p.Version
        $lines.Add($line) | Out-Null
    }
    return [string[]]@($lines)
}

function Get-XsnapshotLanguagePackages {
    $chunks = New-Object System.Collections.Generic.List[string]
    $npm = Get-XsnapshotNativeOutput -FileName 'npm' -ArgumentList @('ls','-g','--depth=0') -Name 'npm ls -g --depth=0' -TimeoutSec 45
    if ($npm) { $chunks.Add("## npm -g`n`n$((Invoke-XsnapshotRedact -Text $npm).Text)") | Out-Null }
    $pip = Get-XsnapshotNativeOutput -FileName 'python' -ArgumentList @('-m','pip','list') -Name 'python -m pip list' -TimeoutSec 45
    if (-not $pip) { $pip = Get-XsnapshotNativeOutput -FileName 'py' -ArgumentList @('-3','-m','pip','list') -Name 'py -3 -m pip list' -TimeoutSec 45 }
    if ($pip) { $chunks.Add("## pip`n`n$((Invoke-XsnapshotRedact -Text $pip).Text)") | Out-Null }
    $cargo = Get-XsnapshotNativeOutput -FileName 'cargo' -ArgumentList @('install','--list') -Name 'cargo install --list' -TimeoutSec 30
    if ($cargo) { $chunks.Add("## cargo`n`n$((Invoke-XsnapshotRedact -Text $cargo).Text)") | Out-Null }
    $choco = Get-XsnapshotNativeOutput -FileName 'choco' -ArgumentList @('list','-y') -Name 'choco list' -TimeoutSec 45
    if ($choco) { $chunks.Add("## chocolatey`n`n$((Invoke-XsnapshotRedact -Text $choco).Text)") | Out-Null }
    $scoop = Get-XsnapshotNativeOutput -FileName 'scoop' -ArgumentList @('list') -Name 'scoop list' -TimeoutSec 30
    if ($scoop) { $chunks.Add("## scoop`n`n$((Invoke-XsnapshotRedact -Text $scoop).Text)") | Out-Null }
    return ($chunks -join "`n`n")
}

function Get-XsnapshotDevTools {
    $tools = @(
        @{ n = 'git'; a = @('--version') },
        @{ n = 'gh'; a = @('--version') },
        @{ n = 'node'; a = @('--version') },
        @{ n = 'npm'; a = @('--version') },
        @{ n = 'python'; a = @('--version') },
        @{ n = 'py'; a = @('-3','--version') },
        @{ n = 'pwsh'; a = @('-NoProfile','-Command','$PSVersionTable.PSVersion.ToString()') },
        @{ n = 'powershell'; a = @('-NoProfile','-Command','$PSVersionTable.PSVersion.ToString()') },
        @{ n = 'cargo'; a = @('--version') },
        @{ n = 'rustc'; a = @('--version') },
        @{ n = 'go'; a = @('version') },
        @{ n = 'docker'; a = @('--version') },
        @{ n = 'code'; a = @('--version') },
        @{ n = 'cursor'; a = @('--version') },
        @{ n = 'winget'; a = @('--version') }
    )
    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($t in $tools) {
        $out = Get-XsnapshotNativeOutput -FileName $t.n -ArgumentList $t.a -Name ($t.n + ' ' + ($t.a -join ' ')) -TimeoutSec 15
        if ($null -eq $out) { $lines.Add("$($t.n)=not on PATH") | Out-Null }
        else {
            $first = (($out -split "`r?`n")[0]).Trim()
            $first = (Invoke-XsnapshotRedactIdentity -Text $first).Text
            $lines.Add("$($t.n)=$first") | Out-Null
        }
    }
    $psver = $PSVersionTable.PSVersion.ToString()
    $lines.Add("collector_powershell=$psver") | Out-Null
    return ($lines -join "`n")
}

function Get-XsnapshotAgentInventory {
    $homeDir = $script:HomePath
    function Count-Files([string]$Path, [string]$Filter) {
        if (-not (Test-Path -LiteralPath $Path)) { return 0 }
        if (Test-XsnapshotReparsePoint -Path $Path) { return 0 }
        try { return @(Get-ChildItem -LiteralPath $Path -Filter $Filter -File -ErrorAction Stop).Count } catch { return 0 }
    }
    $claudeSettings = Test-Path -LiteralPath (Join-Path $homeDir '.claude\settings.json')
    $cursorUser = Test-Path -LiteralPath (Join-Path $env:APPDATA 'Cursor\User\settings.json')
    $codeUser = Test-Path -LiteralPath (Join-Path $env:APPDATA 'Code\User\settings.json')
    $info = [ordered]@{
        claude_settings_present = [bool]$claudeSettings
        cursor_user_settings_present = [bool]$cursorUser
        vscode_user_settings_present = [bool]$codeUser
        omp_agents = [int](Count-Files (Join-Path $homeDir '.omp\agent\agents') '*.md')
        devin_agents = [int](Count-Files (Join-Path $homeDir '.config\devin\agents') '*.md')
        agents_skills = [int](Count-Files (Join-Path $homeDir '.agents\skills') 'SKILL.md')
    }
    $text = ($info.GetEnumerator() | ForEach-Object { '{0}={1}' -f $_.Key, $_.Value }) -join "`n"
    $text += "`nnote=agent conversation histories, credentials and local databases are not copied"
    return @{ Agents = $info; Text = $text }
}

function Get-XsnapshotAllowList {
    $homeDir = $script:HomePath
    $appData = $env:APPDATA
    $localApp = $env:LOCALAPPDATA
    $list = New-Object System.Collections.Generic.List[object]

    function Add-Allow([string]$Source, [string]$Rel) {
        if ([string]::IsNullOrWhiteSpace($Source)) { return }
        $list.Add(@{ Source = $Source; Rel = $Rel }) | Out-Null
    }

    $psRoots = @()
    if ($PROFILE) { $psRoots += $PROFILE }
    $docs = Join-Path $homeDir 'Documents'
    Add-Allow (Join-Path $docs 'WindowsPowerShell\Microsoft.PowerShell_profile.ps1') 'applied/WindowsPowerShell/Microsoft.PowerShell_profile.ps1'
    Add-Allow (Join-Path $docs 'WindowsPowerShell\profile.ps1') 'applied/WindowsPowerShell/profile.ps1'
    Add-Allow (Join-Path $docs 'PowerShell\Microsoft.PowerShell_profile.ps1') 'applied/PowerShell/Microsoft.PowerShell_profile.ps1'
    Add-Allow (Join-Path $docs 'PowerShell\profile.ps1') 'applied/PowerShell/profile.ps1'
    Add-Allow (Join-Path $homeDir '.gitconfig') 'applied/.gitconfig'
    Add-Allow (Join-Path $homeDir '.config\git\config') 'applied/config/git/config'
    Add-Allow (Join-Path $homeDir '.ssh\config') 'applied/.ssh/config'
    Add-Allow (Join-Path $homeDir '.vimrc') 'applied/.vimrc'
    Add-Allow (Join-Path $homeDir '.config\nvim\init.lua') 'applied/config/nvim/init.lua'
    Add-Allow (Join-Path $homeDir '.config\nvim\init.vim') 'applied/config/nvim/init.vim'
    Add-Allow (Join-Path $homeDir '.cargo\config.toml') 'applied/.cargo/config.toml'
    Add-Allow (Join-Path $homeDir '.condarc') 'applied/.condarc'
    Add-Allow (Join-Path $homeDir 'pip.conf') 'applied/pip.conf'
    Add-Allow (Join-Path $homeDir 'pip.ini') 'applied/pip.ini'
    Add-Allow (Join-Path $appData 'pip\pip.ini') 'applied/AppData/pip/pip.ini'
    Add-Allow (Join-Path $appData 'Code\User\settings.json') 'applied/AppData/Code/User/settings.json'
    Add-Allow (Join-Path $appData 'Code\User\keybindings.json') 'applied/AppData/Code/User/keybindings.json'
    Add-Allow (Join-Path $appData 'Code\User\argv.json') 'applied/AppData/Code/User/argv.json'
    Add-Allow (Join-Path $appData 'Cursor\User\settings.json') 'applied/AppData/Cursor/User/settings.json'
    Add-Allow (Join-Path $appData 'Cursor\User\keybindings.json') 'applied/AppData/Cursor/User/keybindings.json'
    Add-Allow (Join-Path $localApp 'Microsoft\Windows Terminal\settings.json') 'applied/WindowsTerminal/settings.json'
    Add-Allow (Join-Path $homeDir '.config\alacritty\alacritty.toml') 'applied/config/alacritty/alacritty.toml'
    Add-Allow (Join-Path $homeDir '.wezterm.lua') 'applied/.wezterm.lua'
    Add-Allow (Join-Path $localApp 'Microsoft\WinGet\Settings\settings.json') 'applied/WinGet/settings.json'
    Add-Allow 'C:\Windows\System32\drivers\etc\hosts' 'etc/hosts'

    # Windows Terminal packaged settings (first match only).
    $wtRoot = Join-Path $localApp 'Packages'
    if (Test-Path -LiteralPath $wtRoot) {
        try {
            $pkg = Get-ChildItem -LiteralPath $wtRoot -Directory -Filter 'Microsoft.WindowsTerminal*' -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($pkg) {
                Add-Allow (Join-Path $pkg.FullName 'LocalState\settings.json') 'applied/WindowsTerminal/packages-settings.json'
            }
        } catch {}
    }
    return [object[]]($list.ToArray())
}

function Write-XsnapshotReport {
    param($HostObj, $Hardware, $Packages, $Footprint)
    $areaRows = New-Object System.Collections.Generic.List[string]
    if ($Footprint) {
        foreach ($key in $Footprint.Keys) {
            $info = $Footprint[$key]
            $areaRows.Add(('| {0} | {1} | {2} |' -f $key, $info.files, $info.bytes_human)) | Out-Null
        }
    }
    if ($areaRows.Count -eq 0) { $areaRows.Add('| (none) | 0 | 0 B |') | Out-Null }
    $artifactRows = New-Object System.Collections.Generic.List[string]
    foreach ($a in ($script:Artifacts | Sort-Object { $_.path })) {
        $short = $a.sha256.Substring(0, 12) + [char]0x2026
        $artifactRows.Add(('| `{0}` | {1} | `{2}` |' -f $a.path, (Format-XsnapshotBytes $a.bytes), $short)) | Out-Null
    }
    $cpuName = 'unknown'
    $ram = 'unknown'
    $gpuName = 'unknown'
    if ($Hardware.cpu -and $Hardware.cpu.name) { $cpuName = [string]$Hardware.cpu.name }
    if ($Hardware.memory -and $Hardware.memory.total_human) { $ram = [string]$Hardware.memory.total_human }
    if ($Hardware.gpu -and $Hardware.gpu.name) { $gpuName = [string]$Hardware.gpu.name }
    $report = @"
# Snapshot report: $($script:SnapshotId)

> Captured **$($script:CapturedAt)** on ``$($HostObj.hostname)``.
>
> This report is the capture manifest. The human-readable inventory is the
> repository ``README.md``; the machine-readable form is ``data/snapshot.json``.
> ``ARTIFACTS.sha256`` seals every file in the snapshot except itself.

This collector is the Windows implementation of ``xsnapshot-pc``. It is
deliberately boring: PowerShell 5.1-compatible, allow-listed configuration
copy, redaction of secrets and unique identifiers, no upload, no package
installation, and no change to execution policy or privileges.

1. Runs read-only inventory commands (CIM, registry Uninstall keys, winget,
   Appx, service list, tool versions) and records them in ``commands``.
2. Copies only the allow-listed configuration files listed in
   ``docs/WINDOWS.md``. Browser profiles, credential stores, SSH private keys
   and agent conversation histories are never copied.
3. Redacts secret assignments, tokens, UUIDs, MAC and IP addresses, Windows
   SIDs, hardware serials, the local account name and the user profile path.

| Field | Value |
|---|---|
| Schema | ``$($script:Schema)`` |
| Collector | xsnapshot-pc $($script:CollectorVersion) |
| Host | $($HostObj.hostname) ($($HostObj.chassis)) |
| OS | $($HostObj.os) $($HostObj.os_version) |
| CPU | $cpuName |
| Memory | $ram |
| GPU | $gpuName |
| Uninstall entries (all) | $($Packages.all_count) |
| winget (explicit) | $($Packages.explicit_count) |
| Appx/MSIX (foreign) | $($Packages.foreign_count) |
| Config files captured | $($script:ConfigIndex.Count) |
| Redactions applied | $($script:RedactionTotal) |
| Notes | $($script:Notes.Count) |

## Configuration footprint

| Area | Files | Bytes |
|---|---|---|
$($areaRows -join "`n")

## Package inventory

- ``all``: Windows Uninstall registry entries (HKLM 64-bit, HKLM 32-bit, HKCU), as ``Name Version (Publisher)``.
- ``explicit``: ``winget list`` lines (Id, version and source when winget is present).
- ``foreign``: ``Get-AppxPackage`` Name and Version. This is not a claim that a package is untrusted.
- Extra inventories (npm -g, pip, cargo, chocolatey, scoop) are recorded under ``packages/language.txt`` when those tools are present.

## Coverage and limits

- **Captured:** host identity without unique IDs; CPU/RAM/GPU/board (serials omitted); fixed disks and volumes without GUIDs; adapter names and link state without MAC/IP; firewall profile enablement; firmware type, Secure Boot and TPM presence; desktop session, theme, locale, timezone and monitor size; services (name, state, start mode, account with the profile path redacted); package inventories above; allow-listed configuration bodies after redaction; developer tool versions; agent-definition counts only.
- **Not captured:** file contents outside the allow-list; browser profiles, cookies, history, local storage; password-manager vaults; API keys, OAuth tokens, session tokens; shell and agent conversation histories; SSH/GPG private keys; machine and boot IDs; volume GUIDs, MAC/IP addresses, hardware serials; caches, blobs, logs, sessions, backups; BitLocker protectors; listening sockets and routing tables.
- **Not a backup:** this is a descriptive inventory. It cannot restore credentials, encrypted volumes, browser sessions, or application state.
- **Privileges:** the collector does not require elevation and does not change the process or system execution policy beyond the caller's existing rights.

## Artifact index

| Path | Bytes | SHA-256 |
|---|---|---|
$($artifactRows -join "`n")

## Notes

$(if ($script:Notes.Count -gt 0) { ($script:Notes | ForEach-Object { '- ' + $_ }) -join "`n" } else { '- none' })
"@
    Write-XsnapshotText -Rel 'REPORT.md' -Text ((Invoke-XsnapshotRedactIdentity -Text $report).Text)
}

function Get-XsnapshotConfigFootprint {
    $areas = [ordered]@{}
    foreach ($entry in $script:ConfigIndex) {
        $rel = [string]$entry.path
        $area = ($rel -split '/')[0]
        if (-not $areas.Contains($area)) {
            $areas[$area] = [ordered]@{ files = 0; bytes = 0; bytes_human = '0 B' }
        }
        $areas[$area].files += 1
        $areas[$area].bytes += [int]$entry.bytes
        $areas[$area].bytes_human = Format-XsnapshotBytes ([int64]$areas[$area].bytes)
    }
    return $areas
}

function Write-XsnapshotManifest {
    $expected = New-Object 'System.Collections.Generic.HashSet[string]'
    foreach ($row in $script:Artifacts) {
        if (-not $expected.Add($row.path)) { throw "duplicate artifact path: $($row.path)" }
    }
    $found = New-Object 'System.Collections.Generic.HashSet[string]'
    $files = Get-ChildItem -LiteralPath $script:OutDir -Recurse -Force -File
    foreach ($f in $files) {
        $full = $f.FullName
        if (Test-XsnapshotReparsePoint -Path $full) { throw "capture contains a symlink or special file: $full" }
        $rel = $full.Substring($script:OutDir.Length).TrimStart('\', '/') -replace '\\', '/'
        [void]$found.Add($rel)
    }
    if ($found.Contains('ARTIFACTS.sha256')) { [void]$found.Remove('ARTIFACTS.sha256') }
    if ($expected.Count -ne $found.Count -or ($expected.SymmetricExceptWith -eq $null -and $false)) {
        # Compare sets manually.
    }
    $missing = @($expected | Where-Object { -not $found.Contains($_) })
    $extra = @($found | Where-Object { -not $expected.Contains($_) })
    if ($missing.Count -or $extra.Count) {
        throw ("capture contains unexpected or missing files; refusing to seal it. missing={0} extra={1}" -f ($missing -join ','), ($extra -join ','))
    }
    $lines = @($script:Artifacts | Sort-Object { $_.path } | ForEach-Object { '{0}  {1}' -f $_.sha256, $_.path })
    $body = [System.Text.Encoding]::UTF8.GetBytes((($lines -join "`n") + "`n"))
    Write-XsnapshotPrivateFile -Rel 'ARTIFACTS.sha256' -Body $body | Out-Null
}

function Invoke-XsnapshotCollect {
    param(
        [string]$Root,
        [string]$SnapshotId,
        [string]$Out,
        [switch]$Force
    )
    if (-not (Get-XsnapshotIsWindows)) {
        Write-Error 'collect is implemented for Windows. On Linux use bin/xsnapshot.'
        return 2
    }
    Initialize-XsnapshotIdentity
    $script:RedactionTotal = 0
    $script:Artifacts = [System.Collections.Generic.List[object]]::new()
    $script:ConfigIndex = [System.Collections.Generic.List[object]]::new()
    $script:Notes = [System.Collections.Generic.List[string]]::new()
    $script:Commands = [System.Collections.Generic.List[object]]::new()

    if ([string]::IsNullOrWhiteSpace($SnapshotId)) {
        $SnapshotId = (Get-Date).ToString('yyyy-MM-dd')
    }
    if ($SnapshotId -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$') {
        Write-Error 'snapshot id must be a single safe filename'
        return 2
    }
    $rootPath = [System.IO.Path]::GetFullPath($Root)
    if ($Out) { $outPath = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $Out)) }
    else { $outPath = Join-Path (Join-Path $rootPath 'snapshots') $SnapshotId }
    if (Test-XsnapshotReparsePoint -Path $outPath) {
        Write-Error 'refusing a symlink snapshot destination'
        return 2
    }
    $snapParent = Split-Path -Parent $outPath
    if ((Test-Path -LiteralPath $snapParent) -and (Test-XsnapshotReparsePoint -Path $snapParent)) {
        Write-Error 'refusing a symlink snapshot destination'
        return 2
    }
    if ((Test-Path -LiteralPath $outPath) -and -not $Force) {
        Write-Error "refusing to overwrite existing snapshot: $outPath`nuse --force to replace this capture deliberately"
        return 2
    }
    if ((Test-Path -LiteralPath $outPath) -and $Force) {
        if (Test-XsnapshotReparsePoint -Path $outPath) {
            Write-Error 'refusing to replace a reparse point'
            return 2
        }
        Remove-Item -LiteralPath $outPath -Recurse -Force
    }
    Write-Host "collecting snapshot $SnapshotId -> $outPath"
    New-XsnapshotPrivateDirectory -Path $outPath
    foreach ($sub in @('applied','etc','packages','system','data')) {
        New-XsnapshotPrivateDirectory -Path (Join-Path $outPath $sub)
    }
    $script:OutDir = $outPath
    $script:SnapshotId = $SnapshotId
    $script:CapturedAt = (Get-Date).ToString('yyyy-MM-ddTHH:mm:sszzz')

    $osInv = Get-XsnapshotOsInventory
    Write-XsnapshotText -Rel 'system/identity.txt' -Text (ConvertFrom-XsnapshotRedact -Text $osInv.Text)
    $hwInv = Get-XsnapshotHardwareInventory
    Write-XsnapshotText -Rel 'system/hardware.txt' -Text (ConvertFrom-XsnapshotRedact -Text $hwInv.Text)
    $stInv = Get-XsnapshotStorageInventory
    Write-XsnapshotText -Rel 'system/storage.txt' -Text (ConvertFrom-XsnapshotRedact -Text $stInv.Text)
    $netInv = Get-XsnapshotNetworkInventory
    Write-XsnapshotText -Rel 'system/network.txt' -Text (ConvertFrom-XsnapshotRedact -Text $netInv.Text)
    $bootInv = Get-XsnapshotBootInventory
    Write-XsnapshotText -Rel 'system/boot.txt' -Text (ConvertFrom-XsnapshotRedact -Text $bootInv.Text)
    $deskInv = Get-XsnapshotDesktopInventory
    Write-XsnapshotText -Rel 'system/desktop.txt' -Text (ConvertFrom-XsnapshotRedact -Text $deskInv.Text)
    $svcInv = Get-XsnapshotServiceInventory
    Write-XsnapshotText -Rel 'system/services.txt' -Text (ConvertFrom-XsnapshotRedact -Text $svcInv.Text)
    $tools = Get-XsnapshotDevTools
    Write-XsnapshotText -Rel 'system/devtools.txt' -Text (ConvertFrom-XsnapshotRedact -Text $tools)
    $agentInv = Get-XsnapshotAgentInventory
    Write-XsnapshotText -Rel 'system/agents.txt' -Text (ConvertFrom-XsnapshotRedact -Text $agentInv.Text)

    $all = @(Get-XsnapshotUninstallEntries)
    $explicit = @(Get-XsnapshotWingetPackages)
    $foreign = @(Get-XsnapshotAppxPackages)
    Write-XsnapshotText -Rel 'packages/uninstall.txt' -Text ($all -join "`n")
    Write-XsnapshotText -Rel 'packages/winget.txt' -Text ($explicit -join "`n")
    Write-XsnapshotText -Rel 'packages/appx.txt' -Text ($foreign -join "`n")
    $lang = Get-XsnapshotLanguagePackages
    if ($lang) { Write-XsnapshotText -Rel 'packages/language.txt' -Text $lang }

    foreach ($item in (Get-XsnapshotAllowList)) {
        [void](Copy-XsnapshotAllowlistedFile -Source $item.Source -Rel $item.Rel)
    }

    $packages = [ordered]@{
        all_count = [int]$all.Count
        explicit_count = [int]$explicit.Count
        foreign_count = [int]$foreign.Count
        all = @($all)
        explicit = @($explicit)
        foreign = @($foreign)
        sources = [ordered]@{
            all = 'registry Uninstall keys (HKLM 64-bit, HKLM Wow6432Node, HKCU)'
            explicit = 'winget list'
            foreign = 'Get-AppxPackage'
        }
    }
    $footprint = Get-XsnapshotConfigFootprint
    $privacy = [ordered]@{
        policy = 'allow-list plus redaction; secrets and unique identifiers excluded'
        excluded = @(
            'SSH/GPG private keys',
            'password-manager vaults',
            'browser profiles, cookies, history, local storage',
            'API keys, OAuth tokens, session tokens',
            'shell and agent conversation histories',
            'machine and boot IDs',
            'partition UUIDs, MAC/IP addresses, hardware serials',
            'local account names and home paths',
            'caches, blobs, logs, sessions, backups'
        )
        redactions_applied = [int]$script:RedactionTotal
        config_files_captured = [int]$script:ConfigIndex.Count
        artifact_seal = 'ARTIFACTS.sha256'
        local_output = 'owner-only capture directories and files; not encryption or a privacy guarantee'
    }
    $script:Data = [ordered]@{
        schema = $script:Schema
        snapshot_id = $script:SnapshotId
        captured_at = $script:CapturedAt
        collector = [ordered]@{
            name = 'xsnapshot-pc'
            version = $script:CollectorVersion
            powershell = $PSVersionTable.PSVersion.ToString()
            platform = 'windows'
        }
        host = $osInv.Host
        os = $osInv.Os
        hardware = $hwInv.Hardware
        storage = $stInv.Storage
        network = $netInv.Network
        boot = $bootInv.Boot
        desktop = $deskInv.Desktop
        services = @{ count = [int]$svcInv.Count }
        packages = $packages
        agents = $agentInv.Agents
        config_index = @($script:ConfigIndex)
        config_footprint = $footprint
        privacy = $privacy
        commands = @($script:Commands)
        notes = @($script:Notes)
    }
    $preview = ConvertTo-XsnapshotJson -Value $script:Data
    $idPreview = Invoke-XsnapshotRedactIdentity -Text $preview
    $script:RedactionTotal += [int]$idPreview.Count
    $script:Data.privacy.redactions_applied = [int]$script:RedactionTotal
    Write-XsnapshotReport -HostObj $osInv.Host -Hardware $hwInv.Hardware -Packages $packages -Footprint $footprint
    $script:Data.artifacts = @($script:Artifacts | Sort-Object { $_.path })
    $jsonText = ConvertTo-XsnapshotJson -Value $script:Data
    $jsonText = (Invoke-XsnapshotRedactIdentity -Text $jsonText).Text
    Write-XsnapshotText -Rel 'data/snapshot.json' -Text $jsonText
    Write-XsnapshotManifest
    Write-Host ("done: {0} artifacts, {1} redactions" -f $script:Artifacts.Count, $script:RedactionTotal)
    Write-Host "report: $(Join-Path $outPath 'REPORT.md')"
    Write-Host "json:   $(Join-Path $outPath 'data\snapshot.json')"
    Write-Host 'Nothing was uploaded.'
    return 0
}

function Invoke-XsnapshotValidate {
    param([string]$SnapshotPath)
    $snap = [System.IO.Path]::GetFullPath($SnapshotPath)
    if (-not (Test-Path -LiteralPath $snap)) { throw "snapshot not found: $snap" }
    $onDisk = New-Object 'System.Collections.Generic.HashSet[string]'
    $totalBytes = [int64]0
    $count = 0
    foreach ($f in Get-ChildItem -LiteralPath $snap -Recurse -Force) {
        $count++
        $relItem = $f.FullName.Substring($snap.Length).TrimStart('\', '/') -replace '\\', '/'
        if ($count -gt 8192 -or (($relItem -split '/').Count -gt 32)) { throw 'snapshot traversal limit exceeded' }
        if (Test-XsnapshotReparsePoint -Path $f.FullName) { throw 'snapshot contains a symlink or special file' }
        if (-not $f.PSIsContainer) {
            [void]$onDisk.Add($relItem)
            $totalBytes += $f.Length
            if ($onDisk.Count -gt 4096 -or $totalBytes -gt 64MB) { throw 'snapshot exceeds 4096 files or 64 MiB' }
        }
    }
    foreach ($need in @('data/snapshot.json','REPORT.md','ARTIFACTS.sha256')) {
        if (-not $onDisk.Contains($need)) { throw 'snapshot JSON, report and artifact seal are required' }
    }
    $dataPath = Join-Path $snap 'data\snapshot.json'
    $sealPath = Join-Path $snap 'ARTIFACTS.sha256'
    if ((Get-Item -LiteralPath $dataPath).Length -gt 8MB -or (Get-Item -LiteralPath $sealPath).Length -gt 1MB) {
        throw 'snapshot JSON or seal exceeds its size limit'
    }
    $raw = [System.IO.File]::ReadAllText($dataPath, [System.Text.Encoding]::UTF8)
    if ($raw.Length -gt 0 -and [int][char]$raw[0] -eq 0xFEFF) { throw 'snapshot JSON must not have a BOM' }
    $data = $raw | ConvertFrom-Json
    foreach ($key in @('schema','snapshot_id','captured_at','host','os','hardware','storage','desktop','packages','config_index','artifacts','privacy')) {
        if (-not ($data.PSObject.Properties.Name -contains $key)) { throw "snapshot is not an object with the required sections (missing $key)" }
    }
    if ($data.schema -ne $script:Schema) { throw 'unexpected snapshot schema' }
    if ($data.snapshot_id -ne (Split-Path -Leaf $snap)) { throw 'snapshot id does not match the capture directory' }
    [void][datetimeoffset]::Parse($data.captured_at)
    $seal = @{}
    foreach ($line in [System.IO.File]::ReadAllLines($sealPath, [System.Text.Encoding]::UTF8)) {
        if ($line -notmatch '^([0-9a-f]{64})  (.+)$') { throw 'malformed artifact seal line' }
        $digest = $Matches[1]; $rel = $Matches[2]
        if ($seal.ContainsKey($rel)) { throw 'duplicate artifact seal entry' }
        $seal[$rel] = $digest
    }
    $onDiskMinusSeal = New-Object 'System.Collections.Generic.HashSet[string]'
    foreach ($item in $onDisk) { [void]$onDiskMinusSeal.Add($item) }
    [void]$onDiskMinusSeal.Remove('ARTIFACTS.sha256')
    if ($seal.Count -ne $onDiskMinusSeal.Count) { throw 'artifact seal does not exactly cover the capture' }
    foreach ($rel in $seal.Keys) {
        if (-not $onDiskMinusSeal.Contains($rel)) { throw 'artifact seal does not exactly cover the capture' }
        $path = Join-Path $snap ($rel -replace '/', '\')
        $bytes = [System.IO.File]::ReadAllBytes($path)
        $digest = Get-XsnapshotSha256 -Body $bytes
        if ($digest -ne $seal[$rel]) { throw "artifact seal hash mismatch: $rel" }
    }
    $artifacts = @($data.artifacts)
    if ($artifacts.Count -lt 1) { throw 'artifact index must be a nonempty list' }
    $indexed = @{}
    foreach ($item in $artifacts) {
        $rel = [string]$item.path
        if ($indexed.ContainsKey($rel)) { throw 'duplicate artifact index entry' }
        $indexed[$rel] = $item
    }
    $indexExpected = New-Object 'System.Collections.Generic.HashSet[string]'
    foreach ($item in $onDisk) { [void]$indexExpected.Add($item) }
    [void]$indexExpected.Remove('data/snapshot.json')
    [void]$indexExpected.Remove('ARTIFACTS.sha256')
    if ($indexed.Count -ne $indexExpected.Count) { throw 'artifact index does not exactly cover the capture' }
    foreach ($rel in $indexed.Keys) {
        if (-not $indexExpected.Contains($rel)) { throw 'artifact index does not exactly cover the capture' }
        $path = Join-Path $snap ($rel -replace '/', '\')
        $size = [int64]((Get-Item -LiteralPath $path).Length)
        if ([int]$indexed[$rel].bytes -ne $size) { throw "artifact byte size mismatch: $rel" }
        if ([string]$indexed[$rel].sha256 -ne $seal[$rel]) { throw "artifact hash mismatch: $rel" }
    }
    $configs = @($data.config_index)
    $seen = @{}
    foreach ($entry in $configs) {
        $rel = [string]$entry.path
        if ($seen.ContainsKey($rel) -or -not $indexed.ContainsKey($rel)) { throw 'duplicate or unindexed config entry' }
        $seen[$rel] = $true
        if ([int]$entry.bytes -ne [int]$indexed[$rel].bytes) { throw 'config entry does not match artifact' }
        if ([string]$entry.snapshot_sha256 -ne $seal[$rel]) { throw 'config entry does not match artifact' }
        if ([int]$entry.redactions -lt 0) { throw 'invalid config redaction count' }
        if (-not $entry.source) { throw 'config entry missing source' }
    }
    if ([int]$data.privacy.config_files_captured -ne $configs.Count) { throw 'privacy count does not match config index' }
    foreach ($name in @('all','explicit','foreign')) {
        $values = @($data.packages.$name)
        $countName = $name + '_count'
        $count = [int]$data.packages.$countName
        if ($count -ne $values.Count) { throw 'package inventory count or type mismatch' }
        foreach ($item in $values) { if ($item -isnot [string]) { throw 'package inventory count or type mismatch' } }
    }
    $sealDigest = Get-XsnapshotSha256 -Body ([System.IO.File]::ReadAllBytes($sealPath))
    Write-Host ("valid: {0} ({1} artifacts, seal {2}…)" -f $snap, $indexed.Count, $sealDigest.Substring(0,12))
    return 0
}

function Invoke-XsnapshotPreflight {
    param([switch]$Json)
    $isWin = Get-XsnapshotIsWindows
    $psOk = $PSVersionTable.PSVersion.Major -ge 5
    $tools = [ordered]@{}
    foreach ($name in @('git','winget','pwsh','python','py','npm','cargo','docker')) {
        $tools[$name] = [bool](Get-Command $name -ErrorAction SilentlyContinue)
    }
    $report = [ordered]@{
        windows = $isWin
        powershell_5_1_or_newer = $psOk
        powershell_version = $PSVersionTable.PSVersion.ToString()
        core_prerequisites_met = [bool]($isWin -and $psOk)
        tools_on_path = $tools
        limits = 'No workstation inventory, configuration bodies, daemon queries, uploads, installs or permission changes. Presence is not trust, compatibility, privacy or release verification.'
        notes = @()
    }
    if (-not $isWin) { $report.notes += 'This collector captures Windows only. On Linux use bin/xsnapshot.' }
    if (-not $tools.winget) { $report.notes += 'winget is absent from the system search path. The explicit package list will be empty; Uninstall-registry and Appx inventories are still collected.' }
    if ($Json) {
        Write-Output (ConvertTo-XsnapshotJson -Value $report)
        if ($report.core_prerequisites_met) { return 0 } else { return 2 }
    }
    if ($report.core_prerequisites_met) { Write-Host 'xsnapshot preflight: core prerequisites available' }
    else { Write-Host 'xsnapshot preflight: blocked prerequisites' }
    Write-Host ("  {0}: windows" -f $(if ($isWin) { 'ok' } else { 'missing/unsupported' }))
    Write-Host ("  {0}: powershell_5_1_or_newer ({1})" -f $(if ($psOk) { 'ok' } else { 'missing/unsupported' }), $report.powershell_version)
    $absent = @($tools.GetEnumerator() | Where-Object { -not $_.Value } | ForEach-Object { $_.Key })
    Write-Host ('  optional tools absent from system path: ' + $(if ($absent) { $absent -join ', ' } else { 'none' }))
    foreach ($n in $report.notes) { Write-Host "  note: $n" }
    Write-Host $report.limits
    if ($report.core_prerequisites_met) { return 0 } else { return 2 }
}

function Invoke-XsnapshotList {
    param([string]$Root)
    $base = Join-Path $Root 'snapshots'
    if (-not (Test-Path -LiteralPath $base)) { return 0 }
    $dirs = Get-ChildItem -LiteralPath $base -Directory | Sort-Object Name -Descending
    foreach ($d in $dirs) {
        $json = Join-Path $d.FullName 'data\snapshot.json'
        $captured = ''
        if (Test-Path -LiteralPath $json) {
            try { $captured = (Get-Content -LiteralPath $json -Raw | ConvertFrom-Json).captured_at } catch { $captured = '' }
        }
        Write-Host ("{0}`t{1}" -f $d.Name, $captured)
    }
    return 0
}

function Invoke-XsnapshotMain {
    param([string[]]$Argv)
    if (-not $Argv) { $Argv = @() }
    $root = $null
    $command = $null
    $snapshot = $null
    $out = $null
    $force = $false
    $json = $false
    $positional = New-Object System.Collections.Generic.List[string]
    for ($i = 0; $i -lt $Argv.Count; $i++) {
        $a = $Argv[$i]
        switch -Regex ($a) {
            '^(--root|-Root)$' { $i++; $root = $Argv[$i] }
            '^--root=' { $root = $a.Substring(7) }
            '^(--snapshot|-Snapshot)$' { $i++; $snapshot = $Argv[$i] }
            '^--snapshot=' { $snapshot = $a.Substring(11) }
            '^(--out|-Out)$' { $i++; $out = $Argv[$i] }
            '^--out=' { $out = $a.Substring(6) }
            '^(--force|-Force)$' { $force = $true }
            '^(--json|-Json)$' { $json = $true }
            '^(--help|-h|-Help)$' {
                Write-Host @'
xsnapshot — Windows collector (schema xsnapshot/v1)

Usage:
  xsnapshot.ps1 [--root <dir>] preflight [--json]
  xsnapshot.ps1 [--root <dir>] collect [--snapshot <id>] [--out <dir>] [--force]
  xsnapshot.ps1 [--root <dir>] validate [<snapshot-dir>]
  xsnapshot.ps1 [--root <dir>] list

Nothing is uploaded. Review REPORT.md before publishing.
'@
                return 0
            }
            default { $positional.Add($a) | Out-Null }
        }
    }
    if (-not $command -and $positional.Count -gt 0) { $command = $positional[0] }
    if (-not $root) {
        if ($PSScriptRoot) { $root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path }
        else { $root = (Get-Location).Path }
    }
    if (-not $command) { $command = 'collect' }
    switch ($command) {
        'preflight' { return Invoke-XsnapshotPreflight -Json:$json }
        'collect' { return Invoke-XsnapshotCollect -Root $root -SnapshotId $snapshot -Out $out -Force:$force }
        'validate' {
            $target = $null
            if ($positional.Count -gt 1) { $target = $positional[1] }
            if (-not $target) {
                $base = Join-Path $root 'snapshots'
                $newest = Get-ChildItem -LiteralPath $base -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending | Select-Object -First 1
                if (-not $newest) { Write-Error 'no snapshots found'; return 2 }
                $target = $newest.FullName
            }
            return Invoke-XsnapshotValidate -SnapshotPath $target
        }
        'list' { return Invoke-XsnapshotList -Root $root }
        default { Write-Error "unknown command: $command"; return 2 }
    }
}

param(
    [switch]$Force,
    [switch]$Check,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
if ($PSVersionTable.PSVersion.Major -lt 7) {
    throw "Agent Orchestrator requires PowerShell 7 or newer. Run this installer with pwsh, not Windows PowerShell 5.1."
}
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$TargetHome = if ($env:AGENT_ORCHESTRATOR_HOME) { $env:AGENT_ORCHESTRATOR_HOME } else { $HOME }
$SkillDest = Join-Path $TargetHome ".agents\skills\agent-orchestrator"
$AgentDest = Join-Path $TargetHome ".codex\agents"
$StateRoot = Join-Path $TargetHome ".agent-orchestrator"
$InstallManifestName = ".agent-orchestrator-install.tsv"
$InstallManifest = Join-Path $SkillDest $InstallManifestName

$ManifestText = [IO.File]::ReadAllText((Join-Path $Root "manifest.toml"))
$VersionMatch = [regex]::Match($ManifestText, '(?m)^version = "([^"]+)"')
if (-not $VersionMatch.Success) { throw "Unable to read version from manifest.toml" }
$Version = $VersionMatch.Groups[1].Value

$CompatibilityMatch = [regex]::Match($ManifestText, '(?ms)^\[compatibility\]\s*(.*?)(?=^\[|\z)')
if (-not $CompatibilityMatch.Success) { throw "manifest.toml is missing [compatibility]." }
$LegacyFingerprintMatch = [regex]::Match($CompatibilityMatch.Groups[1].Value, '(?ms)legacy_orchestrator_sha256\s*=\s*\[(.*?)\]')
if (-not $LegacyFingerprintMatch.Success) { throw "manifest.toml compatibility is missing legacy_orchestrator_sha256." }
$LegacyOrchestratorHashes = @(
    [regex]::Matches($LegacyFingerprintMatch.Groups[1].Value, '(?i)[0-9a-f]{64}') |
        ForEach-Object { $_.Value.ToLowerInvariant() }
)
if ($LegacyOrchestratorHashes.Count -eq 0) { throw "manifest.toml contains no legacy orchestrator compatibility fingerprints." }
$LegacyOrchestratorPath = Join-Path $AgentDest "orchestrator.toml"

$SkillRuntimeFiles = @(
    "SKILL.md",
    "agents/openai.yaml",
    "references/orchestration.md",
    "references/agent-contract.md",
    "references/models.md",
    "references/codex.md"
)
$AgentProfileFiles = @(
    "backend-worker.toml",
    "docs-worker.toml",
    "explorer-worker.toml",
    "frontend-worker.toml",
    "generic-worker.toml",
    "review-worker.toml",
    "test-worker.toml"
)
$ExpectedSkillPaths = @($SkillRuntimeFiles | ForEach-Object { $_.Replace('\', '/') })

function Get-Sha256([string]$Path) {
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Get-SafeInstallerSourceItem([string]$Path, [string]$Label) {
    $RootFull = [IO.Path]::GetFullPath($Root)
    $Cursor = [IO.Path]::GetFullPath($Path)
    $Comparer = if ([OperatingSystem]::IsWindows()) { [StringComparer]::OrdinalIgnoreCase } else { [StringComparer]::Ordinal }
    $FinalItem = $null
    while ($true) {
        $Item = Get-Item -Force -LiteralPath $Cursor -ErrorAction SilentlyContinue
        if ($null -eq $Item) { throw "Missing or unsafe $Label source: $Path" }
        if (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Missing or unsafe $Label source: $Path (reparse/symlink component: $Cursor)"
        }
        if ($null -eq $FinalItem) { $FinalItem = $Item }
        if ($Comparer.Equals($Cursor, $RootFull)) { break }
        $Parent = [IO.Path]::GetDirectoryName($Cursor)
        if ([string]::IsNullOrEmpty($Parent) -or $Comparer.Equals($Parent, $Cursor)) {
            throw "Missing or unsafe $Label source: $Path (path escapes source root)"
        }
        $Cursor = $Parent
    }
    if ($FinalItem.PSIsContainer) { throw "Missing or unsafe $Label source: $Path" }
    return $FinalItem
}

function Assert-InstallerSource {
    $Required = @("manifest.toml") + $SkillRuntimeFiles
    foreach ($Relative in $Required) {
        $Path = Join-Path $Root $Relative
        [void](Get-SafeInstallerSourceItem $Path "installer")
    }
    $Sources = New-Object System.Collections.Generic.List[object]
    foreach ($Name in $AgentProfileFiles) {
        $Path = Join-Path $Root "templates\codex-agents\$Name"
        $Sources.Add((Get-SafeInstallerSourceItem $Path "canonical Agent"))
    }
    return $Sources.ToArray()
}

$ExpectedAgentNames = @($AgentProfileFiles)
$AgentSources = if ($Uninstall) { @() } else { @(Assert-InstallerSource) }

function Assert-SafeRelativeManagedPath([string]$Value, [string]$Label) {
    if ([string]::IsNullOrWhiteSpace($Value) -or [IO.Path]::IsPathRooted($Value) -or $Value.Contains('\') -or $Value.Contains(':')) {
        throw "Unsafe $Label path in install manifest: $Value"
    }
    $Parts = $Value -split '/'
    if ($Parts.Count -eq 0 -or @($Parts | Where-Object { [string]::IsNullOrEmpty($_) -or $_ -eq '.' -or $_ -eq '..' }).Count -gt 0) {
        throw "Unsafe $Label path in install manifest: $Value"
    }
}

function Assert-ManagedHash([string]$Value, [string]$Label) {
    if ($Value -notmatch '^[0-9A-Fa-f]{64}$') { throw "Invalid managed hash in install manifest for $Label" }
}

function Get-PathEntry([string]$Path) {
    return Get-Item -Force -LiteralPath $Path -ErrorAction SilentlyContinue
}

function Get-CanonicalInstallerPath([string]$Path, [string]$Label) {
    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw "Unsafe installer destination: empty $Label path."
    }
    try {
        $Full = [IO.Path]::GetFullPath($Path)
    } catch {
        throw "Unsafe installer destination: unable to normalize $Label path: $Path. $($_.Exception.Message)"
    }
    $Root = [IO.Path]::GetPathRoot($Full)
    if ([string]::IsNullOrEmpty($Root)) {
        throw "Unsafe installer destination: unable to canonicalize $Label path: $Path"
    }
    if ($Full.Length -gt $Root.Length) {
        $Full = $Full.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
    }
    return $Full
}

function Assert-SafeInstallerDestinationPath([string]$Path, [string]$Label = "installer destination") {
    $Canonical = Get-CanonicalInstallerPath $Path $Label
    $Comparer = if ([OperatingSystem]::IsWindows()) { [StringComparison]::OrdinalIgnoreCase } else { [StringComparison]::Ordinal }
    if ([string]::Equals($Canonical, $TargetHomeCanonical, $Comparer)) {
        return $Canonical
    }
    $Boundary = $TargetHomeCanonical
    if (-not $Boundary.EndsWith([IO.Path]::DirectorySeparatorChar) -and -not $Boundary.EndsWith([IO.Path]::AltDirectorySeparatorChar)) {
        $Boundary += [IO.Path]::DirectorySeparatorChar
    }
    if (-not $Canonical.StartsWith($Boundary, $Comparer)) {
        throw "Unsafe installer destination: $Path ($Label path escapes configured home: $TargetHomeCanonical)"
    }

    $Relative = $Canonical.Substring($Boundary.Length)
    $Parts = @($Relative -split '[\\/]')
    $Cursor = $TargetHomeCanonical
    for ($Index = 0; $Index -lt $Parts.Count; $Index++) {
        $Part = $Parts[$Index]
        if ([string]::IsNullOrEmpty($Part) -or $Part -eq "." -or $Part -eq "..") {
            throw "Unsafe installer destination: $Path ($Label contains an unsafe component)"
        }
        $Cursor = Join-Path $Cursor $Part
        $Item = Get-Item -Force -LiteralPath $Cursor -ErrorAction SilentlyContinue
        if ($null -eq $Item) {
            break
        }
        if (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Unsafe installer destination: $Path ($Label reparse/symlink component: $Cursor)"
        }
        if ($Index -lt ($Parts.Count - 1) -and -not $Item.PSIsContainer) {
            throw "Unsafe installer destination: $Path ($Label has a non-directory ancestor: $Cursor)"
        }
    }
    return $Canonical
}

function Ensure-SafeInstallerDirectory([string]$Path, [string]$Label = "installer destination", [switch]$RequireMissing) {
    $Canonical = Assert-SafeInstallerDestinationPath $Path $Label
    $Comparer = if ([OperatingSystem]::IsWindows()) { [StringComparison]::OrdinalIgnoreCase } else { [StringComparison]::Ordinal }
    $ConfiguredHome = $TargetHomeCanonical
    $HomeItem = Get-Item -Force -LiteralPath $ConfiguredHome -ErrorAction SilentlyContinue
    if ($null -eq $HomeItem) {
        try {
            New-Item -ItemType Directory -Path $ConfiguredHome -ErrorAction Stop | Out-Null
        } catch {
            throw "Unable to create configured home: $ConfiguredHome. $($_.Exception.Message)"
        }
        $HomeItem = Get-Item -Force -LiteralPath $ConfiguredHome -ErrorAction SilentlyContinue
    }
    if ($null -eq $HomeItem -or -not $HomeItem.PSIsContainer) {
        throw "Configured home is not a directory: $ConfiguredHome"
    }

    if ([string]::Equals($Canonical, $ConfiguredHome, $Comparer)) {
        return $Canonical
    }

    $Boundary = $ConfiguredHome
    if (-not $Boundary.EndsWith([IO.Path]::DirectorySeparatorChar) -and -not $Boundary.EndsWith([IO.Path]::AltDirectorySeparatorChar)) {
        $Boundary += [IO.Path]::DirectorySeparatorChar
    }
    $Relative = $Canonical.Substring($Boundary.Length)
    $Parts = @($Relative -split '[\\/]')
    $Cursor = $ConfiguredHome
    for ($Index = 0; $Index -lt $Parts.Count; $Index++) {
        $Part = $Parts[$Index]
        if ([string]::IsNullOrEmpty($Part) -or $Part -eq "." -or $Part -eq "..") {
            throw "Unsafe installer destination: $Path ($Label contains an unsafe component)"
        }
        $Cursor = Join-Path $Cursor $Part
        $Item = Get-Item -Force -LiteralPath $Cursor -ErrorAction SilentlyContinue
        if ($null -ne $Item) {
            if (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Unsafe installer destination: $Path ($Label reparse/symlink component: $Cursor)"
            }
            if (-not $Item.PSIsContainer) {
                throw "Destination component is not a directory: $Cursor"
            }
            if ($RequireMissing -and $Index -eq ($Parts.Count - 1)) {
                throw "Destination already exists: $Path"
            }
            continue
        }

        try {
            New-Item -ItemType Directory -Path $Cursor -ErrorAction Stop | Out-Null
        } catch {
            throw "Unable to create destination directory: $Cursor. $($_.Exception.Message)"
        }
        [void](Assert-SafeInstallerDestinationPath $Cursor $Label)
        $Created = Get-Item -Force -LiteralPath $Cursor -ErrorAction SilentlyContinue
        if ($null -eq $Created -or -not $Created.PSIsContainer -or (($Created.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
            throw "Unsafe installer destination: $Path ($Label component was not created as a regular directory: $Cursor)"
        }
    }
    [void](Assert-SafeInstallerDestinationPath $Canonical $Label)
    return $Canonical
}

$TargetHomeCanonical = Get-CanonicalInstallerPath $TargetHome "configured home"
$TargetHome = $TargetHomeCanonical
$SkillDest = Join-Path $TargetHome ".agents\skills\agent-orchestrator"
$AgentDest = Join-Path $TargetHome ".codex\agents"
$StateRoot = Join-Path $TargetHome ".agent-orchestrator"
$InstallManifest = Join-Path $SkillDest $InstallManifestName
$LegacyOrchestratorPath = Join-Path $AgentDest "orchestrator.toml"

function Test-PathEntryExists([string]$Path) {
    return $null -ne (Get-PathEntry $Path)
}

[void](Assert-SafeInstallerDestinationPath $SkillDest "Skill destination")
[void](Assert-SafeInstallerDestinationPath $AgentDest "Agent destination")
[void](Assert-SafeInstallerDestinationPath $StateRoot "state root")

function Get-Collisions {
    $Items = New-Object System.Collections.Generic.List[string]
    if (Test-PathEntryExists $SkillDest) { $Items.Add($SkillDest) }
    foreach ($Name in $ExpectedAgentNames) {
        $Dest = Join-Path $AgentDest $Name
        if (Test-PathEntryExists $Dest) { $Items.Add($Dest) }
    }
    return $Items.ToArray()
}

function Get-LegacyOrchestratorStatus {
    $Item = Get-Item -Force -LiteralPath $LegacyOrchestratorPath -ErrorAction SilentlyContinue
    if ($null -eq $Item) { return "none" }
    if ($Item.PSIsContainer -or (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) { return "unknown" }
    if (-not (Test-Path -LiteralPath $LegacyOrchestratorPath -PathType Leaf)) { return "unknown" }
    $Hash = Get-Sha256 $LegacyOrchestratorPath
    if ($LegacyOrchestratorHashes -contains $Hash) { return "known" }
    return "unknown"
}

function Test-SafeInstalledSkillFile([string]$Relative) {
    $SkillItem = Get-PathEntry $SkillDest
    if ($null -eq $SkillItem -or -not $SkillItem.PSIsContainer -or (($SkillItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) { return $false }
    $Cursor = $SkillDest
    $Parts = $Relative -split '/'
    foreach ($Part in $Parts) {
        $Cursor = Join-Path $Cursor $Part
        $Item = Get-PathEntry $Cursor
        if ($null -eq $Item -or (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) { return $false }
    }
    $Final = Get-PathEntry $Cursor
    return ($null -ne $Final -and -not $Final.PSIsContainer)
}

function Get-ExpectedInstalledSkillEntries {
    $Comparer = if ([OperatingSystem]::IsWindows()) { [StringComparer]::OrdinalIgnoreCase } else { [StringComparer]::Ordinal }
    $Expected = [System.Collections.Generic.HashSet[string]]::new($Comparer)
    [void]$Expected.Add($InstallManifestName)
    foreach ($Relative in $ExpectedSkillPaths) {
        [void]$Expected.Add($Relative)
        $Parts = $Relative -split '/'
        if ($Parts.Count -gt 1) {
            $Current = New-Object System.Collections.Generic.List[string]
            for ($Index = 0; $Index -lt ($Parts.Count - 1); $Index++) {
                $Current.Add($Parts[$Index])
                [void]$Expected.Add(($Current -join '/'))
            }
        }
    }
    return $Expected
}

function Read-ManagedManifest {
    $SkillItem = Get-PathEntry $SkillDest
    $ManifestItem = Get-PathEntry $InstallManifest
    if ($null -eq $SkillItem -or -not $SkillItem.PSIsContainer -or (($SkillItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
        throw "Managed Skill destination is missing, non-directory, or a reparse/symlink: $SkillDest"
    }
    if ($null -eq $ManifestItem -or $ManifestItem.PSIsContainer -or (($ManifestItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
        throw "Managed install manifest not found or is not a regular owned file: $InstallManifest"
    }
    $SkillEntries = New-Object System.Collections.Generic.List[object]
    $AgentEntries = New-Object System.Collections.Generic.List[object]
    $SeenSkill = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $SeenAgent = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $VersionEntries = 0
    $LegacyAgentEntries = 0
    foreach ($Line in [IO.File]::ReadAllLines($InstallManifest)) {
        if ([string]::IsNullOrWhiteSpace($Line)) { continue }
        $Parts = $Line -split "`t", 3
        if ($Parts.Count -lt 3) { throw "Invalid managed install manifest line: $Line" }
        switch ($Parts[0]) {
            "version" {
                if ($Parts[1] -notmatch '^\d+\.\d+\.\d+$' -or $Parts[2] -ne '-') { throw "Install manifest version entry is invalid." }
                $VersionEntries++
            }
            "skill" {
                Assert-SafeRelativeManagedPath $Parts[1] "Skill"
                if ($ExpectedSkillPaths -notcontains $Parts[1]) { throw "Unsafe or unknown managed Skill path in install manifest: $($Parts[1])" }
                Assert-ManagedHash $Parts[2] $Parts[1]
                if (-not $SeenSkill.Add($Parts[1])) { throw "Duplicate managed Skill path in install manifest: $($Parts[1])" }
                $SkillEntries.Add([pscustomobject]@{ Path = $Parts[1]; Hash = $Parts[2].ToLowerInvariant() })
            }
            "agent" {
                Assert-ManagedHash $Parts[2] $Parts[1]
                $NormalizedHash = $Parts[2].ToLowerInvariant()
                if ($Parts[1] -eq "orchestrator.toml") {
                    if ($LegacyOrchestratorHashes -notcontains $NormalizedHash) {
                        throw "Install manifest contains an unrecognized legacy orchestrator fingerprint."
                    }
                    $LegacyAgentEntries++
                } elseif ($Parts[1].Contains('/') -or $Parts[1].Contains('\') -or $ExpectedAgentNames -notcontains $Parts[1]) {
                    throw "Unsafe or unknown managed Agent name in install manifest: $($Parts[1])"
                }
                if (-not $SeenAgent.Add($Parts[1])) { throw "Duplicate managed Agent name in install manifest: $($Parts[1])" }
                $AgentEntries.Add([pscustomobject]@{ Path = $Parts[1]; Hash = $NormalizedHash })
            }
            default { throw "Invalid managed install manifest entry: $($Parts[0])" }
        }
    }
    if ($VersionEntries -ne 1) { throw "Install manifest must contain exactly one version entry." }
    if ($SkillEntries.Count -ne $ExpectedSkillPaths.Count) { throw "Install manifest must contain exactly $($ExpectedSkillPaths.Count) canonical runtime Skill files." }
    foreach ($Path in $ExpectedSkillPaths) {
        if (-not $SeenSkill.Contains($Path)) { throw "Install manifest missing managed Skill file: $Path" }
    }
    if ($LegacyAgentEntries -gt 1 -or $AgentEntries.Count -ne ($ExpectedAgentNames.Count + $LegacyAgentEntries)) {
        throw "Install manifest must contain $($ExpectedAgentNames.Count) canonical worker Agent files, plus at most one recognized legacy orchestrator.toml."
    }
    foreach ($Name in $ExpectedAgentNames) {
        if (-not $SeenAgent.Contains($Name)) { throw "Install manifest missing managed Agent: $Name" }
    }
    return [pscustomobject]@{ Skill = $SkillEntries.ToArray(); Agent = $AgentEntries.ToArray() }
}

function Get-CollisionOwnership($Collisions) {
    $ManagedInstall = $null
    $SkillItem = Get-PathEntry $SkillDest
    $ManifestItem = Get-PathEntry $InstallManifest
    if ($null -ne $SkillItem -and $SkillItem.PSIsContainer -and (($SkillItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) -and
        $null -ne $ManifestItem -and -not $ManifestItem.PSIsContainer -and (($ManifestItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0)) {
        try { $ManagedInstall = Read-ManagedManifest } catch { $ManagedInstall = $null }
    }

    $Managed = New-Object System.Collections.Generic.List[string]
    $Unmanaged = New-Object System.Collections.Generic.List[string]
    foreach ($Collision in $Collisions) {
        if ($null -ne $ManagedInstall) {
            if ($Collision -eq $SkillDest) {
                $Managed.Add($Collision)
                continue
            }
            $Name = Split-Path $Collision -Leaf
            if (@($ManagedInstall.Agent | Where-Object { $_.Path -eq $Name }).Count -eq 1) {
                $Managed.Add($Collision)
                continue
            }
        }
        $Unmanaged.Add($Collision)
    }
    return [pscustomobject]@{ Managed = $Managed.ToArray(); Unmanaged = $Unmanaged.ToArray(); ExistingInstall = $ManagedInstall }
}

function Get-ModifiedManagedFiles($Managed) {
    $Modified = New-Object System.Collections.Generic.List[string]
    foreach ($Entry in $Managed.Skill) {
        $Local = $Entry.Path.Replace('/', [IO.Path]::DirectorySeparatorChar)
        $Path = Join-Path $SkillDest $Local
        if (-not (Test-SafeInstalledSkillFile $Entry.Path)) {
            $Modified.Add("$Path (missing, non-regular, or reparse/symlinked component)")
        } elseif ((Get-Sha256 $Path) -ne $Entry.Hash.ToLowerInvariant()) {
            $Modified.Add($Path)
        }
    }

    $ExpectedEntries = Get-ExpectedInstalledSkillEntries
    foreach ($Item in @(Get-ChildItem -Force -Recurse -LiteralPath $SkillDest)) {
        $Relative = [IO.Path]::GetRelativePath($SkillDest, $Item.FullName).Replace('\', '/')
        if (-not $ExpectedEntries.Contains($Relative)) {
            $Modified.Add("$($Item.FullName) (unmanaged extra content)")
        }
    }

    foreach ($Entry in $Managed.Agent) {
        $Path = Join-Path $AgentDest $Entry.Path
        $Item = Get-PathEntry $Path
        if ($null -eq $Item -or $Item.PSIsContainer -or (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
            $Modified.Add("$Path (missing or non-regular)")
        } elseif ((Get-Sha256 $Path) -ne $Entry.Hash.ToLowerInvariant()) {
            $Modified.Add($Path)
        }
    }
    return $Modified.ToArray()
}

function Test-LegacyManagedOwnershipUnknown($Managed) {
    $LegacyEntry = @($Managed.Agent | Where-Object { $_.Path -eq "orchestrator.toml" })
    if ($LegacyEntry.Count -eq 0) { return $false }
    $Item = Get-Item -Force -LiteralPath $LegacyOrchestratorPath -ErrorAction SilentlyContinue
    if ($null -eq $Item) { return $false }
    if ($Item.PSIsContainer -or (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) { return $true }
    if (-not (Test-Path -LiteralPath $LegacyOrchestratorPath -PathType Leaf)) { return $true }
    return ($LegacyOrchestratorHashes -notcontains (Get-Sha256 $LegacyOrchestratorPath))
}

$OperationLockStream = $null
function Acquire-OperationLock {
    [void](Ensure-SafeInstallerDirectory $StateRoot "state root")
    $LockPath = Join-Path $StateRoot "operation.lock"
    [void](Assert-SafeInstallerDestinationPath $LockPath "operation lock")
    try {
        return [IO.File]::Open($LockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    } catch {
        throw "Another Agent Orchestrator operation is already running or holds the operation lock. $($_.Exception.Message)"
    }
}

if (-not $Check) {
    $OperationLockStream = Acquire-OperationLock
}

try {
if ($Uninstall) {
    $SkillItem = Get-PathEntry $SkillDest
    $ManifestItem = Get-PathEntry $InstallManifest
    $HasManagedManifest = ($null -ne $SkillItem -and $SkillItem.PSIsContainer -and (($SkillItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) -and
        $null -ne $ManifestItem -and -not $ManifestItem.PSIsContainer -and (($ManifestItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0))
    if (-not $HasManagedManifest) {
        $UnmanagedTargets = New-Object System.Collections.Generic.List[string]
        foreach ($Path in @(Get-Collisions)) { $UnmanagedTargets.Add($Path) }
        $LegacyStatus = Get-LegacyOrchestratorStatus
        if ($LegacyStatus -ne "none") { $UnmanagedTargets.Add($LegacyOrchestratorPath) }
        if ($Check) {
            if ($UnmanagedTargets.Count -eq 0) {
                Write-Host "CHECK PASS: no managed installation found; uninstall would make no changes."
            } else {
                Write-Host "CHECK PASS: no managed installation found; $($UnmanagedTargets.Count) unmanaged/unverified target(s) are present. A real uninstall is blocked and -Force will not claim them."
                foreach ($Path in $UnmanagedTargets) { Write-Host "  $Path" }
            }
            return
        }
        if ($UnmanagedTargets.Count -eq 0) {
            Write-Host "No managed installation found; nothing to uninstall."
            return
        }
        throw "Refusing to uninstall because no valid managed install manifest exists for the active target(s):`n  $($UnmanagedTargets -join "`n  ")`nThese targets are unmanaged or unverified; -Force will not claim them."
    }

    $Managed = Read-ManagedManifest
    $Modified = @(Get-ModifiedManagedFiles $Managed)
    $LegacyManagedOwnershipUnknown = Test-LegacyManagedOwnershipUnknown $Managed
    if ($Check) {
        if ($LegacyManagedOwnershipUnknown) {
            Write-Host "CHECK PASS: uninstall preflight completed without mutation; active orchestrator.toml no longer matches a recognized legacy fingerprint, so a real uninstall is blocked even with -Force. Move or remove that user-owned profile explicitly first."
            return
        }
        if ($Modified.Count -gt 0) {
            if ($Force) {
                Write-Host "CHECK PASS: uninstall preflight completed without mutation; -Force would back up and remove $($Modified.Count) modified managed file(s)."
            } else {
                Write-Host "CHECK PASS: uninstall preflight completed without mutation; $($Modified.Count) modified managed file(s) found. A real uninstall requires -Force."
            }
            foreach ($Path in $Modified) { Write-Host "  $Path" }
        } else {
            Write-Host "CHECK PASS: uninstall preflight completed without mutation; managed installation can be removed without -Force."
        }
        return
    }
    if ($LegacyManagedOwnershipUnknown) {
        throw "Refusing to uninstall because active orchestrator.toml no longer matches a recognized Agent Orchestrator legacy fingerprint. This profile may now be user-owned; move or remove it explicitly before uninstalling. -Force will not claim it."
    }
    if ($Modified.Count -gt 0 -and -not $Force) {
        throw "Refusing to uninstall because managed files changed after installation:`n  $($Modified -join "`n  ")`nRe-run with -Force to remove the managed installation after backup."
    }

    $Stamp = Get-Date -Format "yyyyMMddHHmmss"
    $BackupRoot = Join-Path $StateRoot ("backups\uninstall-{0}-{1}" -f $Stamp, [guid]::NewGuid().ToString("N"))
    $BackupAgents = Join-Path $BackupRoot "agents"
    [void](Ensure-SafeInstallerDirectory $BackupAgents "uninstall backup")
    $BackupSkill = Join-Path $BackupRoot "skill"
    [void](Assert-SafeInstallerDestinationPath $BackupRoot "uninstall backup")
    [void](Assert-SafeInstallerDestinationPath $BackupSkill "uninstall backup skill")
    try {
        [void](Assert-SafeInstallerDestinationPath $SkillDest "Skill destination")
        Move-Item -LiteralPath $SkillDest -Destination $BackupSkill
        foreach ($Entry in $Managed.Agent) {
            $Path = Join-Path $AgentDest $Entry.Path
            if (Test-PathEntryExists $Path) {
                $BackupAgent = Join-Path $BackupAgents $Entry.Path
                [void](Assert-SafeInstallerDestinationPath $Path "Agent destination")
                [void](Assert-SafeInstallerDestinationPath $BackupAgent "uninstall backup Agent")
                Move-Item -LiteralPath $Path -Destination $BackupAgent
            }
        }
    } catch {
        if ((Test-Path -LiteralPath $BackupSkill) -and -not (Test-Path -LiteralPath $SkillDest)) {
            [void](Ensure-SafeInstallerDirectory (Split-Path $SkillDest -Parent) "Skill destination parent")
            [void](Assert-SafeInstallerDestinationPath $BackupSkill "uninstall backup skill")
            [void](Assert-SafeInstallerDestinationPath $SkillDest "Skill destination")
            Move-Item -LiteralPath $BackupSkill -Destination $SkillDest
        }
        if (Test-Path -LiteralPath $BackupAgents) {
            [void](Ensure-SafeInstallerDirectory $AgentDest "Agent destination")
            foreach ($File in @(Get-ChildItem -LiteralPath $BackupAgents -Filter "*.toml" -File)) {
                $RestoreAgent = Join-Path $AgentDest $File.Name
                [void](Assert-SafeInstallerDestinationPath $File.FullName "uninstall backup Agent")
                [void](Assert-SafeInstallerDestinationPath $RestoreAgent "Agent destination")
                Move-Item -LiteralPath $File.FullName -Destination $RestoreAgent
            }
        }
        throw "Uninstall failed; managed targets were rolled back. $($_.Exception.Message)"
    }
    Write-Host "Uninstalled Agent Orchestrator from active Codex paths."
    Write-Host "Backup: $BackupRoot"
    return
}

$Collisions = @(Get-Collisions)
$CollisionState = Get-CollisionOwnership $Collisions
$LegacyOrchestratorStatus = Get-LegacyOrchestratorStatus
if ($Check) {
    if ($CollisionState.Unmanaged.Count -gt 0) {
        Write-Host "CHECK PASS: source-valid, non-mutating preflight; $($CollisionState.Unmanaged.Count) unmanaged target collision(s) found. A real installation is blocked; -Force will not replace user-owned or unverified targets."
        foreach ($Path in $CollisionState.Unmanaged) { Write-Host "  $Path" }
    } elseif ($CollisionState.Managed.Count -gt 0) {
        if ($Force) {
            Write-Host "CHECK PASS: source-valid, non-mutating preflight; -Force would replace $($CollisionState.Managed.Count) verified managed collision(s)."
        } else {
            Write-Host "CHECK PASS: source-valid, non-mutating preflight; $($CollisionState.Managed.Count) verified managed collision(s) found. A real installation requires -Force."
        }
    } else {
        Write-Host "CHECK PASS: source-valid, non-mutating preflight; no target collisions found."
    }
    if ($LegacyOrchestratorStatus -eq "known") {
        Write-Host "CHECK INFO: a known legacy orchestrator.toml would be backed up and deactivated during a real installation."
    } elseif ($LegacyOrchestratorStatus -eq "unknown") {
        Write-Host "CHECK INFO: unmanaged orchestrator.toml is present, so a real installation is blocked until it is moved or removed manually; -Force will not replace it."
    }
    return
}

if ($LegacyOrchestratorStatus -eq "unknown") {
    throw "Refusing installation because unmanaged orchestrator.toml is present: $LegacyOrchestratorPath`nNo files were changed. Move or remove that user-owned profile explicitly; -Force will not replace it."
}

if ($CollisionState.Unmanaged.Count -gt 0) {
    throw "Refusing installation because unmanaged or unverified target collisions exist:`n  $($CollisionState.Unmanaged -join "`n  ")`nNo files were changed. -Force only replaces targets proven to belong to an existing managed Agent Orchestrator installation."
}

if ($CollisionState.Managed.Count -gt 0 -and -not $Force) {
    throw "Refusing installation because verified managed target collisions exist:`n  $($CollisionState.Managed -join "`n  ")`nNo files were changed. Re-run with -Force only if replacement is intentional."
}

$StagingRoot = Join-Path $StateRoot "staging"
[void](Ensure-SafeInstallerDirectory $StagingRoot "staging root")
$Stage = Join-Path $StagingRoot ("install-" + [guid]::NewGuid().ToString("N"))
[void](Ensure-SafeInstallerDirectory $Stage "staging operation" -RequireMissing)
$StageSkill = Join-Path $Stage "skill"
$StageAgents = Join-Path $Stage "agents"
[void](Ensure-SafeInstallerDirectory $StageSkill "staged Skill")
[void](Ensure-SafeInstallerDirectory $StageAgents "staged Agents")

try {
    foreach ($Relative in $SkillRuntimeFiles) {
        $SourcePath = Join-Path $Root $Relative
        $DestPath = Join-Path $StageSkill $Relative
        [void](Ensure-SafeInstallerDirectory (Split-Path $DestPath -Parent) "staged Skill parent")
        Copy-Item -LiteralPath $SourcePath -Destination $DestPath
    }
    foreach ($Source in $AgentSources) {
        Copy-Item -LiteralPath $Source.FullName -Destination (Join-Path $StageAgents $Source.Name)
    }

    $Lines = New-Object System.Collections.Generic.List[string]
    $Lines.Add("version`t$Version`t-")
    $StagePrefixLength = $StageSkill.Length + 1
    $SkillFiles = @(Get-ChildItem -LiteralPath $StageSkill -Recurse -File | Where-Object { $_.Name -ne $InstallManifestName } | Sort-Object FullName)
    foreach ($File in $SkillFiles) {
        $Relative = $File.FullName.Substring($StagePrefixLength).Replace('\', '/')
        $Lines.Add("skill`t$Relative`t$(Get-Sha256 $File.FullName)")
    }
    foreach ($File in @(Get-ChildItem -LiteralPath $StageAgents -Filter "*.toml" -File | Sort-Object Name)) {
        $Lines.Add("agent`t$($File.Name)`t$(Get-Sha256 $File.FullName)")
    }
    $Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    [IO.File]::WriteAllLines((Join-Path $StageSkill $InstallManifestName), $Lines, $Utf8NoBom)

    # Re-check immediately before committing in case a managed target appeared during staging.
    $Collisions = @(Get-Collisions)
    $CollisionState = Get-CollisionOwnership $Collisions
    $LegacyOrchestratorStatus = Get-LegacyOrchestratorStatus
    if ($LegacyOrchestratorStatus -eq "unknown") {
        throw "Unmanaged orchestrator.toml appeared or changed during staging; no managed target was changed."
    }
    if ($CollisionState.Unmanaged.Count -gt 0) {
        throw "Unmanaged or unverified target collision appeared during staging; no managed target was changed: $($CollisionState.Unmanaged -join ', ')"
    }
    if ($CollisionState.Managed.Count -gt 0 -and -not $Force) {
        throw "Verified managed target collision appeared during staging; no managed target was changed: $($CollisionState.Managed -join ', ')"
    }

    $BackupRoot = $null
    if ($CollisionState.Managed.Count -gt 0 -or $LegacyOrchestratorStatus -eq "known") {
        $Stamp = Get-Date -Format "yyyyMMddHHmmss"
        $BackupRoot = Join-Path $StateRoot ("backups\install-{0}-{1}" -f $Stamp, [guid]::NewGuid().ToString("N"))
        [void](Ensure-SafeInstallerDirectory (Join-Path $BackupRoot "agents") "install backup Agents")
        [void](Assert-SafeInstallerDestinationPath $BackupRoot "install backup")
        [void](Assert-SafeInstallerDestinationPath (Join-Path $BackupRoot "skill") "install backup skill")
    }

    $MovedNewAgents = New-Object System.Collections.Generic.List[string]
    $BackedUpAgents = New-Object System.Collections.Generic.List[string]
    $SkillBackedUp = $false
    $NewSkillInstalled = $false
    $LegacyOrchestratorBackedUp = $false

    function Install-AgentNoClobber([string]$Source, [string]$Destination) {
        [void](Ensure-SafeInstallerDirectory $AgentDest "Agent destination")
        $Temp = Join-Path $AgentDest (".agent-orchestrator-agent-" + [guid]::NewGuid().ToString("N") + ".tmp")
        [void](Assert-SafeInstallerDestinationPath $Temp "temporary Agent destination")
        [void](Assert-SafeInstallerDestinationPath $Destination "Agent destination")
        try {
            Copy-Item -LiteralPath $Source -Destination $Temp
            [IO.File]::Move($Temp, $Destination, $false)
        } catch {
            throw "Late or unverified Agent collision detected during commit; refusing to overwrite: $Destination. $($_.Exception.Message)"
        } finally {
            if (Test-Path -LiteralPath $Temp) {
                [void](Assert-SafeInstallerDestinationPath $Temp "temporary Agent destination")
                Remove-Item -Force -LiteralPath $Temp
            }
        }
    }

    function Install-SkillNoClobber {
        try {
            [void](Ensure-SafeInstallerDirectory $SkillDest "Skill destination" -RequireMissing)
        } catch {
            throw "Late or unverified Skill collision detected during commit; refusing to overwrite: $SkillDest. $($_.Exception.Message)"
        }
        $script:NewSkillInstalled = $true
        foreach ($Relative in @($SkillRuntimeFiles + $InstallManifestName)) {
            $Source = Join-Path $StageSkill $Relative
            $Destination = Join-Path $SkillDest $Relative
            [void](Ensure-SafeInstallerDirectory (Split-Path $Destination -Parent) "Skill destination parent")
            [void](Assert-SafeInstallerDestinationPath $Destination "Skill destination file")
            Copy-Item -LiteralPath $Source -Destination $Destination
        }
    }

    try {
        [void](Ensure-SafeInstallerDirectory (Split-Path $SkillDest -Parent) "Skill destination parent")
        [void](Ensure-SafeInstallerDirectory $AgentDest "Agent destination")
        if (Test-PathEntryExists $SkillDest) {
            [void](Assert-SafeInstallerDestinationPath $SkillDest "Skill destination")
            if ($CollisionState.Managed -notcontains $SkillDest) {
                throw "Late unverified Skill collision appeared during commit; refusing to take ownership: $SkillDest"
            }
            $BackupSkill = Join-Path $BackupRoot "skill"
            [void](Assert-SafeInstallerDestinationPath $BackupSkill "install backup skill")
            Move-Item -LiteralPath $SkillDest -Destination $BackupSkill
            $SkillBackedUp = $true
        }
        foreach ($Source in $AgentSources) {
            $Dest = Join-Path $AgentDest $Source.Name
            if (Test-PathEntryExists $Dest) {
                [void](Assert-SafeInstallerDestinationPath $Dest "Agent destination")
                if ($CollisionState.Managed -notcontains $Dest) {
                    throw "Late unverified Agent collision appeared during commit; refusing to take ownership: $Dest"
                }
                $BackupAgent = Join-Path $BackupRoot "agents\$($Source.Name)"
                [void](Assert-SafeInstallerDestinationPath $BackupAgent "install backup Agent")
                Move-Item -LiteralPath $Dest -Destination $BackupAgent
                $BackedUpAgents.Add($Source.Name)
            }
        }
        $LegacyOrchestratorStatus = Get-LegacyOrchestratorStatus
        if ($LegacyOrchestratorStatus -eq "unknown") {
            throw "Legacy orchestrator ownership changed during commit; refusing to take ownership: $LegacyOrchestratorPath"
        } elseif ($LegacyOrchestratorStatus -eq "known") {
            if (-not $BackupRoot) { throw "Known legacy orchestrator appeared too late for a safe migration; retry the install." }
            $BackupLegacy = Join-Path $BackupRoot "agents\orchestrator.toml"
            [void](Assert-SafeInstallerDestinationPath $LegacyOrchestratorPath "legacy Agent destination")
            [void](Assert-SafeInstallerDestinationPath $BackupLegacy "install backup legacy Agent")
            Move-Item -LiteralPath $LegacyOrchestratorPath -Destination $BackupLegacy
            $LegacyOrchestratorBackedUp = $true
        }

        Install-SkillNoClobber
        foreach ($File in @(Get-ChildItem -LiteralPath $StageAgents -Filter "*.toml" -File)) {
            $Dest = Join-Path $AgentDest $File.Name
            Install-AgentNoClobber $File.FullName $Dest
            $MovedNewAgents.Add($Dest)
        }

        $Managed = Read-ManagedManifest
        $Modified = @(Get-ModifiedManagedFiles $Managed)
        if ($Modified.Count -gt 0) { throw "Post-install integrity verification failed: $($Modified -join ', ')" }
    } catch {
        if ($NewSkillInstalled -and (Test-Path -LiteralPath $SkillDest)) {
            [void](Assert-SafeInstallerDestinationPath $SkillDest "Skill destination")
            Remove-Item -Recurse -Force -LiteralPath $SkillDest
        }
        foreach ($Path in $MovedNewAgents) {
            if (Test-Path -LiteralPath $Path) {
                [void](Assert-SafeInstallerDestinationPath $Path "Agent destination")
                Remove-Item -Force -LiteralPath $Path
            }
        }
        if ($BackupRoot) {
            $BackupSkill = Join-Path $BackupRoot "skill"
            if ($SkillBackedUp -and (Test-Path -LiteralPath $BackupSkill)) {
                [void](Ensure-SafeInstallerDirectory (Split-Path $SkillDest -Parent) "Skill destination parent")
                [void](Assert-SafeInstallerDestinationPath $BackupSkill "install backup skill")
                [void](Assert-SafeInstallerDestinationPath $SkillDest "Skill destination")
                Move-Item -LiteralPath $BackupSkill -Destination $SkillDest
            }
            $BackupAgents = Join-Path $BackupRoot "agents"
            if (Test-Path -LiteralPath $BackupAgents) {
                [void](Ensure-SafeInstallerDirectory $AgentDest "Agent destination")
                foreach ($Name in $BackedUpAgents) {
                    $BackupAgent = Join-Path $BackupAgents $Name
                    if (Test-Path -LiteralPath $BackupAgent) {
                        $RestoreAgent = Join-Path $AgentDest $Name
                        [void](Assert-SafeInstallerDestinationPath $BackupAgent "install backup Agent")
                        [void](Assert-SafeInstallerDestinationPath $RestoreAgent "Agent destination")
                        Move-Item -LiteralPath $BackupAgent -Destination $RestoreAgent
                    }
                }
                $BackupLegacyOrchestrator = Join-Path $BackupAgents "orchestrator.toml"
                if ($LegacyOrchestratorBackedUp -and (Test-Path -LiteralPath $BackupLegacyOrchestrator)) {
                    [void](Assert-SafeInstallerDestinationPath $BackupLegacyOrchestrator "install backup legacy Agent")
                    [void](Assert-SafeInstallerDestinationPath $LegacyOrchestratorPath "legacy Agent destination")
                    Move-Item -LiteralPath $BackupLegacyOrchestrator -Destination $LegacyOrchestratorPath
                }
            }
        }
        throw "Installation failed; managed targets were rolled back. $($_.Exception.Message)"
    }

    Write-Host "Installed Agent Orchestrator v$Version"
    Write-Host "Runtime skill: $SkillDest"
    Write-Host "Agent profiles: $AgentDest"
    if ($BackupRoot) { Write-Host "Backup: $BackupRoot" }
} finally {
    if (Test-Path -LiteralPath $Stage) {
        [void](Assert-SafeInstallerDestinationPath $Stage "staging operation")
        Remove-Item -Recurse -Force -LiteralPath $Stage
    }
}
} finally {
    if ($OperationLockStream) {
        $OperationLockStream.Dispose()
    }
}

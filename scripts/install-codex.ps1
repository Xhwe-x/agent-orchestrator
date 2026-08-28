param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$TargetHome = if ($env:AGENT_ORCHESTRATOR_HOME) { $env:AGENT_ORCHESTRATOR_HOME } else { $HOME }
$SkillDest = Join-Path $TargetHome ".agents\skills\agent-orchestrator"
$AgentDest = Join-Path $TargetHome ".codex\agents"

if ((Test-Path $SkillDest) -and -not $Force) {
    throw "Refusing to replace existing skill at $SkillDest. Re-run with -Force if replacement is intentional."
}

New-Item -ItemType Directory -Force -Path (Split-Path $SkillDest -Parent) | Out-Null
New-Item -ItemType Directory -Force -Path $AgentDest | Out-Null

if (Test-Path $SkillDest) {
    Remove-Item -Recurse -Force $SkillDest
}
New-Item -ItemType Directory -Force -Path $SkillDest | Out-Null
Copy-Item -Force (Join-Path $Root "SKILL.md") (Join-Path $SkillDest "SKILL.md")
Copy-Item -Recurse -Force (Join-Path $Root "agents") (Join-Path $SkillDest "agents")
Copy-Item -Recurse -Force (Join-Path $Root "references") (Join-Path $SkillDest "references")

Get-ChildItem (Join-Path $Root "templates\codex-agents\*.toml") | ForEach-Object {
    $Dest = Join-Path $AgentDest $_.Name
    if ((Test-Path $Dest) -and -not $Force) {
        Write-Host "Skipping existing agent: $Dest"
    } else {
        Copy-Item -Force $_.FullName $Dest
    }
}

Write-Host "Installed runtime skill: $SkillDest"
Write-Host "Installed/updated agent profiles: $AgentDest"

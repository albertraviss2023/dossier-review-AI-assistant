# ground_rules.ps1
# Creates:
#   .codex\config.toml
#   .gemini\settings.json
#   AGENTS.md
#   GEMINI.md
# using CLAUDE.md as the source of truth when it exists.

$ErrorActionPreference = "Stop"

Write-Host "Setting up agent config..." -ForegroundColor Cyan

$root = Get-Location
$claudeFile = Join-Path $root "CLAUDE.md"

$codexDir = Join-Path $root ".codex"
$geminiDir = Join-Path $root ".gemini"

$codexConfig = Join-Path $codexDir "config.toml"
$geminiConfig = Join-Path $geminiDir "settings.json"

$agentsFile = Join-Path $root "AGENTS.md"
$geminiMdFile = Join-Path $root "GEMINI.md"

if (-not (Test-Path -LiteralPath $codexDir)) {
    New-Item -ItemType Directory -Path $codexDir | Out-Null
    Write-Host "Created .codex directory"
}

if (-not (Test-Path -LiteralPath $geminiDir)) {
    New-Item -ItemType Directory -Path $geminiDir | Out-Null
    Write-Host "Created .gemini directory"
}

$codexContent = 'project_doc_fallback_filenames = ["CLAUDE.md"]'

$geminiContent = @'
{
  "context": {
    "fileName": ["CLAUDE.md"]
  }
}
'@

Set-Content -LiteralPath $codexConfig -Value $codexContent -Encoding utf8
Write-Host "Wrote $codexConfig"

Set-Content -LiteralPath $geminiConfig -Value $geminiContent -Encoding utf8
Write-Host "Wrote $geminiConfig"

if (Test-Path -LiteralPath $claudeFile) {
    Copy-Item -LiteralPath $claudeFile -Destination $agentsFile -Force
    Write-Host "Created/updated AGENTS.md from CLAUDE.md"

    Copy-Item -LiteralPath $claudeFile -Destination $geminiMdFile -Force
    Write-Host "Created/updated GEMINI.md from CLAUDE.md"
}
else {
    $placeholder = @'
# CLAUDE.md

Add your project rules here. This file is the source of truth.

Suggested sections:
- Project context
- Hard rules
- Coding rules
- Testing rules
- Deployment rules
- Definition of done
'@

    Set-Content -LiteralPath $claudeFile -Value $placeholder -Encoding utf8
    Write-Host "CLAUDE.md did not exist, so a placeholder was created."

    Copy-Item -LiteralPath $claudeFile -Destination $agentsFile -Force
    Write-Host "Created AGENTS.md from placeholder CLAUDE.md"

    Copy-Item -LiteralPath $claudeFile -Destination $geminiMdFile -Force
    Write-Host "Created GEMINI.md from placeholder CLAUDE.md"
}

Write-Host "Setup complete." -ForegroundColor Green
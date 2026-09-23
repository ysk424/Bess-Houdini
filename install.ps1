param([string]$HoudiniDir, [string]$PrefsDir, [switch]$DryRun, [switch]$DisableLegacyMcp)
$ErrorActionPreference = 'Stop'
$bessArgs = @((Join-Path $PSScriptRoot 'scripts/install.py'))
if ($HoudiniDir) { $bessArgs += @('--houdini-dir', $HoudiniDir) }
if ($PrefsDir) { $bessArgs += @('--prefs-dir', $PrefsDir) }
if ($DryRun) { $bessArgs += '--dry-run' }
if ($DisableLegacyMcp) { $bessArgs += '--disable-legacy-mcp' }
& python @bessArgs
if ($LASTEXITCODE -ne 0) { throw 'Bessのインストールに失敗しました。' }

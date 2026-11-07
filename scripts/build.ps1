param([string]$Python = 'python', [string]$DistPath = 'dist')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$releaseDirectory = if ([IO.Path]::IsPathRooted($DistPath)) { $DistPath } else { Join-Path $projectRoot $DistPath }
& (Join-Path $PSScriptRoot 'build-icons.ps1')
& $Python -m PyInstaller --noconfirm --distpath $releaseDirectory YutongTeams.spec
if ($LASTEXITCODE -ne 0) { throw 'EXE build failed' }
$releaseExe = Join-Path $releaseDirectory 'Yutong Agent Teams.exe'
$releaseHash = (Get-FileHash -LiteralPath $releaseExe -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath "$releaseExe.sha256" -Value "$releaseHash  Yutong Agent Teams.exe" -Encoding UTF8
$sdkDirectory = Join-Path $releaseDirectory 'sdk'
New-Item -ItemType Directory -Path $sdkDirectory -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $projectRoot 'yutong_teams\sdk.py') -Destination (Join-Path $sdkDirectory 'teams_client.py') -Force
Copy-Item -LiteralPath (Join-Path $projectRoot 'docs\INTEGRATIONS.md') -Destination (Join-Path $sdkDirectory 'README.md') -Force
Write-Host "Output: $releaseExe"

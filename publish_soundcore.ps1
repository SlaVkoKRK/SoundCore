param(
    [string]$Repo = "SlaVkoKRK/SoundCore",
    [string]$Branch = "main"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Fail {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
    exit 1
}

function Info {
    param([string]$Message)
    Write-Host "[SOUNDCORE] $Message" -ForegroundColor Cyan
}

function Ok {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Run-Git {
    param([string[]]$Args)
    & git @Args
    return $LASTEXITCODE
}

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Fail "GitHub CLI not found. Install: winget install --id GitHub.cli"
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Fail "Git not found. Install Git for Windows."
}

& gh auth status
if ($LASTEXITCODE -ne 0) {
    Fail "GitHub CLI is not logged in. Run: gh auth login"
}

$env:SOUNDCORE_REPO = $Repo
$env:SOUNDCORE_BRANCH = $Branch

# Create the public repository if it does not exist yet.
$oldEap = $ErrorActionPreference
try {
    $ErrorActionPreference = "SilentlyContinue"
    & gh repo view $Repo 1>$null 2>$null
    $repoExists = ($LASTEXITCODE -eq 0)
}
finally {
    $ErrorActionPreference = $oldEap
}

if (-not $repoExists) {
    Info "Repository $Repo does not exist - creating PUBLIC repository."
    & gh repo create $Repo --public --description "SoundCore - local AI voice cloning and XTTS training" --disable-wiki
    if ($LASTEXITCODE -ne 0) {
        Fail "Could not create repository $Repo"
    }
}

if (-not (Test-Path -LiteralPath ".git")) {
    Info "Initializing local Git repository..."
    & git init
    if ($LASTEXITCODE -ne 0) { Fail "git init failed." }

    & git branch -M $Branch
    if ($LASTEXITCODE -ne 0) { Fail "Could not set branch $Branch." }
}

$origin = ""
$oldEap = $ErrorActionPreference
try {
    $ErrorActionPreference = "SilentlyContinue"
    $origin = (& git remote get-url origin 2>$null | Out-String).Trim()
}
finally {
    $ErrorActionPreference = $oldEap
}

$remoteUrl = "https://github.com/$Repo.git"
if ([string]::IsNullOrWhiteSpace($origin)) {
    & git remote add origin $remoteUrl
    if ($LASTEXITCODE -ne 0) { Fail "Could not add Git remote origin." }
}
else {
    & git remote set-url origin $remoteUrl
    if ($LASTEXITCODE -ne 0) { Fail "Could not update Git remote origin." }
}

# Configure a local commit identity only when none is configured.
$gitUserName = (& git config user.name 2>$null | Out-String).Trim()
$gitUserEmail = (& git config user.email 2>$null | Out-String).Trim()
if ([string]::IsNullOrWhiteSpace($gitUserName)) {
    & git config user.name "SoundCore Publisher"
}
if ([string]::IsNullOrWhiteSpace($gitUserEmail)) {
    & git config user.email "soundcore-publisher@users.noreply.github.com"
}

Info "Building release packages and SHA256 files..."
& python tools/build_release.py
if ($LASTEXITCODE -ne 0) {
    Fail "Release build failed."
}

$metaPath = Join-Path $Root "dist/release.json"
$nextChannelPath = Join-Path $Root "dist/channel.next.json"

if (-not (Test-Path -LiteralPath $metaPath)) {
    Fail "Missing dist/release.json after build."
}
if (-not (Test-Path -LiteralPath $nextChannelPath)) {
    Fail "Missing dist/channel.next.json after build."
}

$meta = Get-Content -LiteralPath $metaPath -Raw | ConvertFrom-Json
$version = [string]$meta.version
$tag = [string]$meta.tag

if ([string]::IsNullOrWhiteSpace($version) -or [string]::IsNullOrWhiteSpace($tag)) {
    Fail "release.json does not contain version/tag."
}

Info "Publishing source code to $Repo / $Branch..."
& git add -A
if ($LASTEXITCODE -ne 0) { Fail "git add failed." }

# channel.next.json must never activate an update before Release assets exist.
& git reset -- "dist/channel.next.json" 2>$null

$oldEap = $ErrorActionPreference
try {
    $ErrorActionPreference = "SilentlyContinue"
    & git diff --cached --quiet
    $hasSourceChanges = ($LASTEXITCODE -ne 0)
}
finally {
    $ErrorActionPreference = $oldEap
}

if ($hasSourceChanges) {
    & git commit -m "release: SoundCore $version source"
    if ($LASTEXITCODE -ne 0) { Fail "Could not create source commit." }
}
else {
    Info "No new source changes to commit."
}

& git push -u origin $Branch
if ($LASTEXITCODE -ne 0) {
    Fail "Could not push source code to GitHub."
}

$updatePath = Join-Path $Root ("dist/" + [string]$meta.update_package)
$sourcePath = Join-Path $Root ("dist/" + [string]$meta.source_package)
$updateShaPath = "$updatePath.sha256"
$sourceShaPath = "$sourcePath.sha256"
$notesPath = Join-Path $Root "RELEASE_NOTES.md"
$releaseJsonPath = Join-Path $Root "dist/release.json"

$requiredFiles = @(
    $updatePath,
    $sourcePath,
    $updateShaPath,
    $sourceShaPath,
    $notesPath,
    $releaseJsonPath
)

foreach ($file in $requiredFiles) {
    if (-not (Test-Path -LiteralPath $file)) {
        Fail "Missing release file: $file"
    }
}

Info "Publishing GitHub Release $tag..."
$oldEap = $ErrorActionPreference
try {
    $ErrorActionPreference = "SilentlyContinue"
    & gh release view $tag --repo $Repo 1>$null 2>$null
    $releaseExists = ($LASTEXITCODE -eq 0)
}
finally {
    $ErrorActionPreference = $oldEap
}

$assets = @(
    $updatePath,
    $sourcePath,
    $updateShaPath,
    $sourceShaPath,
    $releaseJsonPath
)

if ($releaseExists) {
    $ghArgs = @("release", "upload", $tag)
    $ghArgs += $assets
    $ghArgs += @("--repo", $Repo, "--clobber")
    & gh @ghArgs
    if ($LASTEXITCODE -ne 0) {
        Fail "Could not update GitHub Release assets."
    }

    & gh release edit $tag --repo $Repo --title "SoundCore $version" --notes-file $notesPath
    if ($LASTEXITCODE -ne 0) {
        Fail "Could not update GitHub Release notes."
    }
}
else {
    $ghArgs = @("release", "create", $tag)
    $ghArgs += $assets
    $ghArgs += @("--repo", $Repo, "--target", $Branch, "--title", "SoundCore $version", "--notes-file", $notesPath)
    & gh @ghArgs
    if ($LASTEXITCODE -ne 0) {
        Fail "Could not create GitHub Release."
    }
}

Ok "Release $tag is ready."

# Activate the update channel only after Release assets are available.
Info "Activating update channel as the final step..."
Copy-Item -LiteralPath $nextChannelPath -Destination (Join-Path $Root "dist/channel.json") -Force
Copy-Item -LiteralPath $notesPath -Destination (Join-Path $Root ("dist/" + [string]$meta.release_notes)) -Force

& git add "dist/channel.json" "dist/release.json" ("dist/" + [string]$meta.release_notes)
if ($LASTEXITCODE -ne 0) { Fail "Could not stage update channel files." }

if (Test-Path -LiteralPath $updateShaPath) {
    & git add -f "dist/soundcore_update.tar.gz.sha256"
    if ($LASTEXITCODE -ne 0) { Fail "Could not stage update checksum." }
}

$oldEap = $ErrorActionPreference
try {
    $ErrorActionPreference = "SilentlyContinue"
    & git diff --cached --quiet
    $hasChannelChanges = ($LASTEXITCODE -ne 0)
}
finally {
    $ErrorActionPreference = $oldEap
}

if ($hasChannelChanges) {
    & git commit -m "release: activate SoundCore $version update channel"
    if ($LASTEXITCODE -ne 0) {
        Fail "Could not create update-channel commit."
    }

    & git push origin $Branch
    if ($LASTEXITCODE -ne 0) {
        Fail "Could not activate update channel on GitHub."
    }
}
else {
    Info "Update channel is already current; no channel commit needed."
}

Remove-Item -LiteralPath $nextChannelPath -Force -ErrorAction SilentlyContinue

Ok "SoundCore $version published successfully."
Write-Host ""
Write-Host "Repo:    https://github.com/$Repo"
Write-Host "Release: https://github.com/$Repo/releases/tag/$tag"
Write-Host "Channel: https://raw.githubusercontent.com/$Repo/$Branch/dist/channel.json"

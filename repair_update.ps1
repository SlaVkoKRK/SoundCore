param(
    [string]$AppDir = $PSScriptRoot,
    [switch]$NoRestart
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Repo = 'SlaVkoKRK/SoundCore'
$ApiChannel = 'https://api.github.com/repos/SlaVkoKRK/SoundCore/contents/dist/channel.json?ref=main'
$RawChannel = 'https://raw.githubusercontent.com/SlaVkoKRK/SoundCore/main/dist/channel.json'
$Protected = @('voice_profiles','output','songs','engine_runtime','venv','.venv','.git','_repair_backups')
$AppDir = [IO.Path]::GetFullPath($AppDir)
$LogFile = Join-Path $AppDir 'repair-update.log'

function Log([string]$Message) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    Write-Host $line
    try { Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8 } catch {}
}

function Get-Channel {
    Log 'Pobieranie informacji o najnowszej wersji...'
    try {
        $headers = @{ 'User-Agent'='SoundCore-Repair'; 'Accept'='application/vnd.github+json' }
        $payload = Invoke-RestMethod -UseBasicParsing -Uri $ApiChannel -Headers $headers -TimeoutSec 20
        $json = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String(($payload.content -replace '\s','')))
        return $json | ConvertFrom-Json
    }
    catch {
        Log "GitHub API niedostepne, fallback raw: $($_.Exception.Message)"
        $url = $RawChannel + '?_soundcore_repair=' + [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
        return Invoke-RestMethod -UseBasicParsing -Uri $url -Headers @{ 'User-Agent'='SoundCore-Repair'; 'Cache-Control'='no-cache' } -TimeoutSec 20
    }
}

function Stop-SoundCore {
    Log 'Sprawdzanie uruchomionych procesow SoundCore...'
    try {
        $needle = [Regex]::Escape((Join-Path $AppDir 'main.py'))
        $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
            ($_.Name -match '^pythonw?\.exe$') -and ($_.CommandLine -match $needle)
        }
        foreach ($p in $procs) {
            Log "Zamykanie SoundCore PID $($p.ProcessId)..."
            Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        }
        if ($procs) { Start-Sleep -Milliseconds 600 }
    } catch {
        Log "Ostrzezenie przy zamykaniu aplikacji: $($_.Exception.Message)"
    }
}

function New-CodeBackup {
    $backupRoot = Join-Path $AppDir '_repair_backups'
    New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
    $backup = Join-Path $backupRoot (Get-Date -Format 'yyyyMMdd_HHmmss')
    New-Item -ItemType Directory -Path $backup -Force | Out-Null
    Log "Backup kodu: $backup"
    Get-ChildItem -LiteralPath $AppDir -Force | ForEach-Object {
        if (($Protected -notcontains $_.Name) -and ($_.Name -ne 'repair-update.log')) {
            $dest = Join-Path $backup $_.Name
            if ($_.PSIsContainer) { Copy-Item -LiteralPath $_.FullName -Destination $dest -Recurse -Force }
            else { Copy-Item -LiteralPath $_.FullName -Destination $dest -Force }
        }
    }
    Get-ChildItem -LiteralPath $backupRoot -Directory | Sort-Object LastWriteTime -Descending | Select-Object -Skip 3 | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    return $backup
}

function Apply-Payload([string]$PayloadDir) {
    $oldReq = ''
    $reqPath = Join-Path $AppDir 'requirements.txt'
    if (Test-Path $reqPath) { $oldReq = (Get-FileHash -LiteralPath $reqPath -Algorithm SHA256).Hash }

    Get-ChildItem -LiteralPath $PayloadDir -Force | ForEach-Object {
        if ($Protected -contains $_.Name) {
            Log "Pomijam chroniony katalog: $($_.Name)"
        } else {
            $dest = Join-Path $AppDir $_.Name
            if ($_.PSIsContainer) {
                if (Test-Path $dest) { Remove-Item -LiteralPath $dest -Recurse -Force }
                Copy-Item -LiteralPath $_.FullName -Destination $dest -Recurse -Force
            } else {
                Copy-Item -LiteralPath $_.FullName -Destination $dest -Force
            }
        }
    }

    $newReq = ''
    if (Test-Path $reqPath) { $newReq = (Get-FileHash -LiteralPath $reqPath -Algorithm SHA256).Hash }
    if ($newReq -and $newReq -ne $oldReq) {
        $venvPython = Join-Path $AppDir 'venv\Scripts\python.exe'
        if (Test-Path $venvPython) {
            Log 'requirements.txt zmieniony - aktualizacja zaleznosci...'
            & $venvPython -m pip install -r $reqPath
            if ($LASTEXITCODE -ne 0) { throw "pip install zakonczyl sie kodem $LASTEXITCODE" }
        } else {
            Log 'Brak venv Python - pomijam zaleznosci. Uruchom instalator SoundCore, jesli aplikacja nadal nie startuje.'
        }
    }
}

try {
    if (-not (Test-Path $AppDir)) { throw "Katalog SoundCore nie istnieje: $AppDir" }
    Set-Content -LiteralPath $LogFile -Value "SoundCore Repair / Update $(Get-Date -Format o)" -Encoding UTF8
    Log "Katalog aplikacji: $AppDir"

    $channel = Get-Channel
    if (-not $channel.package_url -or -not $channel.sha256) { throw 'channel.json nie zawiera package_url/sha256.' }
    Log "Najnowsza wersja: $($channel.version)"

    Stop-SoundCore

    $temp = Join-Path $env:TEMP ('soundcore-repair-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $temp -Force | Out-Null
    $zip = Join-Path $temp 'soundcore_update.zip'
    $payload = Join-Path $temp 'payload'
    New-Item -ItemType Directory -Path $payload -Force | Out-Null

    Log 'Pobieranie soundcore_update.zip...'
    Invoke-WebRequest -UseBasicParsing -Uri $channel.package_url -OutFile $zip -Headers @{ 'User-Agent'='SoundCore-Repair' } -TimeoutSec 180
    $actual = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
    $expected = ([string]$channel.sha256).Trim().ToLowerInvariant()
    if ($actual -ne $expected) { throw "Bledny SHA256. Oczekiwano $expected, otrzymano $actual" }
    Log 'SHA256 poprawny.'

    Expand-Archive -LiteralPath $zip -DestinationPath $payload -Force
    $null = New-CodeBackup
    Log 'Instalowanie najnowszego kodu...'
    Apply-Payload -PayloadDir $payload

    Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
    $versionPath = Join-Path $AppDir 'VERSION'
    $installed = if (Test-Path $versionPath) { (Get-Content -LiteralPath $versionPath -Raw).Trim() } else { [string]$channel.version }
    Log "Naprawa / aktualizacja zakonczona. Wersja: $installed"

    if (-not $NoRestart) {
        $pythonw = Join-Path $AppDir 'venv\Scripts\pythonw.exe'
        $python = Join-Path $AppDir 'venv\Scripts\python.exe'
        $main = Join-Path $AppDir 'main.py'
        if (Test-Path $pythonw) {
            Log 'Uruchamianie SoundCore...'
            Start-Process -FilePath $pythonw -ArgumentList @(("`"{0}`"" -f $main)) -WorkingDirectory $AppDir
        } elseif (Test-Path $python) {
            Start-Process -FilePath $python -ArgumentList @(("`"{0}`"" -f $main)) -WorkingDirectory $AppDir
        } else {
            Log 'Brak venv - nie moge automatycznie uruchomic SoundCore.'
        }
    }

    Write-Host ''
    Write-Host 'GOTOWE. Mozesz zamknac to okno.' -ForegroundColor Green
    Start-Sleep -Seconds 2
    exit 0
}
catch {
    Log "BLAD: $($_.Exception.Message)"
    try { Log $_.ScriptStackTrace } catch {}
    Write-Host ''
    Write-Host 'Naprawa nie powiodla sie. Log:' -ForegroundColor Red
    Write-Host $LogFile -ForegroundColor Yellow
    Write-Host 'Nacisnij Enter, aby zamknac...' -ForegroundColor Yellow
    [void](Read-Host)
    exit 1
}

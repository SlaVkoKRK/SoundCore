param(
    [Parameter(Mandatory=$true)]
    [string]$AppDir
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$LogFile = Join-Path $AppDir 'install.log'

function Log([string]$Message) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

function Run([string]$Exe, [string[]]$Args, [string]$Label) {
    Log "$Label: $Exe $($Args -join ' ')"
    $p = Start-Process -FilePath $Exe -ArgumentList $Args -Wait -PassThru -NoNewWindow
    if ($p.ExitCode -ne 0) {
        throw "$Label failed with exit code $($p.ExitCode)."
    }
}

function Find-Python310 {
    try {
        $py = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($py) {
            $candidate = (& $py.Source -3.10 -c "import sys; print(sys.executable)" 2>$null | Select-Object -Last 1).Trim()
            if ($candidate -and (Test-Path $candidate)) { return $candidate }
        }
    } catch {}

    $paths = @(
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
        "$env:ProgramFiles\Python310\python.exe",
        "${env:ProgramFiles(x86)}\Python310\python.exe"
    )
    foreach ($p in $paths) {
        if ($p -and (Test-Path $p)) { return $p }
    }
    return $null
}

try {
    New-Item -ItemType Directory -Path $AppDir -Force | Out-Null
    Set-Content -Path $LogFile -Value "SoundCore setup bootstrap" -Encoding UTF8

    Log 'Checking Microsoft WebView2 Runtime.'
    try {
        $wvInstaller = Join-Path $env:TEMP 'MicrosoftEdgeWebview2Setup.exe'
        Invoke-WebRequest -UseBasicParsing -Uri 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' -OutFile $wvInstaller
        $p = Start-Process -FilePath $wvInstaller -ArgumentList @('/silent','/install') -Wait -PassThru
        Log "WebView2 installer exit code: $($p.ExitCode)"
        Remove-Item $wvInstaller -Force -ErrorAction SilentlyContinue
    } catch {
        Log "WebView2 bootstrap warning: $($_.Exception.Message)"
    }

    $python = Find-Python310
    if (-not $python) {
        Log 'Python 3.10 not found. Installing Python 3.10.11 for current user.'
        $pythonInstaller = Join-Path $env:TEMP 'python-3.10.11-amd64.exe'
        Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe' -OutFile $pythonInstaller
        Run $pythonInstaller @('/quiet','InstallAllUsers=0','PrependPath=0','Include_test=0','Include_launcher=1','Include_pip=1') 'Python installation'
        Remove-Item $pythonInstaller -Force -ErrorAction SilentlyContinue
        $python = Find-Python310
    }
    if (-not $python) { throw 'Python 3.10 installation completed but python.exe could not be located.' }
    Log "Using Python: $python"

    $venv = Join-Path $AppDir 'venv'
    $venvPython = Join-Path $venv 'Scripts\python.exe'
    if (-not (Test-Path $venvPython)) {
        Run $python @('-m','venv',$venv) 'Virtual environment creation'
    }

    Run $venvPython @('-m','pip','install','--upgrade','pip','wheel','setuptools<81') 'Pip bootstrap'

    $nvidia = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
    if ($nvidia) {
        Log 'NVIDIA GPU detected. Installing PyTorch 2.5.1 CUDA 12.4 build.'
        try {
            Run $venvPython @('-m','pip','install','--no-deps','torch==2.5.1+cu124','torchvision==0.20.1+cu124','torchaudio==2.5.1+cu124','--index-url','https://download.pytorch.org/whl/cu124') 'PyTorch CUDA installation'
        } catch {
            Log "CUDA PyTorch install warning: $($_.Exception.Message)"
            Log 'Falling back to CPU PyTorch. CUDA can be repaired later from SoundCore.'
            Run $venvPython @('-m','pip','install','torch==2.5.1','torchaudio==2.5.1') 'PyTorch CPU fallback'
        }
    } else {
        Log 'No NVIDIA GPU detected. Installing CPU-compatible dependencies.'
    }

    $requirements = Join-Path $AppDir 'requirements.txt'
    Run $venvPython @('-m','pip','install','-r',$requirements) 'SoundCore dependencies'

    # Re-assert the binary-compatible audio stack after all transitive installs.
    Run $venvPython @('-m','pip','install','--force-reinstall','numpy==1.22.0','scipy==1.10.1') 'NumPy/SciPy compatibility fix'

    Run $venvPython @('-c','import numpy, scipy, torch, webview, TTS; print("SoundCore runtime OK")') 'Runtime verification'

    Set-Content -Path (Join-Path $AppDir '.installed') -Value (Get-Date -Format o) -Encoding ASCII
    Log 'Installation completed successfully.'
    exit 0
}
catch {
    Log "FATAL: $($_.Exception.Message)"
    Write-Error $_
    exit 1
}

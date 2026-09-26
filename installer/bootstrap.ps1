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

function Run([string]$Exe, [string[]]$Arguments, [string]$Label) {
    $safeArguments = @()
    foreach ($item in @($Arguments)) {
        if ($null -ne $item) {
            $safeArguments += [string]$item
        }
    }

    Log "${Label}: $Exe $($safeArguments -join ' ')"
    if (-not (Test-Path $Exe) -and -not (Get-Command $Exe -ErrorAction SilentlyContinue)) {
        throw "$Label failed: executable not found: $Exe"
    }

    $previousErrorAction = $ErrorActionPreference
    try {
        # Invoke the native executable directly instead of Start-Process -ArgumentList.
        # This preserves the argument array exactly (including paths with spaces) and
        # avoids the PowerShell automatic $args variable collision that broke 0.4.4.
        $ErrorActionPreference = 'Continue'
        & $Exe @safeArguments 2>&1 | ForEach-Object {
            if ($null -ne $_) {
                Log ("  " + $_.ToString())
            }
        }
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorAction
    }

    if ($exitCode -ne 0) {
        throw "$Label failed with exit code $exitCode."
    }
}

function Find-Python310 {
    try {
        $py = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($py) {
            $candidate = (& $py.Source -3.10 -c "import sys; print(sys.executable)" 2>$null | Select-Object -Last 1)
            if ($candidate) {
                $candidate = $candidate.ToString().Trim()
                if ($candidate -and (Test-Path $candidate)) { return $candidate }
            }
        }
    } catch { Log "Python launcher probe warning: $($_.Exception.Message)" }

    $paths = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python310\python.exe'),
        (Join-Path $env:ProgramFiles 'Python310\python.exe')
    )
    if (${env:ProgramFiles(x86)}) {
        $paths += (Join-Path ${env:ProgramFiles(x86)} 'Python310\python.exe')
    }
    foreach ($p in $paths) {
        if ($p -and (Test-Path $p)) { return $p }
    }
    return $null
}

try {
    New-Item -ItemType Directory -Path $AppDir -Force | Out-Null
    Set-Content -Path $LogFile -Value "SoundCore setup bootstrap $(Get-Date -Format o)" -Encoding UTF8
    Remove-Item (Join-Path $AppDir '.installed') -Force -ErrorAction SilentlyContinue

    Log 'Checking Microsoft WebView2 Runtime.'
    try {
        $wvInstaller = Join-Path $env:TEMP 'MicrosoftEdgeWebview2Setup.exe'
        Invoke-WebRequest -UseBasicParsing -Uri 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' -OutFile $wvInstaller
        $p = Start-Process -FilePath $wvInstaller -ArgumentList @('/silent','/install') -Wait -PassThru -WindowStyle Hidden
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
        Run -Exe $pythonInstaller -Arguments @('/quiet','InstallAllUsers=0','PrependPath=0','Include_test=0','Include_launcher=1','Include_pip=1') -Label 'Python installation'
        Remove-Item $pythonInstaller -Force -ErrorAction SilentlyContinue
        $python = Find-Python310
    }
    if (-not $python) { throw 'Python 3.10 installation completed but python.exe could not be located.' }
    Log "Using Python: $python"

    $venv = Join-Path $AppDir 'venv'
    $venvPython = Join-Path $venv 'Scripts\python.exe'
    $venvPythonw = Join-Path $venv 'Scripts\pythonw.exe'
    if (-not (Test-Path $venvPython)) {
        Log "Creating venv: $venv"
        Run -Exe $python -Arguments @('-m','venv',$venv) -Label 'Virtual environment creation'
    }
    if (-not (Test-Path $venvPython)) { throw "venv python.exe missing after creation: $venvPython" }
    if (-not (Test-Path $venvPythonw)) { throw "venv pythonw.exe missing after creation: $venvPythonw" }

    Run -Exe $venvPython -Arguments @('-m','pip','install','--upgrade','pip','wheel','setuptools<81') -Label 'Pip bootstrap'

    $nvidia = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
    if ($nvidia) {
        Log 'NVIDIA GPU detected. Installing PyTorch 2.5.1 CUDA 12.4 build.'
        try {
            Run -Exe $venvPython -Arguments @('-m','pip','install','--no-deps','torch==2.5.1+cu124','torchvision==0.20.1+cu124','torchaudio==2.5.1+cu124','--index-url','https://download.pytorch.org/whl/cu124') -Label 'PyTorch CUDA installation'
        } catch {
            Log "CUDA PyTorch install warning: $($_.Exception.Message)"
            Log 'Falling back to CPU PyTorch. CUDA can be repaired later from SoundCore.'
            Run -Exe $venvPython -Arguments @('-m','pip','install','torch==2.5.1','torchaudio==2.5.1') -Label 'PyTorch CPU fallback'
        }
    } else {
        Log 'No NVIDIA GPU detected. requirements.txt will provide compatible PyTorch dependencies.'
    }

    $requirements = Join-Path $AppDir 'requirements.txt'
    if (-not (Test-Path $requirements)) { throw "requirements.txt not found: $requirements" }
    Run -Exe $venvPython -Arguments @('-m','pip','install','-r',$requirements) -Label 'SoundCore dependencies'

    Run -Exe $venvPython -Arguments @('-m','pip','install','--force-reinstall','numpy==1.22.0','scipy==1.10.1') -Label 'NumPy/SciPy compatibility fix'
    Run -Exe $venvPython -Arguments @('-c','import numpy, scipy, torch, webview, TTS; print("SoundCore runtime OK"); print("numpy", numpy.__version__); print("scipy", scipy.__version__); print("torch", torch.__version__); print("cuda", torch.cuda.is_available())') -Label 'Runtime verification'

    if (-not (Test-Path $venvPythonw)) { throw "Final validation failed: $venvPythonw does not exist." }
    Set-Content -Path (Join-Path $AppDir '.installed') -Value (Get-Date -Format o) -Encoding ASCII
    Log 'Installation completed successfully.'
    exit 0
}
catch {
    Log "FATAL: $($_.Exception.Message)"
    try { Log ($_.ScriptStackTrace) } catch {}
    Write-Error $_
    exit 1
}

# OneTunnel v0.7 Qt Preview build.
# Keeps stable Tkinter build separate while the Qt frontend matures.
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    py -3.13 --version
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.13 es obligatorio' }

    py -3.13 -m pip install -r requirements-qt.txt
    if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar dependencias Qt' }

    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
    if (-not (Test-Path $vswhere)) { throw 'Instala Visual Studio Build Tools con MSVC y Windows SDK' }
    $vsVersion = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationVersion
    if (-not $vsVersion) { throw 'No se encontró MSVC C++' }
    $major = [int]($vsVersion.Split('.')[0])
    $generator = switch ($major) {
        17 { 'Visual Studio 17 2022' }
        18 { 'Visual Studio 18 2026' }
        default { throw "Visual Studio no compatible: $vsVersion" }
    }

    cmake -S ../native/wfp -B ../native/wfp/build -G $generator -A x64
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo configurar motor WFP' }
    cmake --build ../native/wfp/build --config Release
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo compilar motor WFP' }

    $Native = Resolve-Path ../native/wfp/build/Release
    $Guard = Join-Path $Native 'onetunnel-wfp-guard.exe'
    $Relay = Join-Path $Native 'onetunnel-transparent-relay.exe'
    $Control = Join-Path $Native 'onetunnel-wfp-control.exe'
    $Probe = Join-Path $Native 'onetunnel-egress-probe.exe'
    foreach ($item in ($Guard,$Relay,$Control,$Probe)) {
        if (-not (Test-Path $item)) { throw "Falta componente nativo: $item" }
    }

    $env:QT_QPA_PLATFORM='offscreen'
    py -3.13 -c "from PySide6.QtWidgets import QApplication; from qt_app import OneTunnelQt; a=QApplication([]); w=OneTunnelQt(); assert w.stack.count()==5; assert w.connect_button.text()=='CONECTAR'; w.close()"
    if ($LASTEXITCODE -ne 0) { throw 'Smoke Qt falló' }

    py -3.13 -m PyInstaller --noconfirm --clean --windowed --onefile --name OneTunnel-Qt-Preview --add-binary "$Guard;." --add-binary "$Relay;." --add-binary "$Control;." --add-binary "$Probe;." qt_app.py
    if ($LASTEXITCODE -ne 0) { throw 'Falló empaquetado Qt' }

    Write-Host 'Qt Preview listo en desktop_prototype/dist/OneTunnel-Qt-Preview.exe' -ForegroundColor Green
} finally {
    Pop-Location
}

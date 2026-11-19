# OneTunnel Desktop Lab: build UI + first-party WFP guard.
# Needs Python 3.13, CMake, VS 2022 Build Tools / Windows SDK.
# The build DOES NOT install or activate any WFP filters.
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    py -3.13 --version
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.13 es obligatorio para empaquetar Tkinter' }
    py -3.13 -m pip show pyinstaller *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Instala PyInstaller 6.16.0 para Python 3.13' }
    py -3.13 -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Fallaron pruebas Python' }
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
    if (-not (Test-Path $vswhere)) { throw 'Instala Visual Studio Build Tools con MSVC y Windows SDK' }
    $vsVersion = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationVersion
    if (-not $vsVersion) { throw 'No se encontró un compilador MSVC C++' }
    $vsMajor = [int]($vsVersion.Split('.')[0])
    $generator = switch ($vsMajor) {
        17 { 'Visual Studio 17 2022' }
        18 { 'Visual Studio 18 2026' }
        default { throw "Visual Studio no compatible: $vsVersion" }
    }
    cmake -S ../native/wfp -B ../native/wfp/build -G $generator -A x64
    if ($LASTEXITCODE -ne 0) { throw "No se pudo configurar WFP con $generator" }
    cmake --build ../native/wfp/build --config Release
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo compilar el motor WFP' }
    $NativeDir = (Resolve-Path ../native/wfp/build/Release).Path
    $Helper = Join-Path $NativeDir 'onetunnel-wfp-guard.exe'
    $Relay = Join-Path $NativeDir 'onetunnel-transparent-relay.exe'
    if (-not (Test-Path $Helper)) { throw 'No existe el helper WFP' }
    if (-not (Test-Path $Relay)) { throw 'No existe el relay transparente' }
    & $Relay --self-test
    if ($LASTEXITCODE -ne 0) { throw 'Falló el self-test del relay transparente' }
    py -3.13 -m PyInstaller --noconfirm --clean --windowed --onefile --name 1VPN-Desktop-Lab --add-binary "$Helper;." --add-binary "$Relay;." app.py
    if ($LASTEXITCODE -ne 0) { throw 'Error empaquetando el EXE' }
    Write-Host 'EXE con WFP nativo en desktop_prototype/dist/1VPN-Desktop-Lab.exe' -ForegroundColor Green
} finally {
    Pop-Location
}

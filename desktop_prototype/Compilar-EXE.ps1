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
    cmake -S ../native/wfp -B ../native/wfp/build -G "Visual Studio 17 2022" -A x64
    if ($LASTEXITCODE -ne 0) { throw 'Necesitas CMake y VS 2022 Build Tools' }
    cmake --build ../native/wfp/build --config Release
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo compilar el motor WFP' }
    $Helper = Join-Path (Resolve-Path ../native/wfp/build/Release).Path 'onetunnel-wfp-guard.exe'
    if (-not (Test-Path $Helper)) { throw 'No existe el helper WFP' }
    py -3.13 -m PyInstaller --noconfirm --clean --windowed --onefile --name 1VPN-Desktop-Lab --add-binary "$Helper;." app.py
    if ($LASTEXITCODE -ne 0) { throw 'Error empaquetando el EXE' }
    Write-Host 'EXE con WFP nativo en desktop_prototype/dist/1VPN-Desktop-Lab.exe' -ForegroundColor Green
} finally {
    Pop-Location
}

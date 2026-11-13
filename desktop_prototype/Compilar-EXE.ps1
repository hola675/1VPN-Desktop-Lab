# Compila un EXE local mediante PyInstaller. Requiere internet para instalarlo si falta.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
py -3 -m pip show pyinstaller *> $null
if ($LASTEXITCODE -ne 0) {
    throw 'PyInstaller no está instalado. Instala explícitamente: py -3 -m pip install pyinstaller'
}
py -3 -m PyInstaller --noconfirm --clean --windowed --onefile --name 1VPN-Desktop-Lab app.py
Write-Host 'EXE creado en desktop_prototype\dist\1VPN-Desktop-Lab.exe'

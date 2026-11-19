param(
    [string]$SignedDriverDirectory = $env:ONETUNNEL_SIGNED_DRIVER_DIR
)

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
    $Control = Join-Path $NativeDir 'onetunnel-wfp-control.exe'
    if (-not (Test-Path $Helper)) { throw 'No existe el helper WFP' }
    if (-not (Test-Path $Relay)) { throw 'No existe el relay transparente' }
    if (-not (Test-Path $Control)) { throw 'No existe el control plane WFP' }
    & $Relay --self-test
    if ($LASTEXITCODE -ne 0) { throw 'Falló el self-test del relay transparente' }
    & $Control --self-test
    if ($LASTEXITCODE -ne 0) { throw 'Falló el self-test del control plane WFP' }
    $PyInstallerArgs = @(
        '-m', 'PyInstaller',
        '--noconfirm', '--clean', '--windowed', '--onefile',
        '--name', '1VPN-Desktop-Lab',
        '--add-binary', "$Helper;.",
        '--add-binary', "$Relay;.",
        '--add-binary', "$Control;."
    )

    if ($SignedDriverDirectory) {
        $SignedDriverDirectory = (Resolve-Path -LiteralPath $SignedDriverDirectory).Path
        Write-Host "Verificando paquete WFP firmado: $SignedDriverDirectory" -ForegroundColor Cyan
        & py -3.13 -c "from driver_lifecycle import verify_package; import sys; v=verify_package(sys.argv[1]); print('SIGNED_DRIVER_OK:', v.signer)" $SignedDriverDirectory
        if ($LASTEXITCODE -ne 0) {
            throw 'El paquete WFP no tiene una firma/catálogo confiable para Windows'
        }

        $Inf = Join-Path $SignedDriverDirectory 'OneTunnelRedirect.inf'
        $Cat = Join-Path $SignedDriverDirectory 'OneTunnelRedirect.cat'
        $Sys = Join-Path $SignedDriverDirectory 'onetunnel-wfp-redirect.sys'
        foreach ($Required in @($Inf, $Cat, $Sys)) {
            if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) {
                throw "Falta archivo firmado obligatorio: $Required"
            }
        }

        $PyInstallerArgs += @(
            '--add-data', "$Inf;driver_package",
            '--add-data', "$Cat;driver_package",
            '--add-binary', "$Sys;driver_package"
        )
        Write-Host 'Paquete WFP FIRMADO aceptado: se integrará dentro de OneTunnel.' -ForegroundColor Green
    }
    else {
        Write-Host 'Build sin paquete kernel: PROXY WFP seguirá requiriendo paquete firmado externo.' -ForegroundColor Yellow
    }

    $PyInstallerArgs += 'app.py'
    & py -3.13 @PyInstallerArgs
    if ($LASTEXITCODE -ne 0) { throw 'Error empaquetando el EXE' }

    $Exe = Join-Path $PSScriptRoot 'dist\1VPN-Desktop-Lab.exe'
    Write-Host "EXE creado: $Exe" -ForegroundColor Green
    if ($SignedDriverDirectory) {
        Write-Host 'Release incluye paquete WFP firmado y será detectado automáticamente por la UI.' -ForegroundColor Green
    }
} finally {
    Pop-Location
}

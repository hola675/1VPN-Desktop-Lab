#requires -Version 7.0
<#
Descarga la extensión compilada y su fuente OFICIALES (misma etiqueta).
NO instala, NO ejecuta y NO modifica la configuración de red.
El contenido descargado pertenece a sus autores y está sujeto a su licencia.
#>
[CmdletBinding()]
param(
    [string]$Destino = (Join-Path $PSScriptRoot '..\referencias-oficiales'),
    [switch]$IncluirAndroid
)
$ErrorActionPreference = 'Stop'
$Destino = [System.IO.Path]::GetFullPath($Destino)
New-Item -ItemType Directory -Path $Destino -Force | Out-Null
$headers = @{ 'User-Agent' = '1VPN-Desktop-Lab-Research'; 'Accept' = 'application/vnd.github+json' }

Write-Host '== CONSULTANDO VERSIÓN OFICIAL ==' -ForegroundColor Cyan
$release = Invoke-RestMethod -Headers $headers -Uri 'https://api.github.com/repos/1vpn/browser-extension/releases/latest'
$tag = [string]$release.tag_name
if ($tag -notmatch '^v\d+\.\d+\.\d+$') { throw "Etiqueta inesperada: $tag" }
$asset = @($release.assets | Where-Object { $_.name -eq "1vpn-$tag-chrome.zip" }) | Select-Object -First 1
if (-not $asset) { throw "No existe el ZIP Chrome oficial de $tag" }
$packagedPath = Join-Path $Destino ([string]$asset.name)
$sourcePath = Join-Path $Destino ("1vpn-$tag-source.zip")
$chromeDir = Join-Path $Destino ("extension-chrome-$tag")
$srcDir = Join-Path $Destino ("source-$tag")

Write-Host "Extensión oficial: $tag" -ForegroundColor Green
Write-Host '== DESCARGANDO CÓDIGO COMPILADO ==' -ForegroundColor Cyan
Invoke-WebRequest -Headers $headers -Uri ([string]$asset.browser_download_url) -OutFile $packagedPath
if ((Get-Item $packagedPath).Length -ne [long]$asset.size) {
    throw 'El tamaño descargado no coincide con el publicado por GitHub.'
}
Write-Host '== DESCARGANDO CÓDIGO FUENTE CORRESPONDIENTE ==' -ForegroundColor Cyan
$sourceUrl = "https://github.com/1vpn/browser-extension/archive/refs/tags/$tag.zip"
Invoke-WebRequest -Headers $headers -Uri $sourceUrl -OutFile $sourcePath

foreach ($item in @($chromeDir, $srcDir)) {
    if (Test-Path $item) { throw "La carpeta ya existe: $item. No se sobrescribirá." }
}
Expand-Archive -LiteralPath $packagedPath -DestinationPath $chromeDir
Expand-Archive -LiteralPath $sourcePath -DestinationPath $srcDir

$manifest = Get-ChildItem -LiteralPath $chromeDir -Filter manifest.json -File -Recurse | Select-Object -First 1
if (-not $manifest) { throw 'El paquete Chrome no contiene manifest.json' }
$manifestData = Get-Content -LiteralPath $manifest.FullName -Raw | ConvertFrom-Json
$expectedVersion = $tag.TrimStart('v')
if ([string]$manifestData.version -ne $expectedVersion) {
    throw "Versión inconsistente. Release=$expectedVersion, manifest=$($manifestData.version)"
}

$hashes = @(
    [PSCustomObject]@{ Archivo = $packagedPath; SHA256 = (Get-FileHash -LiteralPath $packagedPath -Algorithm SHA256).Hash },
    [PSCustomObject]@{ Archivo = $sourcePath; SHA256 = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash }
)
$hashes | Format-Table -AutoSize
$metadata = [PSCustomObject]@{
    fecha_utc = (Get-Date).ToUniversalTime().ToString('o')
    fuente = 'https://github.com/1vpn/browser-extension'
    etiqueta = $tag
    release = [string]$release.html_url
    extension_url = [string]$asset.browser_download_url
    source_url = $sourceUrl
    manifest_version = [string]$manifestData.version
    hashes = $hashes
}
$metadata | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath (Join-Path $Destino 'inventario.json') -Encoding utf8
Write-Host "Descargado y validado en: $Destino" -ForegroundColor Green

if ($IncluirAndroid) {
    $appSource = Join-Path $Destino '1vpn-app-main.zip'
    Invoke-WebRequest -Headers $headers -Uri 'https://github.com/1vpn/app/archive/refs/heads/main.zip' -OutFile $appSource
    Write-Host "Referencia Android (fuente): $appSource" -ForegroundColor Green
}
Write-Host 'No se han ejecutado binarios ni scripts descargados.' -ForegroundColor Yellow

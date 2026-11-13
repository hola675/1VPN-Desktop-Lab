# 1VPN Desktop Lab - iniciador para Windows PowerShell 7
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (Get-Command py -ErrorAction SilentlyContinue) {
    py -3 app.py
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    python app.py
} else {
    throw 'Python 3 no encontrado. Instala Python 3 para ejecutar el prototipo.'
}

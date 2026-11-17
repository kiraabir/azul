#!/usr/bin/env pwsh
# Start AZUL server
$ErrorActionPreference = 'Stop'
$proj = split-path $PSScriptRoot
$venv = "$proj\venv"

Set-Location $proj
& "$venv\Scripts\python.exe" -m client.app $args
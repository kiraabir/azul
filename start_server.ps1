#!/usr/bin/env pwsh
# Start AZUL Flask dev server in the background.
$proj = (Get-Item $PSScriptRoot).Parent.FullName
$env:SECRET_KEY = 'dev-secret-key-change-in-production'
Set-Location $proj
& "$proj\venv\Scripts\python.exe" app.py > "$proj\server.log" 2>&1
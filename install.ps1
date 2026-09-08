$ErrorActionPreference = "Stop"
$sourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& python -B (Join-Path $sourceDir "install.py") @args
exit $LASTEXITCODE


param(
  [Parameter(Mandatory=$true)][string]$Src,
  [Parameter(Mandatory=$true)][string]$Out
)
if (Test-Path $Out) { Remove-Item $Out -Force }
Compress-Archive -Path (Join-Path $Src '*') -DestinationPath $Out -Force
Write-Host "Packed $Src -> $Out"

# scripts/smoke-webhook.ps1 — send a few sample webhook calls
param(
  [string]$Gateway = "https://thanyaaura-gateway-1.onrender.com",
  [string]$Secret  = "A0GLS8PU5THM",
  [string]$Email   = "buyer@example.com"
)

function Show-ErrorBody($err) {
  try {
    $resp = $err.Exception.Response
    if ($resp -ne $null) {
      $reader = New-Object System.IO.StreamReader($resp.GetResponseStream())
      $body = $reader.ReadToEnd()
      Write-Host "---- Server error body ----`n$body`n---------------------------" -ForegroundColor Yellow
    }
  } catch {}
}

Write-Host "Health check on $Gateway ..." -ForegroundColor Cyan
try {
  $h = Invoke-RestMethod -Method GET -Uri "$Gateway/health"
  "status: $($h.status)"
} catch { Show-ErrorBody $_; exit 1 }

# Sample: single agent
$form1 = @{
  "event"="order.success"
  "order_id"="tc-agent-cfp-001"
  "customer[email]"=$Email
  "sku"="cfp"
  "thrivecart_secret"=$Secret
}
try {
  $res1 = Invoke-RestMethod -Method POST -Uri "$Gateway/billing/thrivecart" -ContentType "application/x-www-form-urlencoded" -Body $form1
  Write-Host "AGENT result:" -ForegroundColor Green
  $res1 | Format-List
} catch { Show-ErrorBody $_ }

# Sample: tier
$form2 = @{
  "event"="order.success"
  "order_id"="tc-tier-prem-001"
  "customer[email]"=$Email
  "sku"="premium"
  "thrivecart_secret"=$Secret
}
try {
  $res2 = Invoke-RestMethod -Method POST -Uri "$Gateway/billing/thrivecart" -ContentType "application/x-www-form-urlencoded" -Body $form2
  Write-Host "TIER result:" -ForegroundColor Green
  $res2 | Format-List
} catch { Show-ErrorBody $_ }

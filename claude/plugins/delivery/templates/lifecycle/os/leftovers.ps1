# DS235d: after a purge, list what the product left on Windows (LC-15). Exit 0 and no output when nothing is left.
# Reads lifecycle.json: product, paths.*, paths.listen_ports.
param([string]$Lifecycle = $(if ($env:LIFECYCLE_JSON) { $env:LIFECYCLE_JSON } else { 'lifecycle.json' }))
$ErrorActionPreference = 'Stop'
$lc = Get-Content -Raw $Lifecycle | ConvertFrom-Json
$product = $lc.product
$service = if ($lc.paths.service) { $lc.paths.service } else { $product }
$found = New-Object System.Collections.Generic.List[string]

# files and folders
foreach ($key in 'install', 'config', 'data', 'logs') {
  foreach ($p in @($lc.paths.$key)) { if ($p -and (Test-Path $p)) { $found.Add("file: $p") } }
}
foreach ($p in @($lc.paths.legacy_data)) { if ($p -and (Test-Path $p)) { $found.Add("legacy folder: $p") } }
# services
if (Get-Service -Name $service -ErrorAction SilentlyContinue) { $found.Add("service: $service") }
# scheduled tasks
Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object { $_.TaskName -like "*$product*" } |
  ForEach-Object { $found.Add("scheduled task: $($_.TaskPath)$($_.TaskName)") }
# registry Run and Uninstall keys
foreach ($hive in 'HKLM:', 'HKCU:') {
  $run = "$hive\Software\Microsoft\Windows\CurrentVersion\Run"
  if (Test-Path $run) {
    $props = (Get-ItemProperty $run).PSObject.Properties | Where-Object { $_.Name -like "*$product*" }
    foreach ($p in $props) { $found.Add("registry Run: $hive $($p.Name)") }
  }
  foreach ($base in "$hive\Software\Microsoft\Windows\CurrentVersion\Uninstall", "$hive\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall") {
    if (Test-Path $base) {
      Get-ChildItem $base -ErrorAction SilentlyContinue | ForEach-Object {
        $dn = (Get-ItemProperty $_.PSPath).DisplayName
        if ($dn -and $dn -like "*$product*") { $found.Add("registry Uninstall: $($_.PSChildName) ($dn)") }
      }
    }
  }
}
# firewall rules
Get-NetFirewallRule -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -like "*$product*" } |
  ForEach-Object { $found.Add("firewall rule: $($_.DisplayName)") }
# listening ports
$ports = @($lc.paths.listen_ports) + @($lc.paths.console_port) | Where-Object { $_ }
foreach ($port in $ports) {
  if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) { $found.Add("listening port: $port") }
}
$found | ForEach-Object { Write-Output $_ }
if ($found.Count -gt 0) { exit 1 }
exit 0

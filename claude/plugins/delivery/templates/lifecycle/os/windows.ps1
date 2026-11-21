# DS235d: Windows MSI lifecycle steps (LC-8 to LC-17, LC-18, LC-29, LC-33).
# Usage: pwsh ./windows.ps1 -Check all|lc9|lc8|...|lint -Lifecycle lifecycle.json -Pkg App-1.2.0-x64.msi
# Other packages: -PrevPkg (N-1), -BrokenPkg, -OlderPkg. Prints "LC-9 PASS detail" per check; exit 1 on any FAIL.
param(
  [string]$Check = 'all',
  [string]$Lifecycle = $(if ($env:LIFECYCLE_JSON) { $env:LIFECYCLE_JSON } else { 'lifecycle.json' }),
  [string]$Pkg = $env:LC_PKG, [string]$PrevPkg = $env:LC_PREV_PKG,
  [string]$BrokenPkg = $env:LC_BROKEN_PKG, [string]$OlderPkg = $env:LC_OLDER_PKG
)
$ErrorActionPreference = 'Stop'
$script:Fails = 0
$script:Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$script:Lc = Get-Content -Raw $Lifecycle | ConvertFrom-Json
$script:Product = $script:Lc.product
$script:Service = if ($script:Lc.paths.service) { $script:Lc.paths.service } else { $script:Product }

function Out-Lc($id, $ok, $detail) {
  Write-Output ("{0} {1} {2}" -f $id, $(if ($ok) { 'PASS' } else { 'FAIL' }), $detail)
  if (-not $ok) { $script:Fails++ }
}
function Install-Msi($file, [switch]$Purge) {
  $a = @('/i', $file, '/qn', '/norestart')
  $p = Start-Process msiexec.exe -ArgumentList $a -Wait -PassThru
  return $p.ExitCode
}
function Remove-Msi([switch]$Purge) {
  $code = $script:Lc.paths.product_code
  $a = @('/x', $code, '/qn', '/norestart')
  if ($Purge) { $a += 'PURGE=1' }
  return (Start-Process msiexec.exe -ArgumentList $a -Wait -PassThru).ExitCode
}
function Get-Checksums($paths) {
  $paths | Where-Object { $_ -and (Test-Path $_) } | ForEach-Object { Get-ChildItem $_ -Recurse -File } |
    Sort-Object FullName | ForEach-Object { '{0} {1}' -f (Get-FileHash $_.FullName).Hash, $_.FullName }
}
function Get-Version {
  $k = Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue |
    Where-Object { $_.DisplayName -eq $script:Product }
  if ($k) { return $k.DisplayVersion } else { return $null }
}
function Test-Up {
  $s = Get-Service -Name $script:Service -ErrorAction SilentlyContinue
  if (-not $s -or $s.Status -ne 'Running') { return $false }
  try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "http://127.0.0.1:$($script:Lc.paths.console_port)/" | Out-Null; return $true } catch { return $false }
}
function Wait-Until([scriptblock]$cond, [int]$seconds) {
  for ($t = 0; $t -lt $seconds; $t++) { if (& $cond) { return $true }; Start-Sleep -Seconds 1 }
  return $false
}
function Test-RebootPending {
  (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending') -or
  (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired')
}
function Get-DataPaths { @($script:Lc.paths.config) + @($script:Lc.paths.data) }

function Lc9 {
  $rc = Install-Msi $Pkg
  if ($rc -ne 0) { Out-Lc 'LC-9' $false "silent install exit $rc"; return }
  if (Test-RebootPending) { Out-Lc 'LC-9' $false 'install asks for a reboot'; return }
  Out-Lc 'LC-9' (Wait-Until { Test-Up } 30) 'service up and console on 127.0.0.1 within 30 s'
}
function Lc8 {
  $cmd = $script:Lc.test_interface.selftest
  if (-not $cmd) { Out-Lc 'LC-8' $false 'lifecycle.json has no test_interface.selftest'; return }
  & cmd.exe /c $cmd | Out-Null
  Out-Lc 'LC-8' ($LASTEXITCODE -eq 0) 'self-test on a fresh install'
}
function Lc10 {
  $before = (Get-Checksums (Get-DataPaths)) + (Get-Version)
  [void](Install-Msi $Pkg)
  $after = (Get-Checksums (Get-DataPaths)) + (Get-Version)
  Out-Lc 'LC-10' (($before -join "`n") -eq ($after -join "`n")) 'reinstall of the same version changes nothing'
}
function Lc11 {
  if (-not $PrevPkg) { Out-Lc 'LC-11' $false 'missing input PrevPkg'; return }
  [void](Remove-Msi -Purge); [void](Install-Msi $PrevPkg)
  $before = Get-Checksums (Get-DataPaths)
  $rc = Install-Msi $Pkg
  $after = Get-Checksums (Get-DataPaths)
  Out-Lc 'LC-11' (($rc -eq 0) -and $before -and (($before -join "`n") -eq ($after -join "`n"))) 'upgrade from N-1 keeps config and data (checksums)'
}
function Lc12 {
  if (-not $BrokenPkg) { Out-Lc 'LC-12' $false 'missing input BrokenPkg'; return }
  $good = Get-Version
  [void](Install-Msi $BrokenPkg)
  Out-Lc 'LC-12' (Wait-Until { ((Get-Version) -eq $good) -and (Test-Up) } 300) 'broken build rolls back within 5 min'
}
function Lc13 {
  if (-not $OlderPkg) { Out-Lc 'LC-13' $false 'missing input OlderPkg'; return }
  $before = Get-Version
  [void](Install-Msi $OlderPkg)
  Out-Lc 'LC-13' ((Get-Version) -eq $before) 'downgrade refused'
}
function Lc14 {
  $keep = @($script:Lc.keep_on_remove)
  $rc = Remove-Msi
  $bad = 0
  foreach ($p in $keep) { if (-not (Test-Path $p)) { $bad++ } }
  foreach ($p in (Get-DataPaths) + @($script:Lc.paths.logs)) { if ($p -and ($keep -notcontains $p) -and (Test-Path $p)) { $bad++ } }
  Out-Lc 'LC-14' (($rc -eq 0) -and ($bad -eq 0)) 'remove keeps exactly keep_on_remove'
}
function Lc15 {
  $rc = Remove-Msi -Purge
  $out = & pwsh -NoProfile -File (Join-Path $script:Here 'leftovers.ps1') -Lifecycle $Lifecycle
  Out-Lc 'LC-15' (($rc -eq 0) -and ($LASTEXITCODE -eq 0)) $(if ($out) { 'leftovers: ' + ($out -join '; ') } else { 'purge leaves nothing' })
}
function Lc16 {
  $tray = $script:Lc.test_interface.tray_start
  if ($tray) { Start-Process cmd.exe -ArgumentList '/c', $tray; Start-Sleep -Seconds 2 }
  $rc = Remove-Msi
  Out-Lc 'LC-16' (($rc -eq 0) -and -not (Test-RebootPending)) 'remove works with the tray running, no reboot'
}
function Lc17 {
  $users = @(query user 2>$null)
  if ($users.Count -gt 1) { Out-Lc 'LC-17' $false 'a user is signed in; run on a machine with none'; return }
  Out-Lc 'LC-17' (Test-Up) 'service up with nobody signed in'
}
function Lc29 {
  $pair = $script:Lc.test_interface.pair
  if (-not $pair) { Out-Lc 'LC-29' $false 'lifecycle.json has no test_interface.pair'; return }
  & cmd.exe /c $pair | Out-Null
  Out-Lc 'LC-29' (($LASTEXITCODE -eq 0) -and (Wait-Until { (Get-Service $script:Service).Status -eq 'Running' } 30)) 'service running after pairing, no manual step'
}
function Lc33 {
  $n = 0
  foreach ($root in @($script:Lc.paths.data_roots)) {
    if ($root -and (Test-Path $root)) { $n += @(Get-ChildItem $root -Directory | Where-Object { $_.Name -like "*$($script:Product)*" }).Count }
  }
  $legacy = @($script:Lc.paths.legacy_data | Where-Object { $_ -and (Test-Path $_) }).Count
  Out-Lc 'LC-33' (($n -le 1) -and ($legacy -eq 0)) "$n data folders, $legacy legacy folders"
}
function Lint { # LC-18: WiX ICE validation and one Apps-list entry
  & wix msi validate $Pkg | Out-Null
  $ice = $LASTEXITCODE -eq 0
  $entries = @(Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*', 'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue |
    Where-Object { $_.DisplayName -eq $script:Product }).Count
  Out-Lc 'LC-18' ($ice -and ($entries -eq 1)) "ICE $(if ($ice) { 'clean' } else { 'errors' }), $entries Apps-list entry(ies)"
}

$order = 'lc9', 'lc8', 'lc17', 'lc29', 'lc10', 'lc11', 'lc13', 'lc12', 'lc33', 'lint', 'lc16', 'lc14', 'lc15'
$todo = if ($Check -eq 'all') { $order } else { @($Check) }
foreach ($c in $todo) {
  switch ($c) {
    'lint' { Lint } 'lc8' { Lc8 } 'lc9' { Lc9 } 'lc10' { Lc10 } 'lc11' { Lc11 } 'lc12' { Lc12 } 'lc13' { Lc13 }
    'lc14' { Lc14 } 'lc15' { Lc15 } 'lc16' { Lc16 } 'lc17' { Lc17 } 'lc29' { Lc29 } 'lc33' { Lc33 }
    default { Write-Error "unknown check $c"; exit 2 }
  }
}
if ($script:Fails -gt 0) { exit 1 }
exit 0

<#
 One native update window for the whole update (UX-63).
 Steps: Review, Downloading, Waiting for work to finish, Installing, Restarting, Done.
 The result is on Done ("Now running x.y.z"). No message box, ever.
 The layout comes from the content: every control sizes itself (AutoSize, flow and table
 layouts). No fixed pixel height on a content control. No scrollbar, nothing cut off.

 -LayoutCheck builds the window off-screen at 100%, 150% and 200% text scale, lays it out,
 and exits 1 when a control is clipped or a button is off-window.
#>
param(
  [switch]$LayoutCheck,
  [string]$ProductName = "Example App",
  [string]$IconPath = "",
  [string]$Version = "1.2.3",
  [string]$BandColor = "",   # from the design-system tokens, passed by the build
  [string]$SurfaceColor = ""
)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$Steps = @("Review", "Downloading", "Waiting for work to finish", "Installing", "Restarting", "Done")

function New-UpdateWindow([double]$Scale) {
  $form = New-Object System.Windows.Forms.Form
  $form.Text = "$ProductName update"
  $form.AutoSize = $true
  $form.AutoSizeMode = "GrowAndShrink"
  $form.FormBorderStyle = "FixedDialog"
  $form.MaximizeBox = $false
  $form.StartPosition = "CenterScreen"
  $form.Padding = New-Object System.Windows.Forms.Padding(12)
  $form.Font = New-Object System.Drawing.Font("Segoe UI", [single](9 * $Scale))
  if ($IconPath -and (Test-Path $IconPath)) { $form.Icon = New-Object System.Drawing.Icon($IconPath) }

  $root = New-Object System.Windows.Forms.TableLayoutPanel
  $root.ColumnCount = 1
  $root.AutoSize = $true
  $root.Dock = "Fill"

  $band = New-Object System.Windows.Forms.Label   # the product band
  $band.Text = $ProductName
  $band.AutoSize = $true
  $band.Dock = "Top"
  $band.Padding = New-Object System.Windows.Forms.Padding(8)
  if ($BandColor) { $band.BackColor = [System.Drawing.ColorTranslator]::FromHtml($BandColor) }

  $step = New-Object System.Windows.Forms.Label
  $step.Name = "Step"
  $step.AutoSize = $true
  $step.MaximumSize = New-Object System.Drawing.Size([int](420 * $Scale), 0)
  $step.Text = ($Steps -join "  >  ")

  $detail = New-Object System.Windows.Forms.Label
  $detail.Name = "Detail"
  $detail.AutoSize = $true
  $detail.MaximumSize = New-Object System.Drawing.Size([int](420 * $Scale), 0)
  $detail.Text = "Now running $Version"

  $bar = New-Object System.Windows.Forms.ProgressBar
  $bar.Name = "Progress"
  $bar.Dock = "Top"

  $buttons = New-Object System.Windows.Forms.FlowLayoutPanel
  $buttons.FlowDirection = "RightToLeft"
  $buttons.AutoSize = $true
  $buttons.Dock = "Top"
  $primary = New-Object System.Windows.Forms.Button
  $primary.Name = "Primary"; $primary.Text = "Update"; $primary.AutoSize = $true
  $cancel = New-Object System.Windows.Forms.Button
  $cancel.Name = "Cancel"; $cancel.Text = "Cancel"; $cancel.AutoSize = $true
  $buttons.Controls.AddRange(@($primary, $cancel))

  foreach ($c in @($band, $step, $detail, $bar, $buttons)) { $root.Controls.Add($c) }
  $form.Controls.Add($root)
  return $form
}

function Test-Layout([System.Windows.Forms.Form]$Form) {
  $bad = @()
  $Form.CreateControl()
  $Form.PerformLayout()
  $client = $Form.ClientRectangle
  $stack = New-Object System.Collections.Stack
  foreach ($c in $Form.Controls) { $stack.Push($c) }
  while ($stack.Count) {
    $c = $stack.Pop()
    foreach ($k in $c.Controls) { $stack.Push($k) }
    $screen = $Form.RectangleToClient($c.Parent.RectangleToScreen($c.Bounds))
    if (-not $client.Contains($screen)) { $bad += "$($c.Name) $($c.GetType().Name) outside window" }
    if ($c -is [System.Windows.Forms.Label] -and $c.AutoSize) {
      $need = $c.GetPreferredSize($c.MaximumSize)
      if ($c.Width -lt $need.Width -or $c.Height -lt $need.Height) { $bad += "$($c.Name) text clipped" }
    }
  }
  return $bad
}

if ($LayoutCheck) {
  $failed = $false
  foreach ($scale in 1.0, 1.5, 2.0) {
    $form = New-UpdateWindow $scale
    $form.StartPosition = "Manual"
    $form.Location = New-Object System.Drawing.Point(-32000, -32000)   # off-screen
    $bad = Test-Layout $form
    foreach ($b in $bad) { Write-Output ("{0:P0}: {1}" -f $scale, $b); $failed = $true }
    $form.Dispose()
  }
  if ($failed) { exit 1 }
  Write-Output "Layout check passed at 100%, 150% and 200%."
  exit 0
}

# Normal run: one window; the host drives the steps. Failure and result are shown on Done,
# in this window, never in a separate box.
$form = New-UpdateWindow 1.0
[void]$form.ShowDialog()

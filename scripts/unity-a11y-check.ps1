<#
Screen-reader check of the Unity client's panel through Windows UI Automation (the interface used
by Narrator, NVDA and JAWS). Every step uses only what a screen-reader user has: it moves focus to
an element and types, or activates an element. It never clicks pixel positions.

  powershell -File scripts/unity-a11y-check.ps1 -Exe <DrikrTrainingSimulator.exe> `
    -Api https://localhost:8443/api/v1 -Ca deploy/tls/ca.crt -User trainee2
  (password from DRIKR_A11Y_PASSWORD)

Flow: sign in, open a practice scenario, start it, select a track, classify it, finish, and read the
result. Exit code 0 = pass. -drikrScreenReader makes the player publish its accessibility tree even
when no screen reader is running.
#>
param(
  [Parameter(Mandatory)] [string]$Exe,
  [string]$Api = 'https://localhost:8443/api/v1',
  [string]$Ca = '',
  [string]$User = 'trainee2',
  [string]$Password = $env:DRIKR_A11Y_PASSWORD
)
$ErrorActionPreference = 'Stop'
if (-not $Password) { throw 'Set DRIKR_A11Y_PASSWORD' }
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Windows.Forms, Microsoft.VisualBasic
$AE = [System.Windows.Automation.AutomationElement]

$playerArgs = @('-drikrApi', $Api, '-drikrScreenReader', '-screen-fullscreen', '0', '-screen-width', '1280', '-screen-height', '800',
  '-logFile', (Join-Path $env:TEMP 'unity-a11y-player.log'))
if ($Ca) { $playerArgs += @('-drikrCa', (Resolve-Path $Ca).Path) }
# Windows PowerShell 5.1 does not quote array arguments that contain spaces.
$argLine = ($playerArgs | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }) -join ' '
$proc = Start-Process -FilePath $Exe -ArgumentList $argLine -PassThru
$script:step = 0

function Log($msg) { $script:step++; Write-Output ('{0,2}. {1}' -f $script:step, $msg) }

function Root {
  $proc.Refresh()
  if ($proc.MainWindowHandle -eq 0) { return $null }
  return $AE::FromHandle($proc.MainWindowHandle)
}

function Items {
  $r = Root
  if (-not $r) { return @() }
  return @($r.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition))
}

function Find([string]$Pattern, [string]$Type = '', [int]$Seconds = 30, [switch]$Enabled) {
  $deadline = (Get-Date).AddSeconds($Seconds)
  while ((Get-Date) -lt $deadline) {
    foreach ($e in Items) {
      $c = $e.Current
      if ($c.Name -match $Pattern -and (-not $Type -or $c.ControlType.ProgrammaticName -eq "ControlType.$Type") -and (-not $Enabled -or $c.IsEnabled)) { return $e }
    }
    Start-Sleep -Milliseconds 300
  }
  $names = (Items | ForEach-Object { '{0}: {1}' -f $_.Current.ControlType.ProgrammaticName, $_.Current.Name }) -join "`n    "
  throw "Not found within $Seconds s: '$Pattern' $Type`n  Tree:`n    $names"
}

function Activate($e) {
  $e.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
}

function TypeInto($e, [string]$text) {
  [Microsoft.VisualBasic.Interaction]::AppActivate($proc.Id) | Out-Null
  $e.SetFocus()   # screen-reader focus: the panel gives this field keyboard focus
  try { Activate $e } catch { }   # Narrator "activate" (Enter) on an edit field does the same
  Start-Sleep -Milliseconds 400
  $escaped = [regex]::Replace($text, '[+^%~(){}\[\]]', '{$0}')
  [System.Windows.Forms.SendKeys]::SendWait($escaped)
  Start-Sleep -Milliseconds 300
}

function Value($e) {
  try { return $e.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value } catch { return '' }
}

try {
  $deadline = (Get-Date).AddSeconds(60)
  while (-not (Root) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }

  $h = Find '^Sign in$' 'Header' 60; Log "Sign-in screen exposed: header '$($h.Current.Name)'"
  $b = Find '^Sign in$' 'Button'
  if ($b.Current.IsEnabled) { throw 'Sign in should be disabled while the fields are empty' }
  Log 'Sign in button reported as disabled while fields are empty'

  $u = Find '^Username$' 'Edit'; TypeInto $u $User
  if ((Value (Find '^Username$' 'Edit')) -ne $User) { throw "Username field value is '$(Value $u)'" }
  Log "Typed the username into the focused field; value read back as '$User'"
  $pw = Find '^Password$' 'Edit'; TypeInto $pw $Password
  $pv = Value (Find '^Password$' 'Edit')
  if ($pv -match [regex]::Escape($Password)) { throw 'Password exposed to assistive technology' }
  Log "Typed the password; exposed only as '$pv'"

  Activate (Find '^Sign in$' 'Button' -Enabled); Log 'Activated Sign in'
  Find '^My exercises$' 'Header' 30 | Out-Null; Log 'Home screen exposed: My exercises'
  $practise = Find '^Practise$' 'Button' -Enabled
  Log "Practice entry: '$($practise.Current.Name)' (help text '$($practise.Current.HelpText)')"
  Activate $practise

  Activate (Find '^Start exercise$' 'Button' 30 -Enabled); Log 'Activated Start exercise'
  $status = Find '^Exercise status: \d\d:\d\d / ' 'Text' 30
  Log "Exercise status read as '$($status.Current.Name)'"
  $track = Find '^TRK-\d{3}' '' 90
  Log "Track exposed: '$($track.Current.Name)' ($($track.Current.ControlType.ProgrammaticName))"
  Activate $track
  Start-Sleep -Milliseconds 600
  $track = Find ([regex]::Escape($track.Current.Name.Substring(0, 7)))
  Log "Track after activation: value '$(Value $track)'"
  if ((Value $track) -ne 'checked') { throw 'Track toggle did not report checked' }

  Activate (Find '^Classification: Small multirotor$'); Log 'Selected Classification: Small multirotor'
  Start-Sleep -Milliseconds 400
  $opt = Find '^Classification: Small multirotor$'
  if ((Value $opt) -ne 'selected') { throw 'Option did not report selected' }
  Activate (Find '^Submit classification$' 'Button' -Enabled); Log 'Activated Submit classification'
  Find '^Decision recorded\.$' 'Text' 20 | Out-Null; Log "Confirmation exposed: 'Decision recorded.'"

  Activate (Find '^Finish$' 'Button' -Enabled); Log 'Activated Finish'
  Find '^Exercise complete$' 'Header' 60 | Out-Null
  $result = Find '^Overall' 'Text' 30
  Log "Result read: '$($result.Current.Name)'"
  Write-Output 'DRIKR_A11Y result=pass'
  exit 0
}
catch {
  Write-Output "DRIKR_A11Y result=fail $($_.Exception.Message)"
  exit 1
}
finally {
  Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
}

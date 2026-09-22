# build-release.ps1 - one-shot release build: portable exe + onedir payload + installer.
# Reads the repository source, writes every artifact under <repo>\dist-build.
# ASCII only (Windows PowerShell 5.1 + UTF-8-no-BOM would mangle non-ASCII literals).
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File packaging\build-release.ps1
#   powershell ... -File packaging\build-release.ps1 -AppVersion 1.1.2 -IconFile C:\path\app.ico
param(
  [string]$AppName = 'SnapCtrlAlt',
  [string]$AppVersion = '1.1.1',
  [string]$AppPublisher = '',
  [string]$IconFile = '',
  [string]$SourceDir = '',
  [string]$OutName = 'dist-build',
  [switch]$SkipInstaller,
  [switch]$Full
)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path   # ...\packaging
$repo = Split-Path -Parent $here                          # repository root
if (-not $SourceDir) { $SourceDir = $repo }
if (-not $IconFile) {
  $cand = Join-Path $here 'SnapCtrlAlt.ico'
  if (Test-Path $cand) { $IconFile = $cand }
}
# OutName 可换，避免覆盖正在运行的旧版 exe（Windows 会锁定文件导致构建失败）
$root = Join-Path $repo $OutName
$app  = Join-Path $root 'src'
$dist = Join-Path $root 'dist'
$work = Join-Path $root 'work'
$inst = Join-Path $repo 'installer'
$ISCC = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'

if (-not (Test-Path $SourceDir)) { throw "source dir not found: $SourceDir" }

# 1) freeze a read-only snapshot of the source
if (Test-Path $root) { Remove-Item $root -Recurse -Force }
New-Item -ItemType Directory -Path $app -Force | Out-Null
New-Item -ItemType Directory -Path $dist -Force | Out-Null
New-Item -ItemType Directory -Path $work -Force | Out-Null
New-Item -ItemType Directory -Path $inst -Force | Out-Null
Copy-Item (Join-Path $SourceDir '*.py') $app -Force
Copy-Item (Join-Path $SourceDir '*.bat') $app -Force -ErrorAction SilentlyContinue
Copy-Item (Join-Path $SourceDir '*.md') $app -Force -ErrorAction SilentlyContinue
Copy-Item (Join-Path $SourceDir '*.ico') $app -Force -ErrorAction SilentlyContinue
Write-Output "[release] source snapshot: $app"
$manifest = [ordered]@{}
Get-ChildItem $app -File | ForEach-Object {
  $manifest[$_.Name] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.Substring(0,16)
  Write-Output ("  {0,-28} {1,8} bytes  {2}" -f $_.Name, $_.Length, $manifest[$_.Name])
}

$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
$common = @('--noconfirm','--clean','--paths',$app,'--distpath',$dist,'--workpath',$work,'--specpath',$root)

# Verified against the project's real imports (only ctypes/io/PIL/math/tkinter/typing/
# threading/re/subprocess/json/os/sys/winreg/pathlib/argparse/queue are used), and the
# frozen selftest passes with them excluded: 31.04 MB -> 18.28 MB.
if (-not $Full) {
  $exclude = @('numpy','setuptools','pip','pydoc','doctest','unittest','xmlrpc','email',
               'http','urllib','webbrowser','multiprocessing','sqlite3','lib2to3',
               'distutils','pdb','tkinter.test','test')
  foreach ($m in $exclude) { $common += @('--exclude-module', $m) }
  Write-Output ("[release] slim mode: excluding {0} unused stdlib/3rd-party modules (use -Full to disable)" -f $exclude.Count)
}
if ($IconFile -and (Test-Path $IconFile)) {
  $common += @('--icon', (Resolve-Path $IconFile).Path)
  Write-Output "[release] exe icon: $IconFile"
}

# 2) portable onefile
Write-Output '[release] 1/3 portable onefile...'
python -m PyInstaller @common --onefile --windowed --name "$AppName-portable" (Join-Path $app 'snap.py')
if ($LASTEXITCODE -ne 0) { throw "onefile failed ($LASTEXITCODE)" }

# 3) onedir payload for the installer
Write-Output '[release] 2/3 onedir payload...'
python -m PyInstaller @common --onedir --windowed --name $AppName (Join-Path $app 'snap.py')
if ($LASTEXITCODE -ne 0) { throw "onedir failed ($LASTEXITCODE)" }

# 4) console selftest exe - proof the frozen build actually runs (windowed has no stdout)
Write-Output '[release] 3/3 console selftest + smoke test...'
python -m PyInstaller @common --onefile --console --name "$AppName-selftest" (Join-Path $app 'snap.py')
$selftestExe = Join-Path $dist "$AppName-selftest.exe"
# PowerShell 5.1: 原生命令把日志写到 stderr 时，`2>&1` + $ErrorActionPreference='Stop'
# 会被误报成 NativeCommandError 而中断脚本。改用 Start-Process 重定向到文件。
$tmpOut = Join-Path $work 'selftest.out.txt'
$tmpErr = Join-Path $work 'selftest.err.txt'
$proc = Start-Process -FilePath $selftestExe -ArgumentList '--selftest' -Wait -PassThru `
  -NoNewWindow -RedirectStandardOutput $tmpOut -RedirectStandardError $tmpErr
$selftestCode = $proc.ExitCode
$selftestOut = ((Get-Content $tmpOut -Raw -ErrorAction SilentlyContinue) +
                (Get-Content $tmpErr -Raw -ErrorAction SilentlyContinue))
if ($selftestCode -ne 0) { throw "frozen selftest failed, exit=$selftestCode`n$selftestOut" }

# 5) installer
$setup = $null
if (-not $SkipInstaller) {
  if (-not (Test-Path $ISCC)) { throw "ISCC.exe not found: $ISCC" }
  Write-Output '[release] 4/4 Inno Setup compile...'
  $iss = Join-Path $here 'SnapCtrlAlt.iss'
  $defs = @("/DAppName=$AppName", "/DAppVersion=$AppVersion", "/DSourceDir=$dist\$AppName")
  if ($AppPublisher) { $defs += "/DAppPublisher=$AppPublisher" }
  if ($IconFile)     { $defs += "/DIconFile=$IconFile" }
  & $ISCC @defs $iss | Write-Output
  if ($LASTEXITCODE -ne 0) { throw "ISCC failed ($LASTEXITCODE)" }
  $setup = Get-ChildItem $inst -Filter "$AppName-Setup-$AppVersion.exe" -ErrorAction SilentlyContinue |
           Select-Object -First 1
}

# 6) report
$rows = @()
foreach ($p in @(
    (Join-Path $dist "$AppName-portable.exe"),
    (Join-Path $dist "$AppName\$AppName.exe"),
    $selftestExe)) {
  if (Test-Path $p) { $rows += [pscustomobject]@{ Artifact = $p; MB = [math]::Round((Get-Item $p).Length/1MB,2) } }
}
if ($setup) { $rows += [pscustomobject]@{ Artifact = $setup.FullName; MB = [math]::Round($setup.Length/1MB,2) } }

$report = Join-Path $root 'release-report.md'
$md = @()
$md += '# SnapCtrlAlt release report'
$md += ''
$md += "- version: $AppVersion"
$md += "- built at: $stamp"
$md += "- source snapshot: ``$app``"
$md += "- source fingerprint (sha256[0:16]):"
foreach ($k in $manifest.Keys) { $md += "  - ``$k`` = ``$($manifest[$k])``" }
$md += ''
$md += '## Artifacts'
$md += ''
$md += '| artifact | size |'
$md += '|---|---|'
foreach ($r in $rows) { $md += "| ``$($r.Artifact)`` | $($r.MB) MB |" }
$md += ''
$md += '## Frozen selftest output'
$md += ''
$md += '```'
$md += $selftestOut.Trim()
$md += '```'
$md | Set-Content $report -Encoding UTF8

Write-Output ''
$rows | Format-Table -AutoSize
Write-Output "[release] report: $report"
Write-Output "[release] selftest exit=$selftestCode"

; SnapCtrlAlt.iss - installer (Inno Setup 6)
; Called by packaging\build-release.ps1:
;   ISCC.exe /DAppName=.. /DAppVersion=.. /DSourceDir=.. SnapCtrlAlt.iss
; Expects the onedir payload at ..\dist-build\dist\SnapCtrlAlt\ by default.
; ASCII only: ISCC reads a UTF-8-no-BOM file as ANSI, so non-ASCII literals would mojibake.

#ifndef AppName
  #define AppName "SnapCtrlAlt"
#endif
#ifndef AppVersion
  #define AppVersion "1.1.1"
#endif
#ifndef AppPublisher
  #define AppPublisher "mimo and DeepSeek Harness"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist-build\dist\SnapCtrlAlt"
#endif
#ifndef IconFile
  #define IconFile ""
#endif
#ifndef ExeName
  #define ExeName "SnapCtrlAlt.exe"
#endif

[Setup]
AppId={{9C4A7E31-5B62-4F0D-9A3E-2D71C8B4A650}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\installer
OutputBaseFilename={#AppName}-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#ExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
#ifdef IconFile
SetupIconFile={#IconFile}
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startup"; Description: "Start automatically when Windows starts (current user; can be toggled from the tray menu)"; GroupDescription: "Startup options:"
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#ExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#ExeName}"; Tasks: desktopicon

[Registry]
; Same key the in-app "autostart" switch writes (settings.py: APP_NAME = SnapCtrlAlt),
; so the installer task and the tray toggle stay in sync.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
  ValueName: "{#AppName}"; ValueData: """{app}\{#ExeName}"""; \
  Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\{#ExeName}"; Description: "Run {#AppName} now (Ctrl+Alt+D to capture)"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_tray.ico"

; Inno Setup script for RF2K-TRAINER
; NOTE: AppVersion is injected by CI: ISCC /DAppVersion=...

#define MyAppName "RF2K-TRAINER"
#define MyAppExe  "rf2k-trainer.exe"
#define MyAppBat  "rf2k-trainer.bat"
#define MyAppPublisher "tnxqso"
#define MyAppURL "https://github.com/tnxqso/rf2k-trainer"
#define AppVersion GetStringParam("AppVersion", "0.0.0-dev")

[Setup]
; Keep this GUID stable across versions
AppId={{D9A86C1E-6C7D-470C-9E5F-53A2A6C6E0B2}}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Install under the user's profile (matches README + .bat assumptions)
DefaultDirName={userprofile}\rf2k-trainer
DefaultGroupName=RF2K-TRAINER

; Brand the installer/uninstaller with our icon
SetupIconFile=assets\icons\rf2k-trainer.ico
UninstallDisplayIcon={app}\{#MyAppExe}

WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest

Compression=lzma
SolidCompression=yes
OutputBaseFilename=RF2K-TRAINER_{#AppVersion}_Setup

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
; Core binaries/config
Source: "dist\rf2k-trainer.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "rf2k-trainer.bat";       DestDir: "{app}"; Flags: ignoreversion
Source: "settings.example.yml";   DestDir: "{app}"; Flags: ignoreversion

; Docs (optional if present)
Source: "README.md";              DestDir: "{app}"; Flags: ignoreversion; Check: FileExists(ExpandConstant('{src}\README.md'))
Source: "CHANGELOG.md";           DestDir: "{app}"; Flags: ignoreversion; Check: FileExists(ExpandConstant('{src}\CHANGELOG.md'))
Source: "LICENSE";                DestDir: "{app}"; Flags: ignoreversion; Check: FileExists(ExpandConstant('{src}\LICENSE'))

; Data files needed at runtime
Source: "iaru_region_1.yml";          DestDir: "{app}"; Flags: ignoreversion
Source: "iaru_region_2.yml";          DestDir: "{app}"; Flags: ignoreversion
Source: "iaru_region_3.yml";          DestDir: "{app}"; Flags: ignoreversion
Source: "rf2k_segment_alignment.yml"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start Menu shortcut: target the BAT, but force the icon to be the EXE (so it looks nice)
Name: "{group}\RF2K-TRAINER";       Filename: "{app}\{#MyAppBat}"; IconFilename: "{app}\{#MyAppExe}"
; Optional desktop icon
Name: "{commondesktop}\RF2K-TRAINER"; Filename: "{app}\{#MyAppBat}"; IconFilename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
; Offer to run immediately after install
Filename: "{app}\{#MyAppBat}"; Description: "Launch RF2K-TRAINER now"; Flags: nowait postinstall skipifsilent

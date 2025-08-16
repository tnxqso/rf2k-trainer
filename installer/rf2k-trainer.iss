; Inno Setup script for RF2K-TRAINER
; ------------------------------------------------------------------
; Packaging policy:
; - Publish exactly ONE Windows installer to GitHub Releases:
;   RF2K-TRAINER_<version>_Setup.exe
; - No portable zips or raw exe uploads from CI.
; - Do not create settings.yml during install.
; ------------------------------------------------------------------
; CI contract:
; - Workflow calls ISCC with:
;     /DAppVersion=<semver-without-v>  (e.g., 0.9.301)
;     /DAppBin="C:\path\to\dist\rf2k-trainer.exe"
; - For local/manual builds, AppBin fallback points to ..\dist\rf2k-trainer.exe
; ------------------------------------------------------------------

#ifndef AppVersion
#define AppVersion "0.0.0-dev"
#endif

#ifndef AppBin
#define AppBin "..\\dist\\rf2k-trainer.exe"
#endif

#define MyAppName "RF2K-TRAINER"
#define MyAppExe  "rf2k-trainer.exe"
#define MyAppPublisher "RF2K-TRAINER Project"
#define MyAppURL "https://github.com/tnxqso/rf2k-trainer"

[Setup]
AppId={{A8D0911C-4C60-4E2D-BE2D-2C4D9050F3E1}}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
; Install in Program Files if elevated, else per-user in LocalAppData\Programs
DefaultDirName={autopf}\RF2K-TRAINER
DefaultGroupName=RF2K-TRAINER
DisableProgramGroupPage=yes
OutputDir=.
OutputBaseFilename=RF2K-TRAINER_{#AppVersion}_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline
UninstallDisplayIcon={app}\{#MyAppExe}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &Desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
; The workflow passes /DAppBin with an absolute path to rf2k-trainer.exe
; Fallback enables local builds without CI
Source: "{#AppBin}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start menu
Name: "{group}\RF2K-TRAINER, Launcher"; Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"
; Optional desktop icon
Name: "{userdesktop}\RF2K-TRAINER"; Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; (Intentionally disabled) If you want to auto-run after install, uncomment:
; Filename: "{app}\{#MyAppExe}"; Description: "Launch RF2K-TRAINER now"; Flags: nowait postinstall skipifsilent

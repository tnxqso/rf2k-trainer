; Inno Setup script for RF2K-TRAINER
; Installs exactly the repo files the user listed when present.
; Does NOT create settings.yml. Shortcuts point to the .bat if present.
;
; CI must pass:
;   /DAppVersion=<semver-without-v>
;   /DAppBin="C:\absolute\path\to\dist\rf2k-trainer.exe"
; Local builds: AppBin falls back to ..\dist\rf2k-trainer.exe

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

; Optional file flags (relative to this .iss in /installer)
#define HaveBat    FileExists("..\\rf2k-trainer.bat")
#define HaveSample FileExists("..\\settings.example.yml")
#define HaveR1     FileExists("..\\iaru_region_1.yml")
#define HaveR2     FileExists("..\\iaru_region_2.yml")
#define HaveR3     FileExists("..\\iaru_region_3.yml")
#define HaveSeg    FileExists("..\\rf2k_segment_alignment.yml")
#define HaveReadme FileExists("..\\README.md")
#define HaveChlog  FileExists("..\\CHANGELOG.md")

[Setup]
AppId={{A8D0911C-4C60-4E2D-BE2D-2C4D9050F3E1}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
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
; Main EXE from CI (force DestName so the installed file is exactly rf2k-trainer.exe)
Source: "{#AppBin}"; DestDir: "{app}"; DestName: "{#MyAppExe}"; Flags: ignoreversion

#if HaveBat
Source: "..\rf2k-trainer.bat"; DestDir: "{app}"; Flags: ignoreversion
#endif
#if HaveSample
Source: "..\settings.example.yml"; DestDir: "{app}"; Flags: ignoreversion
#endif
#if HaveR1
Source: "..\iaru_region_1.yml"; DestDir: "{app}"; Flags: ignoreversion
#endif
#if HaveR2
Source: "..\iaru_region_2.yml"; DestDir: "{app}"; Flags: ignoreversion
#endif
#if HaveR3
Source: "..\iaru_region_3.yml"; DestDir: "{app}"; Flags: ignoreversion
#endif
#if HaveSeg
Source: "..\rf2k_segment_alignment.yml"; DestDir: "{app}"; Flags: ignoreversion
#endif
#if HaveReadme
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
#endif
#if HaveChlog
Source: "..\CHANGELOG.md"; DestDir: "{app}"; Flags: ignoreversion
#endif

[Icons]
#if HaveBat
[Icons]
Name: "{group}\RF2K-TRAINER"; Filename: "{app}\rf2k-trainer.bat"; WorkingDir: "{app}"; IconFilename: "{app}\rf2k-trainer.exe"; IconIndex: 0
Name: "{userdesktop}\RF2K-TRAINER"; Filename: "{app}\rf2k-trainer.bat"; WorkingDir: "{app}"; Tasks: desktopicon; IconFilename: "{app}\rf2k-trainer.exe"; IconIndex: 0
#else
Name: "{group}\RF2K-TRAINER"; Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"
Name: "{userdesktop}\RF2K-TRAINER"; Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"; Tasks: desktopicon
#endif

[Run]
; No auto-run post install

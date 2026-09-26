#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

#define MyAppName "SoundCore"
#define MyAppPublisher "SoundCore"
#define MyAppURL "https://github.com/SlaVkoKRK/SoundCore"
#define MyAppExe "venv\Scripts\pythonw.exe"

[Setup]
AppId={{E43226CF-20AB-4A41-8E9F-6BB2B659D6C7}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\SoundCore
DefaultGroupName=SoundCore
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=output
OutputBaseFilename=SoundCore-Setup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\gui\assets\soundcore.ico
UninstallDisplayIcon={app}\gui\assets\soundcore.ico
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=yes
UsePreviousTasks=yes

[Languages]
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Utworz skrot na pulpicie"; GroupDescription: "Skroty:"; Flags: checkedonce

[Files]
Source: "..\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: ".git\*;.github\*;installer\*;venv\*;.venv\*;voice_profiles\*;output\*;cache\*;__pycache__\*;*.pyc"
Source: "bootstrap.ps1"; DestDir: "{app}\installer"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\SoundCore"; Filename: "{app}\{#MyAppExe}"; Parameters: """{app}\main.py"""; WorkingDir: "{app}"; IconFilename: "{app}\gui\assets\soundcore.ico"; Check: SoundCoreRuntimeReady
Name: "{autodesktop}\SoundCore"; Filename: "{app}\{#MyAppExe}"; Parameters: """{app}\main.py"""; WorkingDir: "{app}"; IconFilename: "{app}\gui\assets\soundcore.ico"; Tasks: desktopicon; Check: SoundCoreRuntimeReady

[Run]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ""{app}\installer\bootstrap.ps1"" -AppDir ""{app}"""; StatusMsg: "Przygotowywanie srodowiska SoundCore. Pierwsza instalacja moze potrwac kilka minut..."; Flags: waituntilterminated runhidden; BeforeInstall: PrepareBootstrapLog; AfterInstall: VerifyBootstrap
Filename: "{app}\{#MyAppExe}"; Parameters: """{app}\main.py"""; WorkingDir: "{app}"; Description: "Uruchom SoundCore"; Flags: nowait postinstall skipifsilent; Check: SoundCoreRuntimeReady

[UninstallDelete]
Type: filesandordirs; Name: "{app}\venv"
Type: filesandordirs; Name: "{app}\cache"
Type: files; Name: "{app}\.installed"

[Code]
function SoundCoreRuntimeReady(): Boolean;
begin
  Result :=
    FileExists(ExpandConstant('{app}\venv\Scripts\python.exe')) and
    FileExists(ExpandConstant('{app}\venv\Scripts\pythonw.exe')) and
    FileExists(ExpandConstant('{app}\.installed'));
end;


procedure PrepareBootstrapLog();
var
  LogPath, PSPath, ScriptPath, Msg: String;
begin
  LogPath := ExpandConstant('{app}\setup-bootstrap.log');
  PSPath := ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');
  ScriptPath := ExpandConstant('{app}\installer\bootstrap.ps1');
  Msg := 'SoundCore installer bootstrap diagnostic' + #13#10 +
         'PowerShell=' + PSPath + #13#10 +
         'PowerShellExists=' + BoolToStr(FileExists(PSPath), True) + #13#10 +
         'Script=' + ScriptPath + #13#10 +
         'ScriptExists=' + BoolToStr(FileExists(ScriptPath), True) + #13#10;
  SaveStringToFile(LogPath, Msg, False);
end;

procedure VerifyBootstrap();
var
  LogPath: String;
begin
  if not SoundCoreRuntimeReady() then
  begin
    LogPath := ExpandConstant('{app}\install.log');
    SaveStringToFile(ExpandConstant('{app}\setup-bootstrap.log'), 'RuntimeReady=False' + #13#10, True);
    MsgBox(
      'Nie udalo sie przygotowac srodowiska SoundCore.' + #13#10 + #13#10 +
      'Instalator nie uruchomi aplikacji ani nie utworzy niedzialajacych skrotow.' + #13#10 +
      'Szczegoly znajduja sie w:' + #13#10 + LogPath,
      mbError, MB_OK);
    RaiseException('SoundCore runtime bootstrap failed. See ' + LogPath);
  end;
end;

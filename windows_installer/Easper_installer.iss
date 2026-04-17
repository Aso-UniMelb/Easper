#define MyAppName "Easper"
#define MyAppVersion "0.1"
#define MyAppPublisher "Easper Research Group"
#define MyAppURL "https://github.com/Aso-UniMelb/Easper"
#define MyAppExeName "EasperInstaller.exe"

[Setup]
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\{#MyAppName}
UninstallDisplayIcon={app}\icon.ico
DefaultGroupName={#MyAppName}
OutputBaseFilename=Easper_Setup
SetupIconFile="icon.ico"
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
WizardStyle=modern

[Files]
Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "Easper.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "build-venv.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "download-whisper-small.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "ffmpeg-7.1.1-full_build\*"; DestDir: "{app}\ffmpeg"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\download-whisper-small.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\src\*"; DestDir: "{app}\src"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\windows_installer\pip_packages\*"; DestDir: "{app}\pip_packages"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\user_models\*"; DestDir: "{app}\user_models"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\Easper.bat"; IconFilename: "{app}\icon.ico"

[Run]
; Run python installer if downloaded
Filename: "{tmp}\python-installer.exe"; Parameters: "/quiet InstallAllUsers=0 PrependPath=1 TargetDir=""{localappdata}\Programs\Python\Python311"""; Check: NeedsPython; Flags: waituntilterminated

; Run build-venv.bat at the last step
Filename: "{app}\build-venv.bat"; WorkingDir: "{app}"; Flags: runhidden waituntilterminated

[UninstallDelete]
Type: filesandordirs; Name: "{app}\src\*"
Type: dirifempty; Name: "{app}\src"

[Code]
var
  DownloadPage: TDownloadWizardPage;

function IsPythonInstalled: Boolean;
begin
  Result := RegKeyExists(HKEY_LOCAL_MACHINE, 'SOFTWARE\Python\PythonCore\3.11') or
            RegKeyExists(HKEY_CURRENT_USER, 'SOFTWARE\Python\PythonCore\3.11') or
            RegKeyExists(HKEY_LOCAL_MACHINE, 'SOFTWARE\WOW6432Node\Python\PythonCore\3.11') or
            RegKeyExists(HKEY_CURRENT_USER, 'SOFTWARE\WOW6432Node\Python\PythonCore\3.11');
end;

function NeedsPython: Boolean;
begin
  Result := not IsPythonInstalled();
end;

procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage(SetupMessage(msgWizardPreparing), SetupMessage(msgPreparingDesc), nil);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpReady then begin
    if NeedsPython() then begin
      DownloadPage.Clear;
      DownloadPage.Add('https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe', 'python-installer.exe', '');
      DownloadPage.Show;
      try
        try
          DownloadPage.Download;
        except
          if DownloadPage.AbortedByUser then
            Log('Aborted by user.')
          else
            MsgBox('Error downloading Python installer. Please check your internet connection and try again.', mbError, MB_OK);
          Result := False;
        end;
      finally
        DownloadPage.Hide;
      end;
    end;
  end;
end;

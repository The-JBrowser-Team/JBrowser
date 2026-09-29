; ------------------------------------------------------------------------------------------
; JBrowser Windows installer (Inno Setup 6)
;
; Built by tools\build_installer.ps1, which passes:
;   /DAppVersion=1.4.0            the version from jbrowser\__init__.py
;   /DSourceDir=<dist\JBrowser>   the PyInstaller one-folder build
;   /DOutputDir=<dist\installer>  where JBrowser-Setup-<version>.exe is written
;   /DSignSetup /Sjbsign=...      only with a code-signing certificate (tools\sign.ps1): signs
;                                 Setup and the uninstaller
;
; Design notes
;   * Per-user install (no administrator prompt) into %LOCALAPPDATA%\Programs\JBrowser, so the
;     built-in auto-updater can run the next installer silently. An administrator can still
;     install for all users from the command line with /ALLUSERS.
;   * Upgrades install over the previous version (same AppId). Old program files are removed
;     first so no stale Qt libraries survive. User data in %APPDATA%\JBrowser is never touched.
;   * If JBrowser is open, Setup offers to close it (Windows Restart Manager): JBrowser saves its
;     session and exits cleanly, and the last page offers to start it again.
;   * The auto-updater runs this installer with /SILENT /RELAUNCH; /RELAUNCH (JBrowser's own
;     switch) starts the new version at the end. Other silent installs (e.g. winget) don't.
; ------------------------------------------------------------------------------------------

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\JBrowser"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist\installer"
#endif

#define AppName "JBrowser"
#define AppExe "JBrowser.exe"
#define AppPublisher "The JBrowser Team"
#define AppURL "https://github.com/The-JBrowser-Team/JBrowser"
; Held by a running JBrowser for its whole life (jbrowser/app.py).
#define AppMutex "JBrowser.AppMutex"

[Setup]
; The AppId identifies JBrowser to Windows forever: never change it, or upgrades will
; install side by side instead of replacing the old version.
AppId={{7A42C612-1FC3-4E3F-9B05-30CBB1CCD542}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
AppCopyright=(c) 2026 {#AppPublisher}. GNU General Public License v3.
VersionInfoVersion={#AppVersion}.0
VersionInfoDescription={#AppName} Setup
; Product name and version as in JBrowser.exe: code signing checks they match (docs/SIGNING.md).
VersionInfoProductName={#AppName}
VersionInfoProductTextVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline
UsedUserAreasWarning=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
LicenseFile=..\LICENSE
SetupIconFile=..\assets\jbrowser.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
OutputDir={#OutputDir}
OutputBaseFilename={#AppName}-Setup-{#AppVersion}
#ifdef SignSetup
SignTool=jbsign
SignedUninstaller=yes
#endif
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; A running JBrowser is closed through the Restart Manager instead of blocking Setup with
; AppMutex's "please close JBrowser" message. The window gets a normal close request first
; (it saves and exits); "force" only ends leftover web-engine helper processes.
CloseApplications=force
RestartApplications=no
ChangesAssociations=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "browser"; Description: "Register JBrowser as a web browser (so you can choose it as your default in Windows Settings)"; GroupDescription: "Windows integration:"

[InstallDelete]
; Remove the previous version's program files before copying the new ones.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; Comment: "Welcome to the internet - again"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; --- "Default apps" registration (per user, or per machine for an all-users install) ------
Root: HKA; Subkey: "Software\Clients\StartMenuInternet\JBrowser"; ValueType: string; ValueName: ""; ValueData: "{#AppName}"; Flags: uninsdeletekey; Tasks: browser
Root: HKA; Subkey: "Software\Clients\StartMenuInternet\JBrowser\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"",0"; Tasks: browser
Root: HKA; Subkey: "Software\Clients\StartMenuInternet\JBrowser\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"""; Tasks: browser
Root: HKA; Subkey: "Software\Clients\StartMenuInternet\JBrowser\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "{#AppName}"; Tasks: browser
Root: HKA; Subkey: "Software\Clients\StartMenuInternet\JBrowser\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "A spatial, privacy-focused web browser. Welcome to the internet - again."; Tasks: browser
Root: HKA; Subkey: "Software\Clients\StartMenuInternet\JBrowser\Capabilities"; ValueType: string; ValueName: "ApplicationIcon"; ValueData: """{app}\{#AppExe}"",0"; Tasks: browser
Root: HKA; Subkey: "Software\Clients\StartMenuInternet\JBrowser\Capabilities\StartMenu"; ValueType: string; ValueName: "StartMenuInternet"; ValueData: "JBrowser"; Tasks: browser
Root: HKA; Subkey: "Software\Clients\StartMenuInternet\JBrowser\Capabilities\URLAssociations"; ValueType: string; ValueName: "http"; ValueData: "JBrowserURL"; Tasks: browser
Root: HKA; Subkey: "Software\Clients\StartMenuInternet\JBrowser\Capabilities\URLAssociations"; ValueType: string; ValueName: "https"; ValueData: "JBrowserURL"; Tasks: browser
Root: HKA; Subkey: "Software\Clients\StartMenuInternet\JBrowser\Capabilities\FileAssociations"; ValueType: string; ValueName: ".html"; ValueData: "JBrowserHTML"; Tasks: browser
Root: HKA; Subkey: "Software\Clients\StartMenuInternet\JBrowser\Capabilities\FileAssociations"; ValueType: string; ValueName: ".htm"; ValueData: "JBrowserHTML"; Tasks: browser
Root: HKA; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "JBrowser"; ValueData: "Software\Clients\StartMenuInternet\JBrowser\Capabilities"; Flags: uninsdeletevalue; Tasks: browser
; --- The handlers Windows calls for links and .html files --------------------------------
Root: HKA; Subkey: "Software\Classes\JBrowserURL"; ValueType: string; ValueName: ""; ValueData: "JBrowser URL"; Flags: uninsdeletekey; Tasks: browser
Root: HKA; Subkey: "Software\Classes\JBrowserURL"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""; Tasks: browser
Root: HKA; Subkey: "Software\Classes\JBrowserURL\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"",0"; Tasks: browser
Root: HKA; Subkey: "Software\Classes\JBrowserURL\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: browser
Root: HKA; Subkey: "Software\Classes\JBrowserHTML"; ValueType: string; ValueName: ""; ValueData: "JBrowser HTML Document"; Flags: uninsdeletekey; Tasks: browser
Root: HKA; Subkey: "Software\Classes\JBrowserHTML\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"",0"; Tasks: browser
Root: HKA; Subkey: "Software\Classes\JBrowserHTML\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: browser

[Run]
; Normal install: offer to start JBrowser on the last page.
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
; Silent install by the auto-updater (/RELAUNCH): start the new version straight away.
Filename: "{app}\{#AppExe}"; Flags: nowait; Check: RelaunchAfterUpdate

[Code]
{ True when the auto-updater started this silent install and wants JBrowser reopened afterwards. }
function RelaunchAfterUpdate: Boolean;
var
  I: Integer;
begin
  Result := False;
  if WizardSilent then
    for I := 1 to ParamCount do
      if CompareText(ParamStr(I), '/RELAUNCH') = 0 then
        Result := True;
end;

{ Uninstalling while JBrowser is open would leave files behind: ask for it to be closed first.
  A silent uninstall waits up to 30 seconds for it to close, then gives up. }
function InitializeUninstall: Boolean;
var
  Waited: Integer;
begin
  Result := True;
  Waited := 0;
  while CheckForMutexes('{#AppMutex}') do
  begin
    if UninstallSilent then
    begin
      if Waited >= 30 then
      begin
        Result := False;
        Exit;
      end;
      Sleep(1000);
      Waited := Waited + 1;
    end
    else if MsgBox('JBrowser is open. Please close it (your cards and spaces are saved), then click OK '
                   + 'to continue uninstalling.', mbInformation, MB_OKCANCEL) = IDCANCEL then
    begin
      Result := False;
      Exit;
    end;
  end;
end;

{ On an interactive uninstall, offer to delete the user's JBrowser data as well (default: keep). }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent then
  begin
    if MsgBox('Also delete your JBrowser data (spaces, cards, history, bookmarks, saved passwords and settings)?'
              + #13#10#13#10 + 'Choose No to keep it for a future installation.',
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
    begin
      DelTree(ExpandConstant('{userappdata}\JBrowser'), True, True, True);
      DelTree(ExpandConstant('{localappdata}\JBrowser'), True, True, True);
    end;
  end;
end;

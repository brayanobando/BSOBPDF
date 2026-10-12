; Instalador de BSOBPDF para Windows (Inno Setup 6.3 o superior)
; Compilar desde esta carpeta, después de PyInstaller:
;   ISCC.exe /DAppVersion=1.0.0 BSOBPDF.iss
; Resultado: dist\BSOBPDF-Setup-1.0.0.exe

#define AppName "BSOBPDF"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppPublisher "Brayan Stiven Obando"
#define AppURL "https://github.com/brayanobando/BSOBPDF"
#define AppExe "BSOBPDF.exe"

[Setup]
AppId={{8F1C2B7E-5D3A-4C9B-9E61-0B6B55FFE14D}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Se instala solo para el usuario actual (no pide permisos de administrador),
; con opción de instalar para todos los usuarios.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=BSOBPDF-Setup-{#AppVersion}
SetupIconFile=bsobpdf.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
LicenseFile=..\LICENSE
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoDescription=Instalador de BSOBPDF

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\BSOBPDF\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; Comment: "Herramientas PDF en tu computador"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon; Comment: "Herramientas PDF en tu computador"

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Perfil de la ventana (firmas guardadas, ajustes) y registro del programa
Type: filesandordirs; Name: "{localappdata}\BSOBPDF\ventana"
Type: files; Name: "{localappdata}\BSOBPDF\bsobpdf.log"
Type: files; Name: "{localappdata}\BSOBPDF\puerto.txt"

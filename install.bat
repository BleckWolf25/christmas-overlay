@echo off
set DEST=%LOCALAPPDATA%\ChristmasOverlay
taskkill /f /im ChristmasOverlay.exe >nul 2>&1
if not exist "%DEST%" mkdir "%DEST%"
copy /y "%~dp0ChristmasOverlay.exe" "%DEST%\ChristmasOverlay.exe" >nul
powershell -NoProfile -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Programs')+'\Christmas Overlay.lnk');" ^
  "$s.TargetPath='%DEST%\ChristmasOverlay.exe';$s.Save()"
start "" "%DEST%\ChristmasOverlay.exe"